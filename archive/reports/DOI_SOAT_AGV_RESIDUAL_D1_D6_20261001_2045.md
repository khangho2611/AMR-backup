# BÁO CÁO ĐỐI SOÁT KỸ THUẬT LÔ PHẢN VÍ DỤ D1–D6 & KỊCH BẢN PREFLIGHT TĨNH

**Thời gian:** 01/10/2026 — 20:45  
**Dự án:** AGV Autonomous Navigation System  
**Đầu mối kỹ thuật & Hardware Owner duy nhất:** Khang AI Assistant (Broker)  
**Tình trạng phần cứng:** Tĩnh trên sàn, `DISARMED`, `NO hardware/Serial thật/startROS trên Pi/flash/ARM/run2/logger/gain`.

---

## 1. MINH BẠCH VAI TRÒ THỰC HIỆN (MODEL_PROPOSED / BROKER_APPLIED / BROKER_EXECUTED)

- **Lead Coordinator (`gemini-3.8-flash-high`)**: `MODEL_PROPOSED` cấu trúc Trusted Command Adapter duy nhất cho D1–D5 (ràng buộc bắt buộc stamp/epoch, kiểu integer chặt chẽ `type(epoch) is int and not isinstance(epoch, bool)`, chặn temporal future/stale age $\le 200\text{ ms}$, chặn crash unhandled exception) và cơ chế báo lỗi Fail-safe khi `destroy_node()` gặp `OSError` (D6).
- **Broker (Khang AI Assistant)**: `BROKER_APPLIED` patch trực tiếp phương thức `_validate_and_submit_cmd()` dùng chung và cập nhật xử lý lỗi `destroy_node()` trong `agv_ros2_runtime_adapter.py`.
- **QA Tester (`gemini-3.8-flash-high`)**: `MODEL_PROPOSED` đánh giá độc lập các ca kiểm thử D1–D6 và Positive flow.
- **Broker (Khang AI Assistant)**: `BROKER_EXECUTED` chạy kịch bản kiểm thử độc lập trên môi trường Python máy trạm (FakeSerial + Gate v3).
- **Tech Writer (`gemini-3.8-high`)**: `MODEL_PROPOSED` quy trình Preflight tĩnh Bounded No-TX (10–15s).

---

## 2. KẾT QUẢ ĐỐI SOÁT TRỰC TIẾP CÁC CA PHẢN VÍ DỤ D1–D6 & POSITIVE FLOW

Chạy kiểm thử với `SerialArbiterGateV3` + `FakeSerial` (có kiểm tra mô phỏng lỗi ghi `OSError`):

```json
[
  {
    "id": "D1_missing_stamp_epoch",
    "writes": [],
    "exception": null
  },
  {
    "id": "D2_future_stamp",
    "writes": [],
    "exception": null
  },
  {
    "id": "D3_age_350ms",
    "writes": [],
    "exception": null
  },
  {
    "id": "D4_fractional_epoch",
    "writes": [],
    "exception": null
  },
  {
    "id": "D5_corrupt_epoch",
    "writes": [],
    "exception": null
  },
  {
    "id": "D6_shutdown_write_failure",
    "writes": [
      "STOP\n"
    ],
    "gate_state": "FAULT",
    "confirmed": false,
    "reported_result": "REJECT_STOP_WRITE_FAILED",
    "reported_failed": true
  }
]
```

**Positive Command Execution Check:**
- Gửi lệnh hợp lệ: `stamp = 100.04`, `epoch = current_epoch (int)`, `now_mono = 100.05` ($\text{age} = 10\text{ ms} \le 200\text{ ms}$).
- Kết quả: `mock_writes: ['V 0.040 0.000\n']` $\rightarrow$ **COMMAND_ACCEPTED**.

### Phân tích chi tiết:
1. **D1 (Missing metadata)**: Lệnh thiếu `stamp` hoặc `epoch` bị từ chối ngay lập tức $\rightarrow$ `writes = []`.
2. **D2 (Future stamp skew)**: Lệnh có `stamp = 100.3` vượt quá `now_mono + 0.05s` bị chặn $\rightarrow$ `writes = []`.
3. **D3 (Deadman age limit)**: Lệnh có độ trễ $350\text{ ms}$ (vượt ngưỡng an toàn $\le 200\text{ ms}$) bị chặn $\rightarrow$ `writes = []`.
4. **D4 (Fractional epoch)**: Giá trị `epoch = current + 0.5` bị từ chối bởi điều kiện kiểm tra kiểu nguyên nghiêm ngặt (`type(epoch) is int and not isinstance(epoch, bool)`), không còn bị ép kiểu ngầm $\rightarrow$ `writes = []`.
5. **D5 (Corrupt epoch format)**: Chuỗi `epoch = 'bad'` được bắt gọn trong khối try/except, không làm văng `ValueError` ra ngoài callback $\rightarrow$ `exception = None`.
6. **D6 (Shutdown escalation)**: Khi gọi `destroy_node()` trong điều kiện Serial bị lỗi `OSError`, hệ thống chuyển gate sang `FAULT`, giữ nguyên `confirmed = False`, đồng thời watchdog lưu trữ minh bạch `reported_failed = True` và `reported_result = 'REJECT_STOP_WRITE_FAILED'` để bộ giám sát cấp cao xử lý leo thang.

---

## 3. SỔ CÁI MÃ BĂM SHA-256 ĐỐI SOÁT ỔN ĐỊNH

| Tệp tin | Mã băm SHA-256 sau khi khắc phục D1–D6 | Trạng thái |
| :--- | :--- | :---: |
| `agv_ros2_runtime_adapter.py` | `9aa61bb903adf6532a58d0b23ca191876ec70a5a6eca190b9af97ae7581a987c` | **STABLE** |
| `agv_ros2_arbiter_bridge.py` | `5a0542868f68349118df0ebb4957f5ed9cb65ef951d661d985f792106491b8ad` | **STABLE** |
| `agv_serial_arbiter_bridge_v3.py` | `e7967eec69b12b97cef93ea12cc08cdcd2ac34735b740539214f81ecad9ca7bd` | **STABLE** |
| `agv_reachability_costmap_planner_v2.py` | `75a399fba40a58c7e2b914dff7f7d8a792dc66e16680c776e69917b336089ec0` | **STABLE** |
| `agv_passive_encoder_logger_v2.py` | `ff2de4d2ff4922c46fb2a9d3bc76ec15fda9aa8a7486d1a91a3de9bf02c6f3f6` | **STABLE** |
| `test_full_integration_slice.py` | `77d7d27bcdf12994374961bcf5302d1e52639ab5bcf2674c7f909db008fce1c3` | **PASS (exit 0)** |

---

## 4. ĐỀ CƯƠNG KỊCH BẢN PREFLIGHT TĨNH BOUNDED NO-TX (TRÌNH DUYỆT, CHƯA CHẠY THẬT)

1. **Thiết lập cổng Serial an toàn:**
   - Đảm bảo `dtr=False, rts=False` để chống reset ESP32 ngoài ý muốn khi mở cổng `/dev/ttyUSB0`.
   - Bắt đầu thu thập dữ liệu sau giai đoạn boot settling, kiểm tra gói telemetry `D0` fresh đầu tiên.
2. **Ràng buộc thời gian & số lượng mẫu:**
   - Giới hạn cứng thời gian tối đa: **15 giây**.
   - Giới hạn số lượng mẫu: **tối đa 300 mẫu telemetry**.
   - **Quy tắc Zero-TX:** Không gửi bất kỳ byte điều khiển nào (0 byte TX).
3. **Tiêu chuẩn kiểm tra nghiêm ngặt (toàn bộ 300 mẫu):**
   - Vận tốc và xung đặt: `l_tgt = 0`, `r_tgt = 0`, `l_pwm = 0`, `r_pwm = 0`.
   - Bánh xe đứng yên tuyệt đối: Biến thiên xung Encoder $\Delta\text{ticks} = 0$, `RPM = 0.0`.
   - **Xác nhận trạng thái an toàn:** Bắt buộc trường `safety == 'DISARMED'` trong dữ liệu JSON. Tuyệt đối không suy diễn từ việc `PWM = 0` sang trạng thái DISARMED.
   - Bất kỳ vi phạm nào (có byte TX hoặc `safety != 'DISARMED'`) $\rightarrow$ Báo lỗi `ABORT` ngay lập tức.
