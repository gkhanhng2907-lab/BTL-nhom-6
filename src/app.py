import os
import io
import re
import csv
import json
import html
import hmac
import random
import sqlite3
import smtplib
from datetime import datetime
from functools import wraps
from email.message import EmailMessage
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)
DB_NAME = os.environ.get("DB_NAME", "phishing_system.db")

# Địa chỉ mà trình duyệt của nhân viên dùng để mở link theo dõi trong thư giả lập
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/")

# Tài khoản Admin (có thể đổi bằng biến môi trường ADMIN_USERNAME / ADMIN_PASSWORD)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password4admin")

# Danh mục trọng tâm theo phòng ban (tên khớp 100% với emails.json)
DEPT_PRIORITY = {
    "EMP01": ["Hóa đơn, thuế", "Giả mạo sếp", "Ngân hàng"],                          # Kế toán
    "EMP02": ["Nhân sự, lương thưởng", "Giả mạo sếp"],                                # Nhân sự
    "EMP03": ["IT Support", "Cảnh báo bảo mật tài khoản"],                            # IT/Dev
    "EMP04": ["Hợp đồng, đối tác giả", "Chia sẻ tài liệu giả", "Giao hàng, bưu kiện"]  # Kinh doanh
}

# Tham số chiến dịch mặc định. Admin có thể đổi trong hộp thoại "Bắt đầu".
DEFAULT_SETTINGS = {
    "spear_count": 5,            # SPEAR_COUNT: thư lừa đảo đúng chuyên môn phòng ban
    "other_phishing_count": 3,   # OTHER_PHISHING_COUNT: thư lừa đảo đại trà
    "legit_count": 4,            # LEGIT_COUNT: thư hợp lệ
    "points_correct": 10,        # cộng khi báo đúng thư lừa đảo
    "points_false_positive": 5,  # trừ khi báo nhầm thư thật (lưu số dương)
    "points_missed": 10,         # trừ khi bỏ sót thư lừa đảo (lưu số dương)
}
SETTING_LIMITS = {
    "spear_count": (0, 20),
    "other_phishing_count": (0, 20),
    "legit_count": (0, 20),
    "points_correct": (0, 100),
    "points_false_positive": (0, 100),
    "points_missed": (0, 100),
}

STATUS_LABELS = {
    "correct": "Đã Report đúng",
    "false_positive": "Báo cáo nhầm",
    "clicked": "Đã bấm link độc hại",
    "missed": "Bỏ sót",
    "pending": "Chưa xử lý",
    "legit": "Thư hợp lệ",
}


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_column_if_missing(cursor, table, column, ddl):
    """Thêm cột mới cho database cũ mà không phải xóa file .db. Trả về True nếu vừa thêm."""
    cols = [c[1] for c in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if column in cols:
        return False
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    return True


# ==========================================
# 1. KHỞI TẠO DATABASE & NẠP EMAILS.JSON
# ==========================================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            smtp_host TEXT NOT NULL,
            smtp_port INTEGER NOT NULL,
            webmail_port INTEGER NOT NULL,
            score INTEGER DEFAULT 100
        )
    """)

    existing_cols = [col[1] for col in cursor.execute("PRAGMA table_info(employees)").fetchall()]
    if "employee_code" not in existing_cols:
        cursor.execute("DROP TABLE employees")
        cursor.execute("""
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                smtp_host TEXT NOT NULL,
                smtp_port INTEGER NOT NULL,
                webmail_port INTEGER NOT NULL,
                score INTEGER DEFAULT 100
            )
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_templates (
            id INTEGER PRIMARY KEY,
            category TEXT,
            is_phishing INTEGER,
            sender TEXT,
            subject TEXT,
            body TEXT,
            red_flags TEXT
        )
    """)
    # Cột bật/tắt kịch bản (Template Editor)
    add_column_if_missing(cursor, "email_templates", "is_active", "INTEGER DEFAULT 1")
    cursor.execute("UPDATE email_templates SET is_active = 1 WHERE is_active IS NULL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            email_id INTEGER,
            reported INTEGER DEFAULT 0,
            is_scored INTEGER DEFAULT 0,
            FOREIGN KEY(employee_id) REFERENCES employees(id),
            FOREIGN KEY(email_id) REFERENCES email_templates(id)
        )
    """)
    # Các cột mới: bấm link, điểm thực tế của từng thư, mốc thời gian
    add_column_if_missing(cursor, "campaign_logs", "clicked", "INTEGER DEFAULT 0")
    added_points = add_column_if_missing(cursor, "campaign_logs", "points_delta", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "campaign_logs", "sent_at", "TEXT")
    add_column_if_missing(cursor, "campaign_logs", "reported_at", "TEXT")
    add_column_if_missing(cursor, "campaign_logs", "clicked_at", "TEXT")
    if added_points:
        # Dữ liệu cũ được chấm theo luật gốc +10 / -5 / -10
        cursor.execute("""
            UPDATE campaign_logs SET points_delta = (
                SELECT CASE
                    WHEN et.is_phishing = 1 AND campaign_logs.reported = 1 THEN 10
                    WHEN et.is_phishing = 0 AND campaign_logs.reported = 1 THEN -5
                    WHEN et.is_phishing = 1 AND campaign_logs.is_scored = 1 THEN -10
                    ELSE 0 END
                FROM email_templates et WHERE et.id = campaign_logs.email_id
            )
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    for key, value in DEFAULT_SETTINGS.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

    use_docker = os.environ.get("USE_DOCKER", "1") == "1"
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0:
        default_employees = [
            ("EMP01", "Nhân viên 1 (Kế toán)", "nv1@company.local", "employee-1" if use_docker else "localhost", 1025 if use_docker else 1021, 8021, 100),
            ("EMP02", "Nhân viên 2 (Nhân sự)", "nv2@company.local", "employee-2" if use_docker else "localhost", 1025 if use_docker else 1022, 8022, 100),
            ("EMP03", "Nhân viên 3 (IT/Dev)", "nv3@company.local", "employee-3" if use_docker else "localhost", 1025 if use_docker else 1023, 8023, 100),
            ("EMP04", "Nhân viên 4 (Kinh doanh)", "nv4@company.local", "employee-4" if use_docker else "localhost", 1025 if use_docker else 1024, 8024, 100),
        ]
        cursor.executemany("""
            INSERT INTO employees (employee_code, name, email, smtp_host, smtp_port, webmail_port, score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, default_employees)

    cursor.execute("SELECT COUNT(*) FROM email_templates")
    if cursor.fetchone()[0] == 0 and os.path.exists("emails.json"):
        with open("emails.json", "r", encoding="utf-8") as f:
            emails_data = json.load(f)
            for item in emails_data:
                red_flags_val = item.get("red_flags", "")
                if isinstance(red_flags_val, list):
                    red_flags_val = " | ".join(red_flags_val)
                cursor.execute("""
                    INSERT INTO email_templates (id, category, is_phishing, sender, subject, body, red_flags, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    item["id"],
                    item["category"],
                    int(item["is_phishing"]),
                    item["sender"],
                    item["subject"],
                    item["body"],
                    red_flags_val
                ))

    conn.commit()
    conn.close()


# ==========================================
# 2. CẤU HÌNH CHIẾN DỊCH (SETTINGS)
# ==========================================
def get_settings(cursor):
    cfg = dict(DEFAULT_SETTINGS)
    for row in cursor.execute("SELECT key, value FROM settings").fetchall():
        if row["key"] in cfg:
            try:
                cfg[row["key"]] = int(row["value"])
            except (TypeError, ValueError):
                pass
    return cfg


def parse_settings(data):
    """Kiểm tra dữ liệu Admin gửi lên. Trả về (cfg, lỗi)."""
    cfg = {}
    for key, (low, high) in SETTING_LIMITS.items():
        raw = data.get(key, DEFAULT_SETTINGS[key])
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None, f"Giá trị '{key}' phải là số nguyên."
        if value < low or value > high:
            return None, f"Giá trị '{key}' phải nằm trong khoảng {low} đến {high}."
        cfg[key] = value
    if cfg["spear_count"] + cfg["other_phishing_count"] + cfg["legit_count"] == 0:
        return None, "Mỗi nhân viên phải nhận ít nhất 1 thư."
    return cfg, None


# ==========================================
# 3. GỬI MAIL (CÓ LINK THEO DÕI)
# ==========================================
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def build_html_body(text, log_id):
    """Chuyển thư dạng chữ sang HTML. Mọi link giữ nguyên chữ hiển thị (tên miền giả)
    nhưng thực chất trỏ về /click/<log_id> của hệ thống, để biết nhân viên có bấm hay không
    mà không bao giờ truy cập tên miền thật bên ngoài."""
    parts = []
    last = 0
    for m in URL_RE.finditer(text):
        url = m.group(0)
        trailing = ""
        while url and url[-1] in ".,;:)!?":
            trailing = url[-1] + trailing
            url = url[:-1]
        parts.append(html.escape(text[last:m.start()]))
        parts.append(f'<a href="{PUBLIC_BASE_URL}/click/{log_id}">{html.escape(url)}</a>{html.escape(trailing)}')
        last = m.end()
    parts.append(html.escape(text[last:]))
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;white-space:pre-wrap">'
        + "".join(parts) + "</div>"
    )


def send_smtp_email(smtp_host, smtp_port, sender, recipient, emp_code, subject, body, log_id):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"[#MAIL-{log_id}] {subject}"

    full_body = (
        f"Mã định danh thư: #MAIL-{log_id} (Người nhận: {emp_code})\n"
        + "-" * 45 + f"\n\n{body}"
    )
    msg.set_content(full_body)
    msg.add_alternative(build_html_body(full_body, log_id), subtype="html")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
            server.send_message(msg)
    except Exception as e:
        print(f"[LỖI SMTP] Không gửi được tới {smtp_host}:{smtp_port} - {e}")


# ==========================================
# 4. XÁC THỰC ADMIN
# ==========================================
def check_admin_auth(username, password):
    return (hmac.compare_digest(str(username), ADMIN_USERNAME)
            and hmac.compare_digest(str(password), ADMIN_PASSWORD))


def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_admin_auth(auth.username, auth.password):
            return Response(
                "⚠️ Truy cập bị từ chối! Bạn không có quyền truy cập trang Quản trị này.",
                401,
                {"WWW-Authenticate": 'Basic realm="Admin Login Required"'}
            )
        # Chặn giả mạo yêu cầu từ trang web khác (CSRF): các lệnh ghi phải do giao diện admin gửi
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Requested-With") != "fetch":
            return jsonify({"status": "error", "message": "Yêu cầu không hợp lệ."}), 403
        return f(*args, **kwargs)
    return decorated


# ==========================================
# 5. PHÁT ĐỘNG CHIẾN DỊCH (SPEAR PHISHING)
# ==========================================
@app.route("/campaign-settings", methods=["GET"])
@requires_admin
def campaign_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cfg = get_settings(cursor)
    pools = {
        "phishing_active": cursor.execute("SELECT COUNT(*) FROM email_templates WHERE is_phishing = 1 AND is_active = 1").fetchone()[0],
        "legit_active": cursor.execute("SELECT COUNT(*) FROM email_templates WHERE is_phishing = 0 AND is_active = 1").fetchone()[0],
    }
    conn.close()
    return jsonify({"settings": cfg, "limits": SETTING_LIMITS, "pools": pools})


@app.route("/start-campaign", methods=["POST"])
@requires_admin
def start_campaign():
    data = request.get_json(silent=True) or {}
    cfg, error = parse_settings(data) if data else (None, None)

    conn = get_db_connection()
    cursor = conn.cursor()

    if error:
        conn.close()
        return jsonify({"status": "error", "message": error}), 400
    if cfg is None:  # không gửi tham số: dùng cấu hình đã lưu
        cfg = get_settings(cursor)
    else:
        for key, value in cfg.items():
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

    employees = cursor.execute("SELECT * FROM employees").fetchall()
    # Chỉ dùng các kịch bản đang được bật
    all_emails = cursor.execute("SELECT * FROM email_templates WHERE is_active = 1").fetchall()

    phishing_by_cat = {}
    legit_emails = []
    for mail in all_emails:
        if mail["is_phishing"] == 1:
            phishing_by_cat.setdefault(mail["category"], []).append(mail)
        else:
            legit_emails.append(mail)

    warnings = []
    total_sent_per_emp = 0
    actual = {"spear": 0, "other": 0, "legit": 0}
    sent_at = now_str()

    # Cảnh báo chung cho cả 3 nhóm khi kho kịch bản đang bật không đủ thư
    if len(legit_emails) < cfg["legit_count"]:
        warnings.append(f"Chỉ có {len(legit_emails)} thư hợp lệ đang bật (yêu cầu {cfg['legit_count']}).")

    for emp in employees:
        selected_emails = []
        emp_code = emp["employee_code"].upper()
        priority_cats = DEPT_PRIORITY.get(emp_code, [])

        # 1. Spear Phishing: lấy từ các danh mục trọng tâm của phòng ban
        spear_pool = [m for cat in priority_cats for m in phishing_by_cat.get(cat, [])]
        n_spear = min(cfg["spear_count"], len(spear_pool))
        if n_spear < cfg["spear_count"]:
            warnings.append(f"{emp_code} chỉ có {len(spear_pool)} thư Spear Phishing đang bật (yêu cầu {cfg['spear_count']}).")
        selected_emails.extend(random.sample(spear_pool, n_spear))

        # 2. Phishing đại trà: mỗi danh mục còn lại lấy 1 thư trước, thiếu thì lấy thêm từ phần còn lại
        other_cats = [cat for cat, mails in phishing_by_cat.items() if cat not in priority_cats and mails]
        random.shuffle(other_cats)
        chosen_other = []
        for cat in other_cats[:cfg["other_phishing_count"]]:
            chosen_other.append(random.choice(phishing_by_cat[cat]))
        missing = cfg["other_phishing_count"] - len(chosen_other)
        if missing > 0:
            leftovers = [m for cat in other_cats for m in phishing_by_cat[cat] if m not in chosen_other]
            extra = random.sample(leftovers, min(missing, len(leftovers)))
            chosen_other.extend(extra)
            if len(chosen_other) < cfg["other_phishing_count"]:
                warnings.append(f"{emp_code} chỉ có {len(chosen_other)} thư phishing đại trà đang bật (yêu cầu {cfg['other_phishing_count']}).")
        selected_emails.extend(chosen_other)

        # 3. Thư hợp lệ
        n_legit = min(cfg["legit_count"], len(legit_emails))
        selected_emails.extend(random.sample(legit_emails, n_legit))
        actual = {"spear": n_spear, "other": len(chosen_other), "legit": n_legit}

        random.shuffle(selected_emails)
        total_sent_per_emp = len(selected_emails)

        for mail in selected_emails:
            cursor.execute("""
                INSERT INTO campaign_logs (employee_id, email_id, reported, is_scored, clicked, points_delta, sent_at)
                VALUES (?, ?, 0, 0, 0, 0, ?)
            """, (emp["id"], mail["id"], sent_at))
            log_id = cursor.lastrowid

            send_smtp_email(
                smtp_host=emp["smtp_host"],
                smtp_port=emp["smtp_port"],
                sender=mail["sender"],
                recipient=emp["email"],
                emp_code=emp["employee_code"],
                subject=mail["subject"],
                body=mail["body"],
                log_id=log_id
            )

    conn.commit()
    conn.close()

    # Danh sách cảnh báo giống nhau cho các nhân viên chỉ cần hiện một lần
    warnings = list(dict.fromkeys(warnings))
    return jsonify({
        "status": "success",
        "message": (f"Đã phát động chiến dịch! Mỗi nhân viên nhận {total_sent_per_emp} email "
                    f"({actual['spear']} Spear Phishing + {actual['other']} Phishing khác + {actual['legit']} mail thật)."),
        "warnings": warnings,
    })


# ==========================================
# 6. LUỒNG CHẤM ĐIỂM TỰ ĐỘNG & REPORT
# ==========================================
def apply_report(cursor, log, emp_id, who):
    """Chấm điểm một lượt báo cáo. `who` là câu mô tả người được chấm."""
    cfg = get_settings(cursor)
    if log["is_phishing"] == 1:
        delta = cfg["points_correct"]
        feedback_type = "correct"
        msg = f"Chính xác! {who} được cộng +{delta} điểm."
    else:
        delta = -cfg["points_false_positive"]
        feedback_type = "false_positive"
        msg = f"Nhầm lẫn! Đây là email công việc hợp lệ ({who} bị trừ {delta} điểm)."

    cursor.execute("UPDATE employees SET score = score + ? WHERE id = ?", (delta, emp_id))
    cursor.execute(
        "UPDATE campaign_logs SET reported = 1, is_scored = 1, points_delta = ?, reported_at = ? WHERE id = ?",
        (delta, now_str(), log["id"])
    )
    return delta, feedback_type, msg


LOG_QUERY = """
    SELECT cl.*, et.is_phishing, et.red_flags, et.subject, et.category
    FROM campaign_logs cl
    JOIN email_templates et ON cl.email_id = et.id
    WHERE cl.id = ?
"""


@app.route("/report", methods=["POST"])
def report_email_by_employee():
    data = request.get_json() or {}
    emp_code = data.get("employee_code", "").strip().upper()
    raw_mail_input = data.get("mail_code", "").strip()

    match = re.search(r"\d+", raw_mail_input)
    if not match:
        return jsonify({"status": "error", "message": "Mã định danh email không hợp lệ (VD: #MAIL-5 hoặc 5)!"}), 400
    log_id = int(match.group())

    conn = get_db_connection()
    cursor = conn.cursor()

    emp = cursor.execute("SELECT * FROM employees WHERE UPPER(employee_code) = ?", (emp_code,)).fetchone()
    if not emp:
        conn.close()
        return jsonify({"status": "error", "message": f"Không tìm thấy Mã nhân viên '{emp_code}'! (Hãy nhập EMP01, EMP02, EMP03 hoặc EMP04)"}), 404

    log = cursor.execute(LOG_QUERY, (log_id,)).fetchone()

    if not log:
        conn.close()
        return jsonify({"status": "error", "message": f"Không tìm thấy bức thư #MAIL-{log_id} trong chiến dịch!"}), 404

    if log["employee_id"] != emp["id"]:
        conn.close()
        return jsonify({"status": "warning", "message": f"Thư #MAIL-{log_id} không thuộc hộp thư của nhân viên {emp_code}!"}), 400

    if log["is_scored"] == 1:
        conn.close()
        return jsonify({"status": "warning", "message": f"Thư #MAIL-{log_id} đã được báo cáo hoặc đã chốt điểm trước đó!"}), 400

    delta, feedback_type, msg = apply_report(cursor, log, emp["id"], f"Nhân viên {emp_code}")

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "feedback_type": feedback_type,
        "score_change": delta,
        "message": msg,
        "red_flags": log["red_flags"],
        "category": log["category"],
        "subject": log["subject"]
    })


@app.route("/report/<int:log_id>", methods=["POST"])
def report_email(log_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    log = cursor.execute(LOG_QUERY, (log_id,)).fetchone()

    if not log:
        conn.close()
        return jsonify({"status": "error", "message": "Không tìm thấy mã thư này!"}), 404

    if log["is_scored"] == 1:
        conn.close()
        return jsonify({"status": "warning", "message": "Thư này đã được báo cáo hoặc đã chốt điểm trước đó!"}), 400

    delta, feedback_type, msg = apply_report(cursor, log, log["employee_id"], "Bạn")

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "feedback_type": feedback_type,
        "score_change": delta,
        "message": msg,
        "red_flags": log["red_flags"],
        "category": log["category"],
        "subject": log["subject"]
    })


@app.route("/click/<int:log_id>")
def track_click(log_id):
    """Nhân viên bấm link trong thư giả lập. Chỉ ghi nhận, không tiết lộ thư thật hay giả."""
    conn = get_db_connection()
    log = conn.execute("SELECT id, clicked FROM campaign_logs WHERE id = ?", (log_id,)).fetchone()
    if not log:
        conn.close()
        return render_template("clicked.html", found=False), 404
    if not log["clicked"]:
        conn.execute("UPDATE campaign_logs SET clicked = 1, clicked_at = ? WHERE id = ?", (now_str(), log_id))
        conn.commit()
    conn.close()
    return render_template("clicked.html", found=True, log_id=log_id)


@app.route("/finalize-campaign", methods=["POST"])
@requires_admin
def finalize_campaign():
    conn = get_db_connection()
    cursor = conn.cursor()
    cfg = get_settings(cursor)

    missed_logs = cursor.execute("""
        SELECT cl.id, cl.employee_id
        FROM campaign_logs cl
        JOIN email_templates et ON cl.email_id = et.id
        WHERE et.is_phishing = 1 AND cl.reported = 0 AND cl.is_scored = 0
    """).fetchall()

    for item in missed_logs:
        cursor.execute("UPDATE employees SET score = score - ? WHERE id = ?", (cfg["points_missed"], item["employee_id"]))
        cursor.execute("UPDATE campaign_logs SET is_scored = 1, points_delta = ? WHERE id = ?",
                       (-cfg["points_missed"], item["id"]))

    cursor.execute("UPDATE campaign_logs SET is_scored = 1 WHERE is_scored = 0")

    conn.commit()
    conn.close()
    return jsonify({
        "status": "success",
        "missed_count": len(missed_logs),
        "message": f"Đã chốt chiến dịch! Phát hiện {len(missed_logs)} email lừa đảo bị bỏ sót (-{cfg['points_missed']}đ/mail)."
    })


@app.route("/reset", methods=["POST"])
@requires_admin
def reset_system():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM campaign_logs")
    cursor.execute("UPDATE employees SET score = 100")
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Đã Reset toàn bộ dữ liệu và đưa điểm về 100!"})


# ==========================================
# 7. TEMPLATE EDITOR (QUẢN LÝ KỊCH BẢN EMAIL)
# ==========================================
def template_to_dict(row):
    return {
        "id": row["id"],
        "category": row["category"],
        "is_phishing": int(row["is_phishing"]),
        "sender": row["sender"],
        "subject": row["subject"],
        "body": row["body"],
        "red_flags": row["red_flags"] or "",
        "is_active": int(row["is_active"] if row["is_active"] is not None else 1),
    }


def parse_template_payload(data):
    """Kiểm tra dữ liệu form kịch bản. Trả về (dữ liệu sạch, lỗi)."""
    category = str(data.get("category", "")).strip()
    sender = str(data.get("sender", "")).strip()
    subject = str(data.get("subject", "")).strip()
    body = str(data.get("body", "")).strip()
    red_flags = str(data.get("red_flags", "")).strip()
    try:
        is_phishing = 1 if int(data.get("is_phishing", 1)) == 1 else 0
    except (TypeError, ValueError):
        return None, "Loại thư không hợp lệ."

    if not category:
        return None, "Hãy chọn hoặc nhập danh mục."
    if not sender:
        return None, "Hãy nhập người gửi (VD: Tên <ten@congty.vn>)."
    if not subject:
        return None, "Hãy nhập tiêu đề thư."
    if not body:
        return None, "Hãy nhập nội dung thư."
    if is_phishing == 1 and not red_flags:
        return None, "Thư lừa đảo cần có phần giải thích dấu hiệu nhận biết (red flags) để hiển thị cho nhân viên."
    if is_phishing == 0:
        red_flags = ""
    if len(subject) > 200 or len(sender) > 200 or len(category) > 100:
        return None, "Tiêu đề, người gửi hoặc danh mục quá dài."
    if len(body) > 10000 or len(red_flags) > 5000:
        return None, "Nội dung quá dài."
    return {
        "category": category, "is_phishing": is_phishing, "sender": sender,
        "subject": subject, "body": body, "red_flags": red_flags,
    }, None


@app.route("/admin/templates", methods=["GET"])
@requires_admin
def list_templates():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM email_templates ORDER BY is_phishing DESC, category, id").fetchall()
    conn.close()
    return jsonify([template_to_dict(r) for r in rows])


@app.route("/admin/templates", methods=["POST"])
@requires_admin
def create_template():
    clean, error = parse_template_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify({"status": "error", "message": error}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    new_id = (cursor.execute("SELECT COALESCE(MAX(id), 0) FROM email_templates").fetchone()[0]) + 1
    cursor.execute("""
        INSERT INTO email_templates (id, category, is_phishing, sender, subject, body, red_flags, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    """, (new_id, clean["category"], clean["is_phishing"], clean["sender"], clean["subject"], clean["body"], clean["red_flags"]))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"Đã thêm kịch bản #{new_id}.", "id": new_id})


@app.route("/admin/templates/<int:template_id>", methods=["PUT"])
@requires_admin
def update_template(template_id):
    clean, error = parse_template_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify({"status": "error", "message": error}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    exists = cursor.execute("SELECT 1 FROM email_templates WHERE id = ?", (template_id,)).fetchone()
    if not exists:
        conn.close()
        return jsonify({"status": "error", "message": "Không tìm thấy kịch bản này."}), 404
    cursor.execute("""
        UPDATE email_templates
        SET category = ?, is_phishing = ?, sender = ?, subject = ?, body = ?, red_flags = ?
        WHERE id = ?
    """, (clean["category"], clean["is_phishing"], clean["sender"], clean["subject"], clean["body"], clean["red_flags"], template_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"Đã lưu kịch bản #{template_id}."})


@app.route("/admin/templates/<int:template_id>/toggle", methods=["POST"])
@requires_admin
def toggle_template(template_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT is_active FROM email_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"status": "error", "message": "Không tìm thấy kịch bản này."}), 404
    new_state = 0 if (row["is_active"] is None or row["is_active"] == 1) else 1
    cursor.execute("UPDATE email_templates SET is_active = ? WHERE id = ?", (new_state, template_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "is_active": new_state})


# ==========================================
# 8. DRILL-DOWN NHÂN VIÊN & XUẤT DỮ LIỆU THÔ
# ==========================================
def log_status(is_phishing, reported, clicked, is_scored):
    """Trạng thái của một bức thư. Thư lừa đảo bị bấm link mà chưa report được xếp là 'clicked'."""
    if is_phishing:
        if reported:
            return "correct"
        if clicked:
            return "clicked"
        if is_scored:
            return "missed"
        return "pending"
    if reported:
        return "false_positive"
    return "legit"


DETAIL_QUERY = """
    SELECT cl.id AS log_id, cl.employee_id, cl.email_id, cl.reported, cl.clicked, cl.is_scored,
           cl.points_delta, cl.sent_at, cl.reported_at, cl.clicked_at,
           e.employee_code, e.name AS employee_name,
           et.category, et.is_phishing, et.sender, et.subject
    FROM campaign_logs cl
    JOIN employees e ON e.id = cl.employee_id
    JOIN email_templates et ON et.id = cl.email_id
"""


@app.route("/admin/employee/<int:emp_id>/logs")
@requires_admin
def employee_logs(emp_id):
    conn = get_db_connection()
    emp = conn.execute("SELECT id, employee_code, name, email, score FROM employees WHERE id = ?", (emp_id,)).fetchone()
    if not emp:
        conn.close()
        return jsonify({"status": "error", "message": "Không tìm thấy nhân viên."}), 404
    rows = conn.execute(DETAIL_QUERY + " WHERE cl.employee_id = ? ORDER BY cl.id", (emp_id,)).fetchall()
    conn.close()

    logs = []
    counts = {k: 0 for k in STATUS_LABELS}
    for r in rows:
        status = log_status(r["is_phishing"], r["reported"], r["clicked"], r["is_scored"])
        counts[status] += 1
        logs.append({
            "log_id": r["log_id"],
            "subject": r["subject"],
            "sender": r["sender"],
            "category": r["category"],
            "is_phishing": int(r["is_phishing"]),
            "status": status,
            "status_label": STATUS_LABELS[status],
            "clicked": int(r["clicked"] or 0),
            "points": r["points_delta"] or 0,
        })
    return jsonify({
        "employee": dict(emp),
        "total": len(logs),
        "counts": counts,
        "labels": STATUS_LABELS,
        "logs": logs,
    })


def export_rows():
    conn = get_db_connection()
    rows = conn.execute(DETAIL_QUERY + " ORDER BY cl.id").fetchall()
    conn.close()
    header = ["log_id", "employee_code", "employee_name", "email_template_id", "category", "email_type",
              "sender", "subject", "reported", "clicked_link", "is_scored", "status", "points",
              "sent_at", "reported_at", "clicked_at"]
    data = []
    for r in rows:
        status = log_status(r["is_phishing"], r["reported"], r["clicked"], r["is_scored"])
        data.append([
            r["log_id"], r["employee_code"], r["employee_name"], r["email_id"], r["category"],
            "phishing" if r["is_phishing"] else "legit", r["sender"], r["subject"],
            int(r["reported"] or 0), int(r["clicked"] or 0), int(r["is_scored"] or 0),
            STATUS_LABELS[status], r["points_delta"] or 0,
            r["sent_at"] or "", r["reported_at"] or "", r["clicked_at"] or "",
        ])
    return header, data


def safe_cell(value):
    """Chặn công thức độc hại khi mở CSV/Excel (thư lừa đảo có thể bắt đầu bằng = + - @)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@app.route("/admin/export.csv")
@requires_admin
def export_csv():
    header, data = export_rows()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in data:
        writer.writerow([safe_cell(c) for c in row])
    # utf-8-sig để Excel hiển thị đúng tiếng Việt
    content = "﻿" + buf.getvalue()
    filename = f"campaign_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(content, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/admin/export.xlsx")
@requires_admin
def export_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font
    header, data = export_rows()
    wb = Workbook()
    ws = wb.active
    ws.title = "campaign_logs"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in data:
        ws.append([safe_cell(c) for c in row])
    ws.freeze_panes = "A2"
    for col, width in zip("ABCDEFGHIJKLMNOP", [8, 12, 26, 10, 26, 10, 36, 44, 10, 12, 10, 20, 8, 20, 20, 20]):
        ws.column_dimensions[col].width = width
    out = io.BytesIO()
    wb.save(out)
    filename = f"campaign_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(out.getvalue(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


# ==========================================
# 9. ROUTES HIỂN THỊ 2 TRANG RIÊNG BIỆT
# ==========================================
@app.route("/")
@app.route("/portal")
def employee_portal():
    conn = get_db_connection()
    employees = conn.execute("SELECT id, employee_code, name, email, webmail_port FROM employees").fetchall()
    conn.close()
    return render_template("portal.html", employees=employees)


@app.route("/admin")
@requires_admin
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cfg = get_settings(cursor)

    # 1. Bảng xếp hạng nhân viên (từ cao xuống thấp)
    leaderboard = cursor.execute("""
        SELECT
            e.id, e.employee_code, e.name, e.email, e.webmail_port, e.score,
            SUM(CASE WHEN et.is_phishing = 1 THEN 1 ELSE 0 END) as total_phishing_received,
            SUM(CASE WHEN et.is_phishing = 1 AND cl.reported = 1 THEN 1 ELSE 0 END) as correct_reports,
            SUM(CASE WHEN et.is_phishing = 1 AND cl.reported = 0 AND cl.is_scored = 1 THEN 1 ELSE 0 END) as missed_phishing,
            SUM(CASE WHEN et.is_phishing = 0 AND cl.reported = 1 THEN 1 ELSE 0 END) as false_reports,
            SUM(CASE WHEN et.is_phishing = 1 AND cl.clicked = 1 THEN 1 ELSE 0 END) as clicked_links
        FROM employees e
        LEFT JOIN campaign_logs cl ON e.id = cl.employee_id
        LEFT JOIN email_templates et ON cl.email_id = et.id
        GROUP BY e.id
        ORDER BY e.score DESC
    """).fetchall()

    # 2. Thống kê theo loại kịch bản lừa đảo cho biểu đồ
    chart_stats_rows = cursor.execute("""
        SELECT
            et.category,
            SUM(CASE WHEN cl.reported = 1 THEN 1 ELSE 0 END) as reported_count,
            SUM(CASE WHEN cl.reported = 0 AND cl.is_scored = 1 THEN 1 ELSE 0 END) as missed_count
        FROM campaign_logs cl
        JOIN email_templates et ON cl.email_id = et.id
        WHERE et.is_phishing = 1
        GROUP BY et.category
    """).fetchall()
    chart_stats = [dict(row) for row in chart_stats_rows]

    # 3. Trạng thái kết thúc chiến dịch và số nhân viên tham gia
    log_summary = cursor.execute("""
        SELECT
            COUNT(*) as total_logs,
            SUM(CASE WHEN is_scored = 0 THEN 1 ELSE 0 END) as unscored_logs,
            COUNT(DISTINCT employee_id) as participating_employees
        FROM campaign_logs
    """).fetchone()

    is_finalized = (log_summary["total_logs"] > 0 and log_summary["unscored_logs"] == 0)
    participating_count = log_summary["participating_employees"] or 0
    has_logs = log_summary["total_logs"] > 0

    # 4. Nhân viên điểm cao nhất & thấp nhất (xử lý cả đồng điểm)
    highest_emps = []
    lowest_emps = []
    if leaderboard:
        max_score = leaderboard[0]["score"]
        min_score = leaderboard[-1]["score"]
        highest_emps = [dict(emp) for emp in leaderboard if emp["score"] == max_score]
        lowest_emps = [dict(emp) for emp in leaderboard if emp["score"] == min_score]

    # 5. Loại mail lừa đảo được Report nhiều nhất & Bỏ sót nhiều nhất
    most_reported_cats = []
    most_missed_cats = []
    if chart_stats:
        max_rep = max(item["reported_count"] for item in chart_stats)
        max_mis = max(item["missed_count"] for item in chart_stats)
        if max_rep > 0:
            most_reported_cats = [item for item in chart_stats if item["reported_count"] == max_rep]
        if max_mis > 0:
            most_missed_cats = [item for item in chart_stats if item["missed_count"] == max_mis]
    conn.close()
    return render_template(
        "admin.html",
        leaderboard=leaderboard,
        chart_stats=chart_stats,
        is_finalized=is_finalized,
        has_logs=has_logs,
        participating_count=participating_count,
        highest_emps=highest_emps,
        lowest_emps=lowest_emps,
        most_reported_cats=most_reported_cats,
        most_missed_cats=most_missed_cats,
        cfg=cfg
    )


# Khởi tạo DB cả khi chạy bằng `flask run` hoặc gunicorn, không chỉ `python app.py`
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
