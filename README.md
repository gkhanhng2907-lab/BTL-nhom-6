# Phishing Simulation & Awareness System

Hệ thống diễn tập và đào tạo nhận thức An toàn thông tin nội bộ doanh nghiệp (**Phishing Simulation & Awareness System**). Hệ thống giúp giả lập các chiến dịch email lừa đảo trong môi trường cô lập bằng Docker, hỗ trợ nhân viên thực hành nhận biết và báo cáo mối đe dọa an toàn thông tin một cách an toàn.

---

## 1. Giới Thiệu Sơ Qua Về Sản Phẩm

### Mục đích & Tính năng nổi bật
* **Mô phỏng chiến dịch lừa đảo**: Tự động gửi ngẫu nhiên các kịch bản email lừa đảo (trà trộn cùng email thật) tới hòm thư nhân viên qua giao thức SMTP nội bộ.
* **Cổng Báo cáo & Phản hồi giáo dục**: Nhân viên nhận diện mail nghi ngờ, nhập mã thư tại Cổng Nhân viên (`/portal`) và nhận ngay điểm thưởng/trừ kèm giải thích dấu hiệu nhận biết (`red_flags`).
* **Bảng điều khiển Quản trị (Admin Dashboard)**: Cho phép Quản trị viên khởi chạy chiến dịch, kết thúc/chốt điểm, xem bảng xếp hạng thứ hạng nhân viên và theo dõi biểu đồ thống kê Chart.js.
* **Xuất báo cáo PDF**: Tổng kết kết quả chiến dịch diễn tập dưới dạng tệp PDF trực quan (`/export-pdf`).
* **Môi trường cô lập an toàn 100%**: Đóng gói hoàn toàn bằng Docker Compose trong mạng ảo Bridge nội bộ, tuyệt đối không gửi email ra Internet hay Gmail thực tế.

### Công nghệ sử dụng
* **Backend**: Python 3.9+, Flask 3.0.0, SQLite3 (`phishing_system.db`), `fpdf2`.
* **Frontend**: HTML5, Bootstrap 5, Chart.js.
* **Hạ tầng & Mail Server**: Docker, Docker Compose, Mailpit (`axllent/mailpit`).

---

## 2. Hướng Dẫn Cách Chạy Bài Lab (Quickstart)

### Yêu cầu tiên quyết
* Máy tính đã cài đặt và đang mở phần mềm **Docker Desktop**.

---

### Bước 1: Khởi chạy hệ thống

Khởi chạy nhanh hệ thống bằng tệp script tự động hóa tại thư mục gốc của dự án:

#### Trên Windows:
Nhấp đúp chuột vào file **`start.bat`** (hoặc mở Terminal CMD/PowerShell tại thư mục gốc và gõ `.\start.bat`).

#### Trên macOS / Linux:
Mở Terminal tại thư mục gốc và chạy lệnh:
```bash
chmod +x start.sh end.sh
./start.sh
```

> **Lưu ý:** Script sẽ tự động gọi Docker Compose để xây dựng 5 container ngầm, sau đó tự động mở trình duyệt web lên các trang giao diện tương ứng.

---

### Bước 2: Các đường dẫn truy cập Web

| Thành phần giao diện | Địa chỉ URL trên trình duyệt | Chức năng chính |
| :--- | :--- | :--- |
| **Admin Dashboard** | `http://localhost:5000/admin` | Phát động/chốt chiến dịch, xem bảng xếp hạng & biểu đồ |
| **Cổng Nhân viên** | `http://localhost:5000/portal` | Nhân viên đăng ký/nhập mã NV và gửi báo cáo email lừa đảo |
| **WebMail NV 1 (Kế toán)** | `http://localhost:8021` | Xem hòm thư diễn tập của Nhân viên 1 |
| **WebMail NV 2 (Nhân sự)** | `http://localhost:8022` | Xem hòm thư diễn tập của Nhân viên 2 |
| **WebMail NV 3 (IT/Dev)** | `http://localhost:8023` | Xem hòm thư diễn tập của Nhân viên 3 |
| **WebMail NV 4 (Kinh doanh)** | `http://localhost:8024` | Xem hòm thư diễn tập của Nhân viên 4 |

---

### Bước 3: Quy trình Demo / Thực hành diễn tập

1. **Gửi mail diễn tập**:
   * Truy cập `http://localhost:5000/admin` và bấm nút **Gửi mail** (hoặc nhân viên vào `/portal` nhập mã `mnv...` để tự đăng ký nhận mail).
2. **Đọc mail trên Mailpit**:
   * Truy cập các hòm thư WebMail (từ `http://localhost:8021` đến `8024`) để kiểm tra email gửi đến và ghi nhớ **Mã định danh thư** (ví dụ: `#MAIL-5` hoặc `5`).
3. **Báo cáo email lừa đảo**:
   * Vào `http://localhost:5000/portal`, nhập **Mã NV** và **Mã thư**, sau đó bấm **Submit Báo Cáo**.
   * Hệ thống sẽ hiển thị kết quả cộng (+10đ) hoặc trừ điểm (-5đ) kèm giải thích chi tiết dấu hiệu lừa đảo (`red_flags`).
4. **Chốt chiến dịch & Xem thống kê**:
   * Quay lại `http://localhost:5000/admin`, bấm **Kết thúc** để chốt điểm các thư bị bỏ sót (-10đ), theo dõi Bảng xếp hạng, Biểu đồ Chart.js và bấm **Xuất báo cáo PDF**.

---

### Bước 4: Tắt và dọn dẹp hệ thống

Sau khi kết thúc bài lab / demo:

* **Trên Windows**: Nhấp đúp chuột vào file **`end.bat`** (hoặc gõ `.\end.bat`).
* **Trên macOS / Linux**: Chạy lệnh `./end.sh`.

---

## 3. Theo dõi click và trang đăng nhập giả

* Link trong mail lừa đảo được đổi thành `http://localhost:5000/track-click/<log_id>` lúc gửi. Có thể đổi địa chỉ gốc bằng biến môi trường `BASE_URL`.
* Mỗi link có mã riêng `?t=<token>`. Thư cũ còn sót trong Mailpit từ chiến dịch trước sẽ bị từ chối với mã 410, không trỏ nhầm sang thư mới. Khi phát động hoặc Reset, hệ thống tự xóa hộp thư Mailpit cũ.
* Lưu ý khi demo: mọi link trong thư đều trỏ về máy chủ diễn tập (`/track-click/...`) để ghi nhận lượt bấm, nên rê chuột sẽ thấy `localhost`. Địa chỉ giả mạo thật sự là phần chữ hiển thị trong nội dung thư, và trang cảnh báo nêu lại địa chỉ đó cùng tên miền thật.
* Dòng `Đính kèm: tên_tệp` trong mail cũng là liên kết theo dõi: mở tệp được tính như bấm link và chuyển thẳng tới trang cảnh báo, không qua trang đăng nhập giả.
* Nút báo cáo trong mail (`/report-mail/<id>?t=<token>`) ghi nhận báo cáo ngay và hiện trang kết quả gồm thư thật hay giả, đúng hay sai và lời giải thích, không cần nhập mã. Mở lại nhiều lần chỉ tính điểm một lần. Cổng báo cáo `/portal` nhập mã bằng tay vẫn dùng được.
* Bấm link hoặc mở tệp: `clicked = 1`, trừ 15 điểm (chỉ trừ một lần). Thư đã bấm thì không báo cáo được nữa và không bị trừ thêm điểm bỏ sót. Ngược lại, thư đã báo cáo thì bấm link trong thư không còn bị trừ điểm.
* Chỉ thư giả danh BinGroup (giả mạo sếp, IT, nhân sự hoặc tên miền na ná bingroup) mới đưa nhân viên tới trang đăng nhập giả. Bấm Đăng nhập: `submitted_data = 1`, trừ thêm 25 điểm, tổng 40 điểm. Tài khoản và mật khẩu gõ vào không được gửi lên server và không lưu vào database.
* Thư giả danh dịch vụ hoặc công ty bên thứ ba chuyển thẳng tới trang cảnh báo sau khi bấm link, chỉ bị trừ 15 điểm.
* Mọi trường hợp đều kết thúc ở trang `/awareness/<log_id>` giải thích các dấu hiệu lừa đảo.
* Mail gửi dạng HTML, cuối thư có nút báo cáo mở thẳng `/report-mail/<id>?t=<token>`. Cổng `/portal?emp=EMP01&mail=MAIL-5` vẫn có sẵn để nhập mã bằng tay.
* Mẫu thư trong `emails.json` được đồng bộ vào cơ sở dữ liệu mỗi lần ứng dụng khởi động, nên sửa nội dung thư chỉ cần khởi động lại, không cần xóa `phishing_system.db`.
* Trường `target` trong `emails.json` giới hạn thư chỉ gửi cho nhân viên thuộc phòng ban ghi trong đó, ví dụ `EMP01` hoặc `EMP03,EMP04`. Thư không có `target` gửi được cho mọi người.
* Chuỗi `{ten}` trong nội dung thư được thay bằng tên gọi của người nhận khi gửi.
* Banner đầu thư lấy theo người gửi. Chỉ thư dùng hoặc giả tên miền BinGroup mới có banner công ty.
* Phần giải thích dấu hiệu chỉ dựa trên những gì kiểm chứng được trong thư, không giả định người nhận có đặt hàng hay chờ tài liệu nào.
