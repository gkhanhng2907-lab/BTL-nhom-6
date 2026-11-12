# Changelog

## [Chưa phát hành]

### Added
- Admin: Trình tạo kịch bản (Template Editor) để thêm, sửa, bật/tắt mẫu thư ngay trên giao diện.
- Admin: hộp thoại cấu hình chiến dịch (SPEAR_COUNT, OTHER_PHISHING_COUNT, LEGIT_COUNT, mức điểm).
- Admin: xem chi tiết từng nhân viên (drill-down) kèm trạng thái từng thư.
- Theo dõi lượt bấm link trong thư giả lập qua `/click/<mã thư>`.
- Admin: xuất toàn bộ `campaign_logs` ra CSV và Excel.
- Chế độ tối cho trang Admin và Cổng Nhân viên.

### Changed
- Các route ghi dữ liệu của Admin (`/start-campaign`, `/finalize-campaign`, `/reset`) yêu cầu đăng nhập.
- Thư được chọn không trùng lặp khi kho kịch bản nhỏ hơn số thư yêu cầu.
- Tự động nâng cấp database cũ, thêm `openpyxl` vào requirements.
