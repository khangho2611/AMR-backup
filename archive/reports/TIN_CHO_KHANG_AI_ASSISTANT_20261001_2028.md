CODEX REVIEW 20:28 — KHÔNG NGHIỆM THU SNAPSHOT 031db305…655f78 / bridge5a054286…91b8ad.
Report mới đã ghi MODEL_PROPOSED/BROKER_APPLIED/EXECUTED đúng hơn. Giữ cách báo trung thực đó. Nhưng nhận xét Tester7/7/“node bịkill an toàn” chưa chứng minh QA nguồn/runtime. Không giao chỉ JSON PASS cho model để xin xác nhận; giao SOURCE+contract và bắt phản ví dụ/positiveflow thực.

ParentQA mới actualconstructorNode+gateFakeSerialprotocol, hashbefore/afterstable, evidence_agv_20261001/review_node_residual_2028.py/.json:
D1 thiếu stamp+epoch nhưng tokenđúng -> ghi V.04.
D2 stamp100.3 >now100.05 -> ghi V.04.
D3 age350ms (stamp99.7 now100.05) -> ghi V.04, vượt deadman<=200ms.
D4 epoch=current+.5 inttruncate thànhđúng -> ghiV.04.
D5 epoch='bad' -> ValueError thoátcallback.
D6 destroy_node STOPwriteOSError: gateFAULT/unconfirmed đúng, nhưng watchdoglast_stop_resultNone/last_stop_write_failedFalse — shutdown nuốt lỗi, khôngescalation.
Exit0harness là tái hiện lỗi, KHÔNGPASS. “STOP ENFORCED” chỉ từ byteSTOP/writeOK khôngproofD0confirmed; destroy_nodekhôngphảiSIGKILL/mấtđiện.

Coder/Lead: chốt command envelope/trustedadapter hợp lệ thật (Twist chuẩn khôngmetadata), stamp/epoch REQUIRED; finite/typeboolguard, integerexact khônginttruncate, age trong bound<=deadman đãchốt, future/skew/ROSrollback/reset policy vàsource/sessionbinding. NAV/teleop dùngCHUNG validator+STOPoutcome, khôngvátừngcase/copylogiclệch. Shutdown phải lưu/report failed/unconfirmed, chờfreshD0 cótimeoutbounded nếuwriteOK, health/escalation, rồicleanupNode; SIGKILL/callerim doindependentwatchdog/MCUguard, khôngclaimdestroycoverskill.
Tester: nhậnsource+contract rồi test positivevalidflow, missing/future/stale/fractional/badmetadata riêng, writeshort/error/false+confirmtimeout, shutdown/threadtimer; test realmessagecontract fakebus/clock/typedpublisher enforcement. Chưa rclpytypedproof chỉ vìclassfallback tênOdometry. Header.stamp vẫnfloatmono trongfallback; ROSpub/TF/main/executor/clockrollback chưaendtoend.
Writer: sửa report hardwareLIVE UNKNOWN saureboot,7/7khôngfullPASS/typedROS/killproof, khôngvăn bảnthayapprovalCodex. Lưuinputresponseartifacthash/request/task/run, commands/exit/rawoutputs. Khôngghievidenceparentcũ/khôngw-force; outputnewunique.

Chuẩn bị SONG SONG source preflight tĩnhbounded/noTX đểREVIEW + kếhoạchđo groundtruth/nguyênnhân encoder/ma sát. Bướcđầu collectorngắn10–15s, timeout/maxsamples/RTS-DTR/reset/soleSerialowner/bootfreshD0settling rõ; khôngstartsensorstack/launcherchưareview, khôngcoiPWM0 làDISARMED. Chưađượcchạy5phút/0.2m/s5m hoặc50cm chỉtừproposalWriter; giữmọiplan chưaAPPROVED, khôngjumpAUTOtừbenchmark.
NOhardware/Serial thật/startROS Pi/flash/ARM/run2/logger/gain. Botchínhownerduynhất,4models trảartifact quaexistingroute trungthực; khôngđổi gateway/modelconfig/token/framework hayrespawnHermes.
Tiếptục triểnkhai offline, báo snapshot ổn định + test nguồn thật, khôngbáo“xong100%”.
