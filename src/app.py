import os
import re
import json
import random
import sqlite3
import smtplib
from email.message import EmailMessage
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
DB_NAME = "phishing_system.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

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
                    INSERT INTO email_templates (id, category, is_phishing, sender, subject, body, red_flags)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
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

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
            server.send_message(msg)
    except Exception as e:
        print(f"[LỖI SMTP] Không gửi được tới {smtp_host}:{smtp_port} - {e}")

# ==========================================
# 2. LUỒNG PHÁT ĐỘNG CHIẾN DỊCH (SPEAR PHISHING - 12 MAIL / NHÂN VIÊN)
# ==========================================
@app.route("/start-campaign", methods=["POST"])
def start_campaign():
    # Tên danh mục đã được khớp chính xác 100% với file emails.json
    DEPT_PRIORITY = {
        "EMP01": ["Hóa đơn, thuế", "Giả mạo sếp", "Ngân hàng"],                 # Kế toán
        "EMP02": ["Nhân sự, lương thưởng", "Giả mạo sếp"],                      # Nhân sự
        "EMP03": ["IT Support", "Cảnh báo bảo mật tài khoản"],                  # IT/Dev
        "EMP04": ["Hợp đồng, đối tác giả", "Chia sẻ tài liệu giả", "Giao hàng, bưu kiện"]  # Kinh doanh
    }

    SPEAR_COUNT = 5
    OTHER_PHISHING_COUNT = 3
    LEGIT_COUNT = 4

    conn = get_db_connection()
    cursor = conn.cursor()

    employees = cursor.execute("SELECT * FROM employees").fetchall()
    all_emails = cursor.execute("SELECT * FROM email_templates").fetchall()

    phishing_by_cat = {}
    legit_emails = []

    for mail in all_emails:
        if mail["is_phishing"] == 1:
            cat = mail["category"]
            phishing_by_cat.setdefault(cat, []).append(mail)
        else:
            legit_emails.append(mail)

    total_sent_per_emp = 0

    for emp in employees:
        selected_emails = []
        emp_code = emp["employee_code"].upper()
        priority_cats = DEPT_PRIORITY.get(emp_code, [])

        # 1. Chọn 5 mail Spear Phishing từ các danh mục trọng tâm của phòng ban
        spear_pool = [
            m for cat in priority_cats
            if cat in phishing_by_cat
            for m in phishing_by_cat[cat]
        ]
        if spear_pool:
            if len(spear_pool) >= SPEAR_COUNT:
                selected_emails.extend(random.sample(spear_pool, SPEAR_COUNT))
            else:
                selected_emails.extend(spear_pool)
                selected_emails.extend(random.choices(spear_pool, k=SPEAR_COUNT - len(spear_pool)))

        # 2. Chọn 3 mail Phishing đại trà từ các danh mục lừa đảo còn lại (mỗi loại 1 mail)
        other_cats = [
            cat for cat in phishing_by_cat.keys()
            if cat not in priority_cats and phishing_by_cat[cat]
        ]
        if len(other_cats) >= OTHER_PHISHING_COUNT:
            chosen_other_cats = random.sample(other_cats, OTHER_PHISHING_COUNT)
        else:
            chosen_other_cats = other_cats

        for cat in chosen_other_cats:
            selected_emails.append(random.choice(phishing_by_cat[cat]))

        # 3. Chọn 4 mail thật (Legit) từ 20 mẫu có sẵn ("Thông báo nội bộ" & "Công việc hằng ngày")
        if legit_emails:
            if len(legit_emails) >= LEGIT_COUNT:
                selected_emails.extend(random.sample(legit_emails, LEGIT_COUNT))
            else:
                selected_emails.extend(random.choices(legit_emails, k=LEGIT_COUNT))

        random.shuffle(selected_emails)
        total_sent_per_emp = len(selected_emails)

        for mail in selected_emails:
            cursor.execute("""
                INSERT INTO campaign_logs (employee_id, email_id, reported, is_scored)
                VALUES (?, ?, 0, 0)
            """, (emp["id"], mail["id"]))
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
    return jsonify({
        "status": "success",
        "message": f"Đã phát động chiến dịch! Mỗi nhân viên nhận đủ {total_sent_per_emp} email (5 Spear Phishing + 3 Phishing khác + 4 mail thật)."
    })
# ==========================================
# 3. LUỒNG CHẤM ĐIỂM TỰ ĐỘNG & REPORT
# ==========================================
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

    log = cursor.execute("""
        SELECT cl.*, et.is_phishing, et.red_flags, et.subject, et.category
        FROM campaign_logs cl
        JOIN email_templates et ON cl.email_id = et.id
        WHERE cl.id = ?
    """, (log_id,)).fetchone()

    if not log:
        conn.close()
        return jsonify({"status": "error", "message": f"Không tìm thấy bức thư #MAIL-{log_id} trong chiến dịch!"}), 404

    if log["employee_id"] != emp["id"]:
        conn.close()
        return jsonify({"status": "warning", "message": f"Thư #MAIL-{log_id} không thuộc hộp thư của nhân viên {emp_code}!"}), 400

    if log["is_scored"] == 1:
        conn.close()
        return jsonify({"status": "warning", "message": f"Thư #MAIL-{log_id} đã được báo cáo hoặc đã chốt điểm trước đó!"}), 400

    if log["is_phishing"] == 1:
        delta = 10
        feedback_type = "correct"
        msg = f"Chính xác! Nhân viên {emp_code} được cộng +10 điểm."
    else:
        delta = -5
        feedback_type = "false_positive"
        msg = f"Nhầm lẫn! Đây là email công việc hợp lệ ({emp_code} bị trừ -5 điểm)."

    cursor.execute("UPDATE employees SET score = score + ? WHERE id = ?", (delta, emp["id"]))
    cursor.execute("UPDATE campaign_logs SET reported = 1, is_scored = 1 WHERE id = ?", (log_id,))

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

    log = cursor.execute("""
        SELECT cl.*, et.is_phishing, et.red_flags, et.subject, et.category
        FROM campaign_logs cl
        JOIN email_templates et ON cl.email_id = et.id
        WHERE cl.id = ?
    """, (log_id,)).fetchone()

    if not log:
        conn.close()
        return jsonify({"status": "error", "message": "Không tìm thấy mã thư này!"}), 404

    if log["is_scored"] == 1:
        conn.close()
        return jsonify({"status": "warning", "message": "Thư này đã được báo cáo hoặc đã chốt điểm trước đó!"}), 400

    if log["is_phishing"] == 1:
        delta = 10
        feedback_type = "correct"
        msg = "Chính xác! Bạn đã phát hiện đúng email lừa đảo (+10 điểm)."
    else:
        delta = -5
        feedback_type = "false_positive"
        msg = "Nhầm lẫn! Đây là email công việc hợp lệ (-5 điểm)."

    cursor.execute("UPDATE employees SET score = score + ? WHERE id = ?", (delta, log["employee_id"]))
    cursor.execute("UPDATE campaign_logs SET reported = 1, is_scored = 1 WHERE id = ?", (log_id,))

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

@app.route("/finalize-campaign", methods=["POST"])
def finalize_campaign():
    conn = get_db_connection()
    cursor = conn.cursor()

    missed_logs = cursor.execute("""
        SELECT cl.id, cl.employee_id
        FROM campaign_logs cl
        JOIN email_templates et ON cl.email_id = et.id
        WHERE et.is_phishing = 1 AND cl.reported = 0 AND cl.is_scored = 0
    """).fetchall()

    for item in missed_logs:
        cursor.execute("UPDATE employees SET score = score - 10 WHERE id = ?", (item["employee_id"],))
        cursor.execute("UPDATE campaign_logs SET is_scored = 1 WHERE id = ?", (item["id"],))

    cursor.execute("UPDATE campaign_logs SET is_scored = 1 WHERE is_scored = 0")

    conn.commit()
    conn.close()
    return jsonify({
        "status": "success",
        "missed_count": len(missed_logs),
        "message": f"Đã chốt chiến dịch! Phát hiện {len(missed_logs)} email lừa đảo bị bỏ sót (-10đ/mail)."
    })

@app.route("/reset", methods=["POST"])
def reset_system():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM campaign_logs")
    cursor.execute("UPDATE employees SET score = 100")
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Đã Reset toàn bộ dữ liệu và đưa điểm về 100!"})

# ==========================================
# 4. ROUTES HIỂN THỊ 2 TRANG RIÊNG BIỆT
# ==========================================
@app.route("/")
@app.route("/portal")
def employee_portal():
    conn = get_db_connection()
    employees = conn.execute("SELECT id, employee_code, name, email, webmail_port FROM employees").fetchall()
    conn.close()
    return render_template("portal.html", employees=employees)

from functools import wraps
from flask import Response

# 👉 ĐỔI TÀI KHOẢN VÀ MẬT KHẨU TẠI 2 DÒNG NÀY:
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password4admin" 

def check_admin_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

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
        return f(*args, **kwargs)
    return decorated


@app.route("/admin")
@requires_admin
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Lấy bảng xếp hạng nhân viên (đã sắp xếp từ cao xuống thấp)
    leaderboard = cursor.execute("""
        SELECT 
            e.id, e.employee_code, e.name, e.email, e.webmail_port, e.score,
            SUM(CASE WHEN et.is_phishing = 1 THEN 1 ELSE 0 END) as total_phishing_received,
            SUM(CASE WHEN et.is_phishing = 1 AND cl.reported = 1 THEN 1 ELSE 0 END) as correct_reports,
            SUM(CASE WHEN et.is_phishing = 1 AND cl.reported = 0 AND cl.is_scored = 1 THEN 1 ELSE 0 END) as missed_phishing,
            SUM(CASE WHEN et.is_phishing = 0 AND cl.reported = 1 THEN 1 ELSE 0 END) as false_reports
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

    # 3. Kiểm tra trạng thái kết thúc chiến dịch và tổng số nhân viên tham gia
    log_summary = cursor.execute("""
        SELECT 
            COUNT(*) as total_logs,
            SUM(CASE WHEN is_scored = 0 THEN 1 ELSE 0 END) as unscored_logs,
            COUNT(DISTINCT employee_id) as participating_employees
        FROM campaign_logs
    """).fetchone()

    is_finalized = (log_summary["total_logs"] > 0 and log_summary["unscored_logs"] == 0)
    participating_count = log_summary["participating_employees"] or 0

    # 4. Tìm nhân viên điểm cao nhất & thấp nhất (xử lý cả trường hợp đồng điểm)
    highest_emps = []
    lowest_emps = []
    if leaderboard:
        max_score = leaderboard[0]["score"]
        min_score = leaderboard[-1]["score"]
        highest_emps = [dict(emp) for emp in leaderboard if emp["score"] == max_score]
        lowest_emps = [dict(emp) for emp in leaderboard if emp["score"] == min_score]

    # 5. Tìm loại mail lừa đảo được Report nhiều nhất & Bỏ sót nhiều nhất
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
        participating_count=participating_count,
        highest_emps=highest_emps,
        lowest_emps=lowest_emps,
        most_reported_cats=most_reported_cats,
        most_missed_cats=most_missed_cats
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)