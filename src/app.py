import os
import json
import random
import sqlite3
import smtplib
from email.message import EmailMessage
from flask import Flask, render_template, request, jsonify, redirect, url_for

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

    # Tạo bảng nhân viên (mặc định 100 điểm)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            smtp_host TEXT NOT NULL,
            smtp_port INTEGER NOT NULL,
            webmail_port INTEGER NOT NULL,
            score INTEGER DEFAULT 100
        )
    """)

    # Tạo bảng mẫu email
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

    # Tạo bảng lịch sử chiến dịch
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

    # Khởi tạo 4 nhân viên tương ứng với 4 container Mailpit
    # Lưu ý: Nếu chạy trong Docker thì smtp_host là tên container (employee-1..4), cổng 1025
    # Nếu chạy test ngoài máy thật (localhost) thì đổi qua biến môi trường USE_DOCKER
    use_docker = os.environ.get("USE_DOCKER", "1") == "1"
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0:
        default_employees = [
            ("Nhân viên 1 (Kế toán)", "nv1@company.local", "employee-1" if use_docker else "localhost", 1025 if use_docker else 1021, 8021, 100),
            ("Nhân viên 2 (Nhân sự)", "nv2@company.local", "employee-2" if use_docker else "localhost", 1025 if use_docker else 1022, 8022, 100),
            ("Nhân viên 3 (IT/Dev)", "nv3@company.local", "employee-3" if use_docker else "localhost", 1025 if use_docker else 1023, 8023, 100),
            ("Nhân viên 4 (Kinh doanh)", "nv4@company.local", "employee-4" if use_docker else "localhost", 1025 if use_docker else 1024, 8024, 100),
        ]
        cursor.executemany("""
            INSERT INTO employees (name, email, smtp_host, smtp_port, webmail_port, score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, default_employees)

    # Nạp dữ liệu từ emails.json vào bảng email_templates
    cursor.execute("SELECT COUNT(*) FROM email_templates")
    if cursor.fetchone()[0] == 0 and os.path.exists("emails.json"):
        with open("emails.json", "r", encoding="utf-8") as f:
            emails_data = json.load(f)
            for item in emails_data:
                # Nếu red_flags trong JSON là list thì nối lại thành chuỗi
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

# Hàm gửi mail qua SMTP vào hộp thư Mailpit của nhân viên
def send_smtp_email(smtp_host, smtp_port, sender, recipient, subject, body, log_id):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"[#MAIL-{log_id}] {subject}"
    
    full_body = f"Mã định danh thư: #MAIL-{log_id}\n" + "-"*40 + f"\n\n{body}"
    msg.set_content(full_body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
            server.send_message(msg)
    except Exception as e:
        print(f"[LỖI SMTP] Không gửi được tới {smtp_host}:{smtp_port} - {e}")

# ==========================================
# 2. LUỒNG PHÁT ĐỘNG CHIẾN DỊCH
# ==========================================
@app.route("/start-campaign", methods=["POST"])
def start_campaign():
    conn = get_db_connection()
    cursor = conn.cursor()

    employees = cursor.execute("SELECT * FROM employees").fetchall()
    all_emails = cursor.execute("SELECT * FROM email_templates").fetchall()

    # Số lượng thư bốc ngẫu nhiên cho mỗi nhân viên trong 1 đợt (ví dụ: 5 thư)
    emails_per_employee = min(5, len(all_emails))

    for emp in employees:
        sampled_emails = random.sample(all_emails, emails_per_employee)
        for mail in sampled_emails:
            # Lưu vào campaign_logs
            cursor.execute("""
                INSERT INTO campaign_logs (employee_id, email_id, reported, is_scored)
                VALUES (?, ?, 0, 0)
            """, (emp["id"], mail["id"]))
            log_id = cursor.lastrowid

            # Bắn email qua SMTP vào Mailpit tương ứng
            send_smtp_email(
                smtp_host=emp["smtp_host"],
                smtp_port=emp["smtp_port"],
                sender=mail["sender"],
                recipient=emp["email"],
                subject=mail["subject"],
                body=mail["body"],
                log_id=log_id
            )

    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Đã phát động chiến dịch và gửi mail thành công!"})

# ==========================================
# 3. LUỒNG CHẤM ĐIỂM TỰ ĐỘNG & REPORT
# ==========================================
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

    # Kiểm tra nhãn is_phishing để cộng/trừ điểm
    if log["is_phishing"] == 1:
        delta = 10  # Report đúng mail lừa đảo -> +10 điểm
        feedback_type = "correct"
        msg = "Chính xác! Bạn đã phát hiện đúng email lừa đảo (+10 điểm)."
    else:
        delta = -5  # Report nhầm mail thật -> -5 điểm
        feedback_type = "false_positive"
        msg = "Nhầm lẫn! Đây là email công việc hợp lệ (-5 điểm)."

    # Cập nhật điểm nhân viên và đánh dấu đã xử lý
    cursor.execute("UPDATE employees SET score = score + ? WHERE id = ?", (delta, log["employee_id"]))
    cursor.execute("UPDATE campaign_logs SET reported = 1, is_scored = 1 WHERE id = ?", (log_id,))

    conn.commit()
    conn.close()

    # Trả về thông tin kèm red_flags để Frontend của Quang hiện hộp Awareness
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

    # Quét toàn bộ thư lừa đảo (is_phishing = 1) nhưng nhân viên bỏ sót (reported = 0, is_scored = 0)
    missed_logs = cursor.execute("""
        SELECT cl.id, cl.employee_id
        FROM campaign_logs cl
        JOIN email_templates et ON cl.email_id = et.id
        WHERE et.is_phishing = 1 AND cl.reported = 0 AND cl.is_scored = 0
    """).fetchall()

    for item in missed_logs:
        # Trừ 10 điểm mỗi thư lừa đảo bị bỏ sót
        cursor.execute("UPDATE employees SET score = score - 10 WHERE id = ?", (item["employee_id"],))
        cursor.execute("UPDATE campaign_logs SET is_scored = 1 WHERE id = ?", (item["id"],))

    # Đánh dấu các mail thật chưa report là đã chốt sổ để đóng chiến dịch
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

# Trang 1: Cổng Nhân viên (Chỉ có ô nhập mã mail và nút Submit)
@app.route("/")
@app.route("/portal")
def employee_portal():
    conn = get_db_connection()
    employees = conn.execute("SELECT id, name, email, webmail_port FROM employees").fetchall()
    conn.close()
    return render_template("portal.html", employees=employees)

# Trang 2: Trang Quản trị riêng biệt (Phát động, Chốt chiến dịch, Bảng điểm & Biểu đồ)
@app.route("/admin")
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Lấy bảng xếp hạng nhân viên và thống kê chi tiết
    leaderboard = cursor.execute("""
        SELECT 
            e.id, e.name, e.email, e.webmail_port, e.score,
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

    # 2. Thống kê theo loại kịch bản (Category) cho 2 biểu đồ Chart.js
    chart_stats = cursor.execute("""
        SELECT 
            et.category,
            SUM(CASE WHEN cl.reported = 1 THEN 1 ELSE 0 END) as reported_count,
            SUM(CASE WHEN cl.reported = 0 AND cl.is_scored = 1 THEN 1 ELSE 0 END) as missed_count
        FROM campaign_logs cl
        JOIN email_templates et ON cl.email_id = et.id
        WHERE et.is_phishing = 1
        GROUP BY et.category
    """).fetchall()

    conn.close()
    return render_template(
        "admin.html",
        leaderboard=leaderboard,
        chart_stats=[dict(row) for row in chart_stats]
    )

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)