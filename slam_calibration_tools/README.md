# HƯỚNG DẪN BỘ CÔNG CỤ HIỆU CHUẨN GÓC QUAY & TỐI ƯU SLAM (CÁCH LY)

> **Mục tiêu**: Khắc phục triệt để hiện tượng bản đồ SLAM bị méo hình cánh quạt ("tường ma") khi xe AGV xoay đầu, mà **không làm thay đổi hay gián đoạn mã nguồn hiện tại của dự án**.

---

## 1. Danh mục các file trong thư mục `slam_calibration_tools/`

| Tên file | Chức năng | An toàn / Cách ly |
| :--- | :--- | :--- |
| `slam_tuned.yaml` | Cấu hình SLAM Toolbox tối ưu: Mở rộng vùng tìm kiếm góc từ 20° lên 40°, giảm phạt góc sai số Odometry từ 1.0 xuống 0.18 để tia LiDAR tự khóa góc vuông tường. | Độc lập, không sửa đè lên `slam_scan_fix.yaml`. |
| `run_slam_tuned.sh` | Script kích hoạt node SLAM với cấu hình mới trên Raspberry Pi. Có cờ `--rollback` để quay lại cấu hình cũ ngay lập tức. | Giữ nguyên các node LiDAR, Unified Brain và Web UI 8080. |
| `auto_angular_calibrator.py` | Công cụ tự động đo sai số trượt bánh xe: Dùng thuật toán so khớp tia LiDAR (Scan Correlation) để đo góc quay vật lý thực tế đối chiếu với số xung Encoder. | Chỉ lắng nghe topic `/scan` và `/tf`, không can thiệp lệnh chạy xe. |
| `calibration_report.json` | Kết quả đo và hệ số bù đề xuất sẽ được lưu tự động sau khi chạy calibrator. | File sinh ra sau khi đo. |

---

## 2. Các bước thử nghiệm an toàn trên Raspberry Pi

### Bước 1: Đồng bộ thư mục `slam_calibration_tools` lên Pi
Từ máy tính phát triển, bạn chạy lệnh rsync/scp để chuyển thư mục này sang Raspberry Pi:
```bash
scp -r slam_calibration_tools khangho@100.90.252.15:/home/khangho/
```

### Bước 2: Thử nghiệm cấu hình SLAM tối ưu (Cách 1 - Nhanh nhất)
1. Đăng nhập vào Pi:
   ```bash
   ssh khangho@100.90.252.15
   cd /home/khangho/slam_calibration_tools
   chmod +x run_slam_tuned.sh auto_angular_calibrator.py
   ```
2. Khởi chạy cấu hình SLAM tối ưu mới:
   ```bash
   ./run_slam_tuned.sh --start
   ```
3. Mở trình duyệt vào Dashboard Web UI (`http://100.90.252.15:8080`):
   - Nhấn nút cho xe quay tại chỗ hoặc lái xe qua lại vài góc cua.
   - **Quan sát bản đồ**: Các góc tường phòng sẽ giữ nguyên vuông vức 90°, không bị vặn vẹo hay sinh ra tường ma xoay chéo.

4. **Nếu muốn khôi phục về trạng thái cũ bất cứ lúc nào**:
   ```bash
   ./run_slam_tuned.sh --rollback
   ```

---

### Bước 3: Tự động đo hệ số sai lệch bánh xe (Cách 2 - Auto Calibration)
Nếu bạn muốn biết chính xác bánh xe bị trượt bao nhiêu phần trăm hoặc khoảng cách 2 bánh xe ($L$) thực tế là bao nhiêu mm:

1. Chạy công cụ đo:
   ```bash
   python3 auto_angular_calibrator.py
   ```
2. Dùng Web UI điều khiển xe quay 1 vòng ($360^\circ$) tại chỗ.
3. Khi xe quay đủ 1 vòng, nhấn `Ctrl+C`. Màn hình sẽ xuất bảng báo cáo:
   ```text
   1. Tổng góc Encoder (Odom) đếm được : +342.10 độ
   2. Tổng góc LiDAR (Thực tế không trượt): +360.00 độ
   3. Sai lệch phần trăm                :   5.23 %
   4. Hệ số bù góc (Scale Factor K)     :  1.0523
   -----------------------------------------------------------------
   [*] Chiều rộng 2 bánh hiện tại        : 192.50 mm
   [>] Chiều rộng 2 bánh HIỆU CHUẨN ĐỀ XUẤT: 182.93 mm
   ```
4. Báo cáo tự động lưu vào file `calibration_report.json`.

---

## 3. Vì sao phương pháp này giải quyết được vấn đề?

* **Vấn đề cốt lõi:** Bánh cao su xoay tại chỗ trên sàn nhà luôn có độ trượt ngang (wheel scrubbing/slip). Khi bánh trượt, Encoder báo xe đã quay $360^\circ$ nhưng thực tế xe mới quay $340^\circ$.
* **Cấu hình cũ (`slam_scan_fix.yaml`):** Đặt `angle_variance_penalty: 1.0` (quá tin Odometry) và `coarse_search_angle_offset: 0.349` (chỉ tìm trong phạm vi 20°). Khi trượt quá 20°, SLAM bỏ cuộc và tưởng đây là một căn phòng mới bị xoay lệch $\rightarrow$ vẽ đè tường ma.
* **Cấu hình mới (`slam_tuned.yaml`):** Mở rộng cửa sổ tìm kiếm lên 40° và hạ mức phạt góc xuống 0.18. Thuật toán Ceres Solver nhận ra các tia LiDAR trùng với bức tường cũ nên **tự động bẻ góc bản đồ về vuông vức**, triệt tiêu hoàn toàn sai số của bánh xe.
