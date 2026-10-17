# THƯ MỤC MÔ HÌNH XUẤT XƯỞNG (EXPORTED ONNX)

Thư mục này chứa các file xuất xưởng cuối cùng, phục vụ việc nạp trực tiếp lên xe thật (Raspberry Pi 4):

## Các file thành phẩm:
1. `local_planner.onnx`:
   - Mô hình Actor (chính sách điều khiển suy luận xác định) được xuất sang định dạng Open Neural Network Exchange (ONNX).
   - Chuẩn Opset: 14.
   - Đầu vào: `[1, 365]` (360 tia LiDAR + khoảng cách đích + sin/cos hướng + v hiện tại + w hiện tại).
   - Đầu ra: `[1, 2]` ($[v_{cmd}, \omega_{cmd}]$).
   - Chạy trực tiếp qua `onnxruntime` trên CPU của Raspberry Pi 4 với độ trễ $< 2\text{ms}$.
2. `manifest.json`:
   - Chứa chữ ký kiểm định tính toàn vẹn (SHA-256), tỷ lệ thành công, các ngưỡng an toàn và siêu tham số phần cứng. Script điều khiển `agv_unified_brain.py` sẽ đọc file này để tự động cấu hình trước khi kích hoạt xe.
