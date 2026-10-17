# THƯ MỤC NHẬT KÝ HUẤN LUYỆN (LOGS)

Thư mục này lưu trữ các sự kiện TensorBoard và file nhật ký CSV đo đạc quá trình hội tụ:

## Cách theo dõi đồ thị trực tiếp bằng TensorBoard:
Chạy lệnh sau tại thư mục gốc của dự án:
```bash
tensorboard --logdir=ai_local_planner/logs --port=6006
```
Sau đó mở trình duyệt tại: `http://localhost:6006`

## Các chỉ số chính cần theo dõi:
1. `charts/episodic_return`: Tổng phần thưởng mỗi episode (cần tăng dần và ổn định).
2. `charts/success_rate`: Tỷ lệ về đích thành công trong 100 episodes gần nhất (mục tiêu $\ge 95\%$).
3. `losses/policy_loss`: Hàm mất mát của Actor policy.
4. `losses/value_loss`: Hàm mất mát dự đoán của Critic (đánh giá giá trị trạng thái).
5. `losses/entropy`: Độ đa dạng hành vi (giảm từ từ để hội tụ chính sách tối ưu).
