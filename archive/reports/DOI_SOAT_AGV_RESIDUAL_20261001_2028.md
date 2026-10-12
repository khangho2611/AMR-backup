# Đối soát snapshot Node — 01/10/2026, 20:28

Chỉ offline source/FakeSerial. Runtime031db305…655f78, bridge5a054286…91b8ad trước/sau stable, hash đầy đủ trong evidence. Report bot đã minh bạch model đề xuất/broker apply và chạy công cụ hơn trước; chưa chứng minh bốn autonomous workers hoặc full runtime acceptance.

`evidence_agv_20261001/review_node_residual_2028.py/.json` dùng constructor Node thật trong môi trường offline, actualgate protocol D0/ARM/ACK/freshARMED với FakeSerial:

| Case | Kết quả |
|---|---|
| D1 | Thiếu stamp/epoch, token đúng: vẫn ghi V.04 |
| D2 | Stamp tương lai100.3, now100.05: vẫn ghi V.04 |
| D3 | Command age350ms: vẫn ghi V.04, quá bound deadman200ms |
| D4 | Epoch current+.5 bị inttruncate và accepted |
| D5 | Epoch bad gây ValueError thoát callback |
| D6 | Shutdown STOPwritefail: gateFAULT/unconfirmed nhưng public watchdog outcomeNone/failedFalse |

Không chạy suite nguồn không đổi. Exit0 harness là tái hiện đủ, không productPASS. Không phát lệnh phần cứng.

Những sửa lô trước có thật: header bắt buộc, parse lỗi scan bị chặn, whitelist frame, clock offset cho fixtureepoch, shutdown gửi STOP. Nhưng metadata command còn optional/future không chặn, tuổi lệnh cho500ms, epoch ép int, shutdown nuốt failure. Whitelist không chứng minh TF hiện hành. Fallback message có tênOdometry/TransformStamped và stampfloatmono không chứng minh typed rclpy/HeaderTime hoặc TF runtime.

Tool8159 model nhận xét từ kết quả7case rồi tuyên bố an toàn khi kill; cần source/contract, test independent và phân biệt destroy_node với SIGKILL/mất nguồn. STOP byte/writeOK chưa freshD0confirmed. Report vẫn nói hardwareDISARMED sau reboot mà chưaliveproof.

Giao broker dùng bốn model cho artifact source-linked, chungvalidator/envelope/trustedadapter cho NAV/teleop và STOPoutcome lifecycle. QA requiredmissing/future/stale/fractional/corruptmetadata, positivevalidflow, failed/shortwrite vàD0timeout, clocks/ROSmessagecontract/fakebus/threadtimer. Mỗi model đề xuất thì ghi đúng MODEL_PROPOSED/BROKER_APPLIED/BROKER_EXECUTED.

Chuẩn bị collector preflight tĩnh ngắn10–15s bounded/noTX source để review; chưa chạy thật. Kế hoạch300s/0.2m/s5m hoặc50cm vẫn proposal, khôngapproved. Giữ firmware/supervisorcũ, nohardware/ARM/flash/run2/logger/gain. Nguyên văn giao việc TIN_CHO_KHANG_AI_ASSISTANT_20261001_2028.md, Sent ghi riêng ledger sau UI xác nhận.
