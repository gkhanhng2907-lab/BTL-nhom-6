# 🛡️ Phishing Simulation & Awareness System

Hệ thống diễn tập và đào tạo nhận thức An toàn thông tin nội bộ doanh nghiệp (**Phishing Simulation & Awareness System**). Hệ thống giúp giả lập các chiến dịch email lừa đảo trong môi trường cô lập bằng Docker, hỗ trợ nhân viên thực hành nhận biết và báo cáo mối đe dọa an toàn thông tin một cách an toàn.

---

## 1. 🌟 Giới Thiệu Sơ Qua Về Sản Phẩm

### 🎯 Mục đích & Tính năng nổi bật
* **Mô phỏng chiến dịch lừa đảo**: Tự động gửi ngẫu nhiên các kịch bản email lừa đảo (trà trộn cùng email thật) tới hòm thư nhân viên qua giao thức SMTP nội bộ.
* **Cổng Báo cáo & Phản hồi giáo dục**: Nhân viên nhận diện mail nghi ngờ, nhập mã thư tại Cổng Nhân viên (`/portal`) và nhận ngay điểm thưởng/trừ kèm giải thích dấu hiệu nhận biết (`red_flags`).
* **Bảng điều khiển Quản trị (Admin Dashboard)**: Cho phép Quản trị viên khởi chạy chiến dịch, kết thúc/chốt điểm, xem bảng xếp hạng thứ hạng nhân viên và theo dõi biểu đồ thống kê Chart.js.
* **Xuất báo cáo PDF**: Tổng kết kết quả chiến dịch diễn tập dưới dạng tệp PDF trực quan (`/export-pdf`).
* **Môi trường cô lập an toàn 100%**: Đóng gói hoàn toàn bằng Docker Compose trong mạng ảo Bridge nội bộ, tuyệt đối không gửi email ra Internet hay Gmail thực tế.

### 🛠️ Công nghệ sử dụng
* **Backend**: Python 3.9+, Flask 3.0.0, SQLite3 (`phishing_system.db`), `fpdf2`.
* **Frontend**: HTML5, Bootstrap 5, Chart.js.
* **Hạ tầng & Mail Server**: Docker, Docker Compose, Mailpit (`axllent/mailpit`).

---

## 2. 🚀 Hướng Dẫn Cách Chạy Bài Lab (Quickstart)

### 📋 Yêu cầu tiên quyết
* Máy tính đã cài đặt và đang mở phần mềm **Docker Desktop**.

---

### 🏃‍♂️ Bước 1: Khởi chạy hệ thống

Khởi chạy nhanh hệ thống bằng tệp script tự động hóa tại thư mục gốc của dự án:

#### 🔹 Trên Windows:
Nhấp đúp chuột vào file **`start.bat`** (hoặc mở Terminal CMD/PowerShell tại thư mục gốc và gõ `.\start.bat`).

#### 🔹 Trên macOS / Linux:
Mở Terminal tại thư mục gốc và chạy lệnh:
```bash
chmod +x start.sh end.sh
./start.sh
```

> 💡 **Lưu ý:** Script sẽ tự động gọi Docker Compose để xây dựng 5 container ngầm, sau đó tự động mở trình duyệt web lên các trang giao diện tương ứng.

---

### 🌐 Bước 2: Các đường dẫn truy cập Web

| Thành phần giao diện | Địa chỉ URL trên trình duyệt | Chức năng chính |
| :--- | :--- | :--- |
| **Admin Dashboard** | `http://localhost:5000/admin` | Phát động/chốt chiến dịch, xem bảng xếp hạng & biểu đồ |
| **Cổng Nhân viên** | `http://localhost:5000/portal` | Nhân viên đăng ký/nhập mã NV và gửi báo cáo email lừa đảo |
| **WebMail NV 1 (Kế toán)** | `http://localhost:8021` | Xem hòm thư diễn tập của Nhân viên 1 |
| **WebMail NV 2 (Nhân sự)** | `http://localhost:8022` | Xem hòm thư diễn tập của Nhân viên 2 |
| **WebMail NV 3 (IT/Dev)** | `http://localhost:8023` | Xem hòm thư diễn tập của Nhân viên 3 |
| **WebMail NV 4 (Kinh doanh)** | `http://localhost:8024` | Xem hòm thư diễn tập của Nhân viên 4 |

---

### 🔄 Bước 3: Quy trình Demo / Thực hành diễn tập

1. **Gửi mail diễn tập**:
   * Truy cập `http://localhost:5000/admin` và bấm nút **✉️ Gửi mail** (hoặc nhân viên vào `/portal` nhập mã `mnv...` để tự đăng ký nhận mail).
2. **Đọc mail trên Mailpit**:
   * Truy cập các hòm thư WebMail (từ `http://localhost:8021` đến `8024`) để kiểm tra email gửi đến và ghi nhớ **Mã định danh thư** (ví dụ: `#MAIL-5` hoặc `5`).
3. **Báo cáo email lừa đảo**:
   * Vào `http://localhost:5000/portal`, nhập **Mã NV** và **Mã thư**, sau đó bấm **Submit Báo Cáo**.
   * Hệ thống sẽ hiển thị kết quả cộng (+10đ) hoặc trừ điểm (-5đ) kèm giải thích chi tiết dấu hiệu lừa đảo (`red_flags`).
4. **Chốt chiến dịch & Xem thống kê**:
   * Quay lại `http://localhost:5000/admin`, bấm **🏁 Kết thúc** để chốt điểm các thư bị bỏ sót (-10đ), theo dõi Bảng xếp hạng, Biểu đồ Chart.js và bấm **📄 Xuất báo cáo PDF**.

---

### 🛑 Bước 4: Tắt và dọn dẹp hệ thống

Sau khi kết thúc bài lab / demo:

* **Trên Windows**: Nhấp đúp chuột vào file **`end.bat`** (hoặc gõ `.\end.bat`).
* **Trên macOS / Linux**: Chạy lệnh `./end.sh`.
