# Đối soát Node và chứng cứ bốn bot — 01/10/2026, 20:12

Chỉ source/fake transport, không hardware. Snapshot runtime `943f6e6d38748cf516a984fce46f8fac91e51a06c95500a162c4fd513122524f`, bridge `fa85d141da8ea7013e17ea3d24bc4e35687d69ebd8db7a6f78c9fc840d08e534`, trước/sau ổn định.

## Kết quả độc lập

Constructor offline hiện chạy được. Harness `evidence_agv_20261001/review_node_followup_2012.py`, output `review_node_followup_2012_v2.json` tái hiện:

| ID | Quan sát |
|---|---|
| Q1 | Scan fresh theo ROS clock1700000000, mono100 bị từ chối; chưa ánh xạ hai clock |
| Q2 | Có ranges/góc nhưng thiếu header vẫn accepted với stamp hiện tại |
| Q3 | Frame camera chưa TF/config vẫn accepted |
| Q4 | Header sec hỏng thoát ValueError |
| Q5 | Token đúng, stamp0/epoch-1 vẫn ghi V0.0400.000 qua FakeSerial sau protocol session |
| Q6 | Node publishers nhận dict và stamp monotonic float; chưa chứng minh typed ROS publication |
| Q7 | destroy_node khi gate mockARMED/leaseactive không gửi STOP, gate và lease còn nguyên |

Outputv1 Q5 sai vì lưu tham chiếu list rồi clear ở case sau; parent sửa harness dùng bản sao list và chạy lại vào outputv2 riêng. Bảo toàn v1, dùng v2 làm kết luận. Exit0 nghĩa hoàn tất tái hiện, không phải toàn bộ sản phẩm PASS. Không chạy lại các suite không liên quan.

## Contract cần giữ

[LaserScan.msg chính thức](https://raw.githubusercontent.com/ros2/common_interfaces/rolling/sensor_msgs/msg/LaserScan.msg) có acquisition header/time/frame và range bounds. [Twist.msg chính thức](https://raw.githubusercontent.com/ros2/common_interfaces/rolling/geometry_msgs/msg/Twist.msg) chỉ linear/angular; không có lease/session/epoch/stamp. Cần trusted adapter/envelope thực để nối authorization và source freshness, không giả định dynamic attributes trên Twist chuẩn.

## Bốn bot: phân biệt lời báo cáo và thực thi

Report7964 gán trạng thái CoderCOMPLETED/TesterVERIFIED/WriterDELIVERED. Log7970 bot tự thừa nhận tin bốn bot trước đó là text soạn sẵn và công cụ do broker thực hiện. Log7979/7981 có output gọi model gateway và gửi tin mới, nhưng nội dung mới là lời chào/nhận việc; chưa chứng minh worker thực thi patch/QA. Không kết luận toàn bộ sửa code là giả: patch và test broker thực sự tồn tại. Không suy model request alias thành chứng minh backend identity hoặc worker có tools.

Giao broker dùng route đã có: Lead trả kiến trúc/criteria, Coder trả patch, Tester trả phản ví dụ/test độc lập, Writer trả ledger/plan với hash. Nếu broker apply/run thay model, ghi rõ MODEL_PROPOSED/BROKER_APPLIED/BROKER_EXECUTED. Đòi task/run/input/outputhash/ACK thật, không lời nhận việc thay artifact. Không in hoặc tìm credential, sửa gateway/model/token hoặc dựng framework ngoài nhiệm vụ.

## Quyết định và việc tiếp

Chưa nghiệm thu Node hoặc phần cứng. Cần clock mapping, source/session/epoch/age guard, typed Odom/TF, fake bus wiring và STOP lifecycle/shutdown. Chuẩn bị boundednoTX preflight source và kế hoạch đo motion thực để review. Giữ firmware/supervisor cũ, không hardware/ARM/nạp/run2/logger/gain. Nguyên văn nhiệm vụ `TIN_GIAO_VIEC_VA_DOI_SOAT_AGV_20261001_2015.md`; Sent chỉ công nhận khi UI xác nhận.
