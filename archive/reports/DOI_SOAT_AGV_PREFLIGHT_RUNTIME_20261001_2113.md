# Đối soát offline 01/10/2026 21:13 Asia/Bangkok

Source collector926ca87cf9a4194150916e9160379b2add08fc0bfb7dd3bf2cb6a87e15168e46 / runtime d44bae5bb04027b49a4989c83213c1ab5d4c34c500c8a19753478922cd1d1cf6 / gate6f4a2106622e99fe60212199b621cdcbbd2a76b2e639519796b15d5a703e3d1d stable trước/sau. Parent Python3.12.10: CLI mock150mẫu/3.078s exit0, collector suite11/11 exit0, fullslice4/4 exit0. Evidence independent_preflight_suite_2111.json. C1gap/C2corrupt/C3durationâm và S1freshD0adapter tới gate/public đã khớp kỳ vọng giới hạn; không hardwareapproval.

Evidence source QA review_preflight_runtime_2112.py/.json không sửa annotation/source, chỉ fakeclock/fakeSerial. C4 NaN gap/age cho30burst rồi mấtdata15s vẫnPASS. C5 fakeOPEN2s/READ.6s với walltimeout.1s min=max1 vẫnPASS, elapsed.6 total2.6; OPEN nằm ngoài budget và chỉ kiểm deadline trướcread. P1 actualconstructor gateprotocol qua mộtadapter: D0→ARMrequest→ACK→ARMED nhưng ACK rejected, gateACKFalse/latchTrue. Telemetry numericguard chạy trướcgate nên bỏACK. Các fixture này FAIL yêu cầu, exit0harness chỉ tái hiện xong. Không mở port thật.

Collector còn thiếu wholeCLI TXspy/portexclusive/unique rawrx-processing timestamps/settling có khoảng quan sát tối thiểu và bounds mọi tham số. Mock50Hz150mẫu3s không chứng minh quan sát10–15s ngoài sàn. Runtime typedROSclock/TF/sourceenvelope/main/executor/STOPtimeout-cleanup còn pending; toàn phòng/map/homeheading chưa nghiệm thu. HardwareLIVE UNKNOWN sau reboot, không DISARMED chỉ từ report.

Giải thích Tuple phải theo interpreter: parent3.12.10/broker3.14.7, fixture annotation2101 đã chứng minh khác biệt; lời giải thích interactivekernel giữfutureflag chưa có chứng cứ. Lỗi8/8 không tái hiện3.12 không đủ kết luận fake trên3.14. Snapshot đã importTuple nên lỗi tương thích cụ thể được sửa.

Review2113 ĐÃ GỬI broker duy nhất: UI DeliverySent9:14PM/composerempty. Chưa processedACK, không gửi lại. Không Serial thật/nạp/ARM/run2/logger/startROS Pi/gain.
