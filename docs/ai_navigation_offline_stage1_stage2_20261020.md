# AI1/AI2 - Navigation: PC integration and offline simulation (2026-10-20)

## Scope and operating boundary

Robot mechanical motion, ESP32 firmware, PID, watchdog and motor parameters were not changed by this integration task. No physical UART or ROS daemon is needed for the tests below. AI1 and AI2 default to `shadow`, while the original navigation is the authority. Neither model is approved for real robot control.

## Changes in the AI-to-navigation boundary

- AI1 now uses `v`/`w` from ESP32 D0 telemetry (with a finite-value fallback) instead of unmaintained measured-velocity attributes.
- AI1 consumes the existing local-planner runtime's filtered action, retains `(0,0)` and very low speeds, and never restores a minimum positive speed after an AI stop. Command dispatch still uses the existing guarded command path.
- In `shadow`, the AI1 prediction is recorded but not dispatched. In the explicit `control` setting, inference/dispatch failure requests HOLD and a zero command.
- AI2 produces training-shaped `(3,9,9)` / `(8,)` observations, flips ROS-grid Y into model row order and uses the first A* step, with the proper 64-step distance scale. Relative yaw and the selected action are converted through the map-origin rotation. Robot yaw from map TF is passed from the navigation loop when available.
- AI2 only ranks candidate **coverage goals**; it does not directly command motor velocity. It validates the four Q-values; invalid results fall back to nearest-first navigation. If the directionally ranked top ten have no valid route, nearest-first candidates are retried.
- `GET /api/telemetry` now exposes model mode, suggested shadow actions/goals, and inference errors. Stale AI1 predictions are cleared on the next loop without inference; AI2 predictions are cleared at the next goal search.

## Verification

Run from the repository root with a local Python environment:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python -m pytest tests/test_agv_ai_integration.py -q --disable-warnings
python -m pytest ai_local_planner/tests -q --disable-warnings
python -m pytest tests/test_coverage_v2.py -q --disable-warnings
python tests/run_agv_tests.py
python -m py_compile agv_ai_bridge.py agv_unified_brain.py tests/test_agv_ai_integration.py
git diff --check
```

AI bridge regression tests exercise mock telemetry, stop preservation, low-speed preservation, finite inputs, shadow/control separation, HOLD-on-error, AI2 coordinate transforms, four-mode synthetic drive feedback, HTTP telemetry, unreachable coverage fallback and baseline navigation dispatch. **These are software tests, not real-world navigation acceptance tests.**

Results (2026-10-20): AI bridge 29/29 PASS; AI1 113/113 PASS; AI2 22/22 PASS; AGV regression 133/135 PASS. AGV failures:

1. `test_actual_reader_http_ack_drive_stop_and_pid_real_ten_seconds`: frontier goal X=0.375 instead of >3; linked to already uncommitted frontier scoring changes.
2. `test_operational_speed_profile_cruises_at_80_rpm`: expected `V 0.307`, actual `V 0.217 0.668` with AI defaulting to shadow. The test assumes the previous AI takeover behavior, whereas conventional Navigation now remains authoritative in shadow; no motor-speed logic was changed to force this test to pass.

## Outstanding limitations / Pi admission criteria

- The coverage policy trained in a synthetic discrete 32x32 grid. Observation alignment reduces mismatch but does not validate performance or safety against real SLAM maps, moving obstacles or unreachable/unknown regions.
- The legacy global `visited_cells` mapping and coverage percentage do not consistently account for rotated map origins, inflated/unreachable area or cells outside the map. This affects both the traditional and AI2 coverage planner. A separate coordinated coverage-state fix is needed before AI2 is promoted.
- AI2 no-progress is now tracked as consecutive navigation ticks with no new visited cell. The feature is still an approximation of the discrete training environment's number of failed coverage steps.
- Four-mode testing uses synthetic, deterministic sensor/pose feedback and the real navigation dispatch with mocks. It does not prove ONNX policy quality under closed-loop real LiDAR dynamics, or controller latency on Raspberry Pi 4.
- Keep `AGV_AI1_MODE=shadow` and `AGV_AI2_MODE=shadow` on Pi until model approval, repeatability testing, collision/coverage comparisons against the traditional baseline, and Pi CPU/latency measurements have been completed.

## Pi 4 powered on: isolated verification (2026-10-20, approximately 09:52–09:55 UTC+7)

- SSH to `khangho@100.90.252.15` succeeded over Tailscale. The Pi reported `Linux 6.8.0-1065-raspi` (aarch64), Python 3.12.3, ONNX Runtime 1.31.0, and approximately 7.2 GiB RAM available. CPU temperature was approximately 32.1°C at initial inspection.
- The controller, LiDAR and SLAM processes were absent at inspection; HTTP port 8080 was not listening. Therefore **no live sensor-to-AI Shadow Mode session was performed**.
- The installed controller still had its older source (`SHA256 8b3e22...7e8595`) and **did not have `agv_ai_bridge.py`**. The new controller code and AI bridge were copied to `/home/khangho/agv_ai_shadow_stage_20261020` without modifying or restarting the installed controller. The integration test harness and benchmark script were copied to the staging tree's `tests/` directory.
- On the Pi, `python3 -B -m pytest -q tests/test_agv_ai_integration.py` succeeded: **29/29 passed (0.90 s)**. Tests mock ROS and motor transport; this is not physical validation.
- Both original ONNX model hashes on the Pi matched the PC copies: AI1 `7e860423...5cad99f7`, AI2 `8344842f...d197afd1`. `LocalPlannerRuntime` successfully verified the AI1 export manifest and loaded the model; both AI outputs were finite.

**Pi single-thread CPU benchmark**: 100 warmups and 1,000 timed samples per case; fixed synthetic inputs, no hardware I/O. Milliseconds:

| Benchmark | P50 | P95 | P99 | Max |
| --- | ---: | ---: | ---: | ---: |
| AI1 ONNX only | 2.2489 | 2.3420 | 2.3695 | 2.4543 |
| AI1 LiDAR/pose observation + ONNX + safety filter | 3.0814 | 3.1857 | **3.2129** | 3.3130 |
| AI2 ONNX only | 0.1090 | 0.1250 | 0.1399 | 0.1670 |

**Decision:** The AI1 inference-only P99 already exceeds the prior 2 ms target on the Pi (2.3695 ms); its measured local pipeline P99 is 3.2129 ms. The full LiDAR–ROS–Navigation–UART latency and workload impact are still unmeasured. Keep both models in shadow, compare against baseline on real ROS data next, and optimize/reassess the AI1 latency criterion before considering any learned motion control. The stage directory is for inspection/offline tests only; it has **not** been activated as the robot controller.

## Autonomous continuation: Pi sensor and AI diagnostics (2026-10-20)

### Delivered and tested

- Created a reusable **read-only** ROS subscriber: `tests/pi_ai_shadow_live.py`. It subscribes to `/scan` and `/map` and reads map->base_footprint TF when available. No UART, ROS publisher, AGV brain import, motion command, or change to the installed controller. If no real TF pose is available, the AI1 input is explicitly labelled a **hypothetical stationary pose with a goal 2 m ahead**; odometry and physical safety are not inferred. AI2 requires a map and real TF; missing map/TF causes a logged skip. AI2 explicitly labels visited-cell state as unknown.
- `tests/pi_run_sensor_shadow.sh` starts only the existing SLLiDAR C1 driver on `/dev/ttyUSB1`, collects a bounded 20-second read-only trace and terminates its own launch process group. It does not touch the motor serial port `/dev/ttyUSB0` or run `start_agv_system.sh`.
- `tests/pi_ai_shadow_map_probe.py` tests the existing `agv_ai_bridge.py` AI2 observation/ranking path on **two captured historical SLAM occupancy maps**. Synthetic robot poses on free inflated cells and empty visited state were used; neither constitutes live localization or real coverage. The original AI2 model produced finite four-element Q outputs on both maps.
- `tests/pi_ai1_ort_tuning.py` compares AI1 ONNX-only single-thread vs multi-thread CPU execution on the Pi. The original model and deployed runtime remain unchanged.
- Four additional read-only probe regressions added in `tests/test_pi_ai_shadow_probe.py`. **33/33 integration+probe tests passed on PC and again on Raspberry Pi.** Offline AGV suite still has the 2 pre-existing unresolved tests described above.

### On-Pi observation outcomes

| Evidence | Result |
| --- | --- |
| LiDAR-only attempt #1 | ROS driver exited 255: `SL_RESULT_OPERATION_TIMEOUT` |
| LiDAR-only attempt #2 | Same timeout, driver exited 255 |
| LiDAR `/scan` frames captured | **0**; consequently no real-LiDAR AI1 timing/behavior conclusions |
| Pi `/map` + map->base_footprint TF | Not published; brain, LiDAR and SLAM were not running |
| AI2 captured live map fixture `agv_live_map_20261002` | 134 reachable candidates; finite Q; observation + path + ONNX + ranking P99 **1.3770 ms** (100 repeats) |
| AI2 captured red-side map fixture `agv_red_side_map_20261003` | 176 reachable candidates; finite Q; same pipeline P99 **1.3915 ms** (100 repeats) |
| AI1 ONNX-only P99 @ 1, 2, 3, 4 CPU threads | **2.3940 / 2.2572 / 2.1915 / 2.1702 ms** (500 repeats each; P99 target <2 ms still unmet) |
| Final checks | 33/33 Pi pytest PASS; ROS observer initializes and exits as designed without `/scan`; no AGV, SLAM or LiDAR processes; both USB serial ports idle |

The C1 was still enumerated by USB as a CH340 `/dev/ttyUSB1`, while the CP2102N motor serial adapter remained `/dev/ttyUSB0`; the SLLiDAR device did not respond to initialization on two attempts. Historical logs from 2026-10-19 show that the same driver and 460800 baud setting had previously initialized and reported healthy. This supports a **current LiDAR communication/power/device problem**, but does not isolate the failing physical component. Pi temperature and CPU benchmarks are not relevant substitutes for missing scans. No software-only way to verify physical LiDAR power/cabling was available.

### Reuse once the sensor communication problem is corrected

```bash
# This runs the LiDAR sensor and an isolated read-only AI observer only.
bash /home/khangho/agv_ai_shadow_stage_20261020/tests/pi_run_sensor_shadow.sh

# Read the recorded probe events and the exact LiDAR launch error if any.
cat /home/khangho/agv_ai_shadow_stage_20261020/evidence/scan_shadow.jsonl
tail -30 /home/khangho/agv_ai_shadow_stage_20261020/evidence/lidar_only.log
```

Evidence copied back to `evidence/ai_pi_shadow_20261020/`. No code in the installed `/home/khangho/agv_codex_reader_20261003_0652` controller was overwritten. That installed controller's SHA256 remained `8b3e22bb...7c7e8595`; the separate staged new source was `14da4f22...318570de`. No reboot, controller startup, AUTO/ARM request, motor actuation, PID/firmware update or ROS topic publishing occurred. **AI1/AI2 real-sensor Shadow Mode remains blocked by the LiDAR startup timeout.**
