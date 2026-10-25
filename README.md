# Bài tập lớn nhóm 6
Phân tích 10 loại mail lừa đảo phổ biến nhất, và tạo ra một hệ thống nhằm nâng cao nhận thức về các loại mail lừa đảo cho các nhân viên trong công ty

Bước 1:
cd BTl-nhom-6/src

bước 2: chạy docker
docker-compose up -d --build

Bước 3: Truy cập các thành phần của hệ thống
Khi các container đã chạy thành công (Started), có thể mở trình duyệt và truy cập:

⚙️ Trang Quản trị viên (Admin Dashboard):

URL: http://localhost:5000/admin

Chức năng: Bấm Phát động Chiến dịch (trộn và bắn mail ngẫu nhiên qua SMTP), bấm Kết thúc & Chốt điểm (trừ điểm mail bị bỏ sót), xem Bảng xếp hạng điểm số và 2 biểu đồ cột Chart.js.

🛡️ Trang Cổng Nhân viên (Employee Submit Portal):

URL: http://localhost:5000/portal (hoặc http://localhost:5000)

Chức năng: Nhân viên mở hộp thư Mailpit của mình, đọc thư, lấy mã định danh (VD: #MAIL-5), nhập Mã ID nhân viên (VD: EMP01) và mã thư để Submit báo cáo, đồng thời nhận ngay hộp phản hồi giáo dục (Awareness Feedback) giải thích các dấu hiệu lừa đảo (red_flags).

📬 Hộp thư Mailpit của 4 nhân viên:

Nhân viên 1 (Kế toán): http://localhost:8021

Nhân viên 2 (Nhân sự): http://localhost:8022

Nhân viên 3 (IT/Dev): http://localhost:8023

Nhân viên 4 (Kinh doanh): http://localhost:8024

Tại trang quản trị admin: bấm phát động chiến dịch
- Hệ thống sẽ random gửi các phishing mail cũng như các mail thật tới các địa chị mail của từng nhân viên

tại trang empoyee portal: các nhân viên sẽ bấm report dựa trên mã thư

tại trang quản trị: theo dõi điểm của các nhân viên và dashboard


Bước 4: Tắt hệ thống khi không sử dụng
Để dừng và xóa toàn bộ các container một cách an toàn, chạy lệnh:

docker-compose down