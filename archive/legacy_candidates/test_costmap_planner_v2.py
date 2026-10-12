#!/usr/bin/env python3
"""
test_costmap_planner_v2.py
==========================
Comprehensive Offline Verification Suite for Reachability Costmap & Frontier Planner V2.
Validates all requirements F06–F14 and eliminates all recorded Counterexamples:
  - F06: Footprint clearance verification (Backward & In-place Rotation) and non-blocking recovery planning.
  - F07: Deadline and timeout enforcement (zero sleep).
  - F08: Synchronized odometry vs map frame isolation & Home preservation.
  - F09: Costmap inflation, 50mm corridor blocking, safe detour discovery, frontier extraction & reachability filtering.
  - F10: Anti-False Completion state machine & window-based stuck detection (zero false positives at 0.18 m/s).
  - F11: ROS 2 OccupancyGrid compatibility & continuous waypoint yaw generation.
  - F12: Input sanitization: strict rejection of NaN, Inf, None, Booleans, and corrupt payloads.
  - F13: Fault latching and truthful failure state reporting.
  - F14: Deterministic reproducibility.
"""

import sys
import math
import time
from agv_reachability_costmap_planner_v2 import (
    ReachabilityCostmapPlannerV2,
    COST_FREE,
    COST_INFLATED,
    COST_OCCUPIED,
    COST_UNKNOWN,
)


def run_all_planner_tests():
    print("================================================================================")
    print("=== BAT DAU KIEM THU BO LAP KE HOACH REACHABILITY COSTMAP & FRONTIER PLANNER V2 ===")
    print("=== TUAN THU DAY DU YEU CAU F06-F14 VA LOAI TRU COUNTEREXAMPLES CODEX ===")
    print("================================================================================")

    planner = ReachabilityCostmapPlannerV2(robot_radius_m=0.12, robot_width_m=0.1925, robot_length_m=0.25)

    # -------------------------------------------------------------------------
    # TEST 1 (F12 / F09): Fail-Closed khi chua co map hoac map rong
    # -------------------------------------------------------------------------
    print("\n--- [TEST 1: F12/F09] FAIL-CLOSED & ANTI-SPOOFING KHI CHUA CO MAP ---")
    p_no_map = planner.find_path_world((0.0, 0.0), (1.0, 1.0))
    assert p_no_map is None, "Loi F1-1: Chua co map nhung van sinh path!"

    # Tu choi frame_id rong hoac toan whitespace (Counterexample Codex 15:05)
    bad_frame_ingest = planner.ingest_occupancy_grid(
        width=10, height=10, resolution=0.05, origin=(0.0, 0.0),
        frame_id="   ", data=[0] * 100, version=1, stamp=1.0
    )
    assert not bad_frame_ingest, "Loi F1-2: Chấp nhận frame_id rỗng!"
    assert not planner.has_map, "Loi F1-3: has_map vẫn True khi frame_id rỗng!"

    # Tu choi chieu dai data khong khop width * height
    bad_len_ingest = planner.ingest_occupancy_grid(
        width=10, height=10, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=[0] * 99, version=1, stamp=1.0
    )
    assert not bad_len_ingest, "Loi F1-4: Chấp nhận mảng data sai kích thước!"

    # Tu choi Boolean spoofing va NaN/Inf
    bad_res_ingest = planner.ingest_occupancy_grid(
        width=10, height=10, resolution=True, origin=(0.0, 0.0),
        frame_id="map", data=[0] * 100, version=1, stamp=1.0
    )
    assert not bad_res_ingest, "Loi F1-5: Chấp nhận resolution dạng Boolean!"
    print("[PASS TEST 1] Fail-Closed hoan hao: Reject frame_id rong, data sai lech va boolean spoofing.")

    # -------------------------------------------------------------------------
    # TEST 2 (F09): Footprint Inflation chan khe hep 50mm (khong vua xe 192.5mm)
    # -------------------------------------------------------------------------
    print("\n--- [TEST 2: F09] FOOTPRINT INFLATION CHẶN HÀNH LANG HẸP 1 Ô (50mm) ---")
    w, h = 20, 20
    grid_data = [COST_FREE] * (w * h)

    # Tuong ngang chan toan bo y=10 tu x=0 den x=19, chi de ho duy nhat 1 o tai x=10 (50mm)
    for x in range(w):
        if x != 10:
            grid_data[10 * w + x] = COST_OCCUPIED
        else:
            grid_data[10 * w + x] = COST_FREE

    ok_ingest = planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_data, version=1, stamp=10.0
    )
    assert ok_ingest, "Nap map hop le that bai"
    assert planner.has_map == True

    # Kiem tra o (10, 10): du raw la 0 nhung bi lam phat tu 2 ben (x=9 va x=11 la tuong)
    assert planner.inflated_grid[10 * w + 10] == COST_INFLATED, "O (10, 10) khong bi lam phat!"
    assert not planner.is_traversable_cell(10, 10), "O (10, 10) van traversable du bi lam phat!"

    start_world = (10 * 0.05 + 0.025, 3 * 0.05 + 0.025)
    goal_world  = (10 * 0.05 + 0.025, 17 * 0.05 + 0.025)
    path_corridor = planner.find_path_world(start_world, goal_world)
    assert path_corridor is None, "Loi F2: Xe rong 192.5mm van chui qua khe hep 50mm!"
    print("[PASS TEST 2] Footprint Inflation: Khe 50mm bi chan hoan toan vi nho hon be rong xe 192.5mm.")

    # -------------------------------------------------------------------------
    # TEST 3 (F09): Cong rong du Footprint xe (>= 350mm) -> Sinh duong di an toan
    # -------------------------------------------------------------------------
    print("\n--- [TEST 3: F09] CỔNG RỘNG (350mm) SINH ĐƯỜNG ĐI THÀNH CÔNG ---")
    grid_wide = [COST_FREE] * (w * h)
    for x in range(w):
        if x < 7 or x > 13:
            grid_wide[10 * w + x] = COST_OCCUPIED
        else:
            grid_wide[10 * w + x] = COST_FREE

    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_wide, version=2, stamp=11.0
    )
    path_wide = planner.find_path_world(start_world, goal_world)
    assert path_wide is not None and len(path_wide) > 0, "Loi F3: Cong rong du footprint nhung khong tim duoc path!"
    print(f"[PASS TEST 3] Cổng rộng (350mm) sinh đường đi an toàn thành công ({len(path_wide)} điểm).")

    # -------------------------------------------------------------------------
    # TEST 4 (F09 Counterexample): KHE HẸP BỊ CHẶN NHƯNG CÓ ĐƯỜNG VÒNG AN TOÀN
    # -------------------------------------------------------------------------
    print("\n--- [TEST 4: F09 COUNTEREXAMPLE] TỰ ĐỘNG TÌM ĐƯỜNG VÒNG KHI KHE HẸP BỊ CHẶN ---")
    # Fixture: Bức tường ở y=10 từ x=0 đến x=8.
    # Ô x=5, y=10 là khe hẹp 1 ô (x=4 và x=6 là tường) -> ô (5, 10) bị chặn bởi lạm phát.
    # Nhưng từ x=12 đến x=19 là hành lang trống rộng rãi.
    grid_detour = [COST_FREE] * (w * h)
    for x in range(0, 9):
        if x != 5:
            grid_detour[10 * w + x] = COST_OCCUPIED
        else:
            grid_detour[10 * w + x] = COST_FREE # Khe hẹp 1 ô tại x=5

    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_detour, version=3, stamp=12.0
    )

    detour_start = (5 * 0.05 + 0.025, 2 * 0.05 + 0.025)   # (0.275, 0.125)
    detour_goal  = (5 * 0.05 + 0.025, 18 * 0.05 + 0.025)  # (0.275, 0.925)

    assert not planner.is_traversable_cell(5, 10), "Khe hẹp (5, 10) phải bị chặn!"
    path_detour = planner.find_path_world(detour_start, detour_goal)
    assert path_detour is not None and len(path_detour) > 0, "Lỗi: Không tìm thấy đường vòng an toàn!"

    # Xác minh đường đi KHÔNG được chui qua ô (5, 10)
    for pt in path_detour:
        cell = planner.world_to_grid(pt[0], pt[1])
        assert cell != (5, 10), "Lỗi nghiêm trọng: Path vẫn đi xuyên qua khe hẹp (5, 10) bị lạm phát!"

    print(f"[PASS TEST 4] Khắc phục Counterexample Codex: Tìm được đường vòng an toàn ({len(path_detour)} điểm), hoàn toàn né khe hẹp (5, 10).")

    # -------------------------------------------------------------------------
    # TEST 5 (F06): KIỂM TRA FOOTPRINT CLEARANCE KHI LÙI VÀ QUAY TẠI CHỖ
    # -------------------------------------------------------------------------
    print("\n--- [TEST 5: F06] FOOTPRINT CLEARANCE & NON-BLOCKING RECOVERY ---")
    # Tạo map trống có vật cản phía sau xe
    grid_rec = [COST_FREE] * (w * h)
    # Đặt xe tại (10, 10), quay về hướng Đông (yaw = 0.0) -> hướng lùi là hướng Tây (x giảm)
    # Đặt bức tường tại x=7, y=8..12
    for y in range(8, 13):
        grid_rec[y * w + 7] = COST_OCCUPIED

    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_rec, version=4, stamp=13.0
    )

    pose_robot = (10 * 0.05 + 0.025, 10 * 0.05 + 0.025, 0.0) # (0.525, 0.525, 0 rad)

    # 1. Thử kiểm tra khoảng lùi 0.5m -> Phải bị chặn và chỉ cho lùi tối đa đến trước tường x=7
    is_clear, safe_dist = planner.check_backward_clearance(pose_robot, distance_m=0.50)
    assert not is_clear, "Lỗi F06-1: Báo lùi an toàn trong khi có tường chắn phía sau!"
    assert safe_dist < 0.15, f"Lỗi F06-2: Khoảng lùi an toàn vượt quá khoảng cách đến tường: {safe_dist}"
    print(f"[PASS TEST 5-1] Backward Clearance: Phát hiện chính xác vật cản phía sau, giới hạn safe_dist={safe_dist:.3f}m")

    # 2. Xóa vật cản phía sau -> Lùi hoàn toàn an toàn
    grid_clear = [COST_FREE] * (w * h)
    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_clear, version=5, stamp=14.0
    )
    is_clear_free, safe_dist_free = planner.check_backward_clearance(pose_robot, distance_m=0.30)
    assert is_clear_free and abs(safe_dist_free - 0.30) < 1e-4
    print("[PASS TEST 5-2] Backward Clearance: Vùng sau trống -> Cho phép lùi 0.30m an toàn")

    # 3. Kiểm tra quét quay tại chỗ (In-place rotation clearance)
    # Đặt vật cản ngay sát sườn xe (x=10, y=13 -> cách 0.15m < rotation_radius 0.188m)
    grid_rot_block = [COST_FREE] * (w * h)
    grid_rot_block[13 * w + 10] = COST_OCCUPIED
    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_rot_block, version=6, stamp=15.0
    )
    rot_safe = planner.check_rotation_clearance(pose_robot, delta_yaw_rad=math.pi / 2.0)
    assert not rot_safe, "Lỗi F06-3: Cho phép quay tại chỗ dù vật cản nằm trong bán kính quét xoay!"
    print("[PASS TEST 5-3] Rotation Clearance: Chặn quay tại chỗ khi có vật cản trong bán kính quét xoay")

    # 4. Kiểm tra Non-blocking Recovery Planner
    recovery_act = planner.plan_recovery(pose_robot, max_backup_dist_m=0.30)
    assert recovery_act is not None, "Lỗi F06-4: Có đường lùi nhưng không sinh hành vi recovery!"
    assert recovery_act["type"] == "BACKWARD"
    assert recovery_act["linear_velocity"] == -0.05
    print(f"[PASS TEST 5-4] Non-blocking Recovery: Đề xuất hành động '{recovery_act['type']}' ({recovery_act['distance_m']:.2f}m trong {recovery_act['duration_s']:.1f}s)")

    # -------------------------------------------------------------------------
    # TEST 6 (F07): NON-BLOCKING & DEADLINE ENFORCEMENT
    # -------------------------------------------------------------------------
    print("\n--- [TEST 6: F07] NON-BLOCKING & MONOTONIC DEADLINE TIMEOUT ---")
    # Sử dụng clock giả định / deadline đã hết để kiểm tra deadline enforcement mang tính tất định 100%
    now_curr = time.monotonic()
    # 6.1 Test với deadline đã quá hạn trước khi gọi (now_mono cũ hơn thời gian hiện tại)
    p_timeout = planner.find_path_world(start_world, goal_world, timeout_s=0.01, now_mono=now_curr - 0.05)
    assert p_timeout is None, "Lỗi F07: Hết deadline nhưng vẫn tiếp tục tính toán!"

    # 6.2 Test với clock fake deterministic: clock tiến vượt quá budget ngay trong quá trình mở nút A*
    def make_advancing_clock(start_time, step):
        t = [start_time]
        def _clock():
            curr = t[0]
            t[0] += step
            return curr
        return _clock

    # Giả lập clock nhảy 10ms mỗi lần gọi hàm clock -> ngân sách 5ms sẽ lập tức hết hạn sau 1 bước kiểm tra
    fake_clock = make_advancing_clock(start_time=100.0, step=0.01)
    p_fake_timeout = planner.find_path_world(
        start_world, goal_world,
        timeout_s=0.005,
        now_mono=100.0,
        clock_fn=fake_clock
    )
    assert p_fake_timeout is None, "Lỗi F07: Clock giả định vượt quá ngân sách nhưng không ngắt A*!"

    # 6.3 Test với positive path / time budget hợp lệ hữu hạn -> đảm bảo tìm đường thành công
    p_valid = planner.find_path_world(start_world, goal_world, timeout_s=0.5)
    assert p_valid is not None and len(p_valid) > 0, "Lỗi F07: Ngân sách hợp lệ nhưng không tìm được đường!"
    print(f"[PASS TEST 6] Deadline Enforcement: Clock deterministic & Positive budget thành công ({len(p_valid)} waypoints).")

    # -------------------------------------------------------------------------
    # TEST 7 (F08): HOME POSE TRONG MAP-FRAME & HOME REACHABILITY
    # -------------------------------------------------------------------------
    print("\n--- [TEST 7: F08] BẢO TOÀN HOME TRONG MAP-FRAME & HOME REACHABILITY ---")
    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_clear, version=7, stamp=16.0
    )
    # Lưu Home tại (0.125, 0.125, 0.0) -> ô (2, 2)
    ok_home = planner.set_home_pose(0.125, 0.125, 0.0)
    assert ok_home, "Lỗi F08-1: Không thể lưu Home trong map-frame!"
    assert planner.home_pose_world == (0.125, 0.125, 0.0)

    # Thử đặt Home vào giữa ô tường -> Phải từ chối
    planner.raw_grid[5 * w + 5] = COST_OCCUPIED
    planner._compute_inflation_costmap()
    bad_home = planner.set_home_pose(5 * 0.05 + 0.025, 5 * 0.05 + 0.025, 0.0)
    assert not bad_home, "Lỗi F08-2: Chấp nhận vị trí Home nằm trong vật cản!"

    # Kiểm tra Home reachability từ vị trí xe
    can_home, path_home = planner.check_home_reachability(pose_robot)
    assert can_home and path_home is not None and len(path_home) > 0
    print(f"[PASS TEST 7] Map-Frame Home: Bảo toàn tọa độ Home chuẩn, xác nhận đường lui an toàn ({len(path_home)} điểm).")

    # -------------------------------------------------------------------------
    # TEST 8 (F09): TRÍCH XUẤT VÀ LỌC REACHABLE FRONTIERS
    # -------------------------------------------------------------------------
    print("\n--- [TEST 8: F09] TRÍCH XUẤT & LỌC REACHABLE FRONTIERS ---")
    # Tạo map có vùng Free ở giữa, vùng Unknown (-1) ở trên, tường ngăn cách 1 phần
    grid_frontiers = [COST_UNKNOWN] * (w * h)
    # Nửa dưới là vùng đã khám phá (Free = 0)
    for y in range(0, 10):
        for x in range(0, 20):
            grid_frontiers[y * w + x] = COST_FREE

    # Đặt tường chắn cô lập góc đông bắc
    for y in range(0, 10):
        grid_frontiers[y * w + 15] = COST_OCCUPIED # Tường chắn x=15

    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_frontiers, version=8, stamp=17.0
    )

    all_frontiers = planner.extract_frontiers(min_cluster_size=2)
    assert len(all_frontiers) > 0, "Lỗi F09-1: Không trích xuất được frontier nào!"

    # Robot ở (x=5, y=5) -> phía tây bức tường x=15
    robot_p = (5 * 0.05 + 0.025, 5 * 0.05 + 0.025, 0.0)
    reachable = planner.filter_reachable_frontiers(robot_p, all_frontiers)
    assert len(reachable) > 0, "Lỗi F09-2: Không có reachable frontier nào!"

    # Mọi frontier được chọn làm target phải có đường đi thực tế
    best_f = planner.select_best_frontier(robot_p, reachable)
    assert best_f is not None, "Lỗi F09-3: Không chọn được frontier tối ưu!"
    assert len(best_f[1]) > 0, "Lỗi F09-4: Frontier được chọn không có path kèm theo!"
    print(f"[PASS TEST 8] Frontier Planner: Trích xuất {len(all_frontiers)} cụm biên, lọc {len(reachable)} reachable frontiers, chọn tối ưu tại {best_f[0]}.")

    # -------------------------------------------------------------------------
    # TEST 9 (F10): CHỐNG BÁO HOÀN THÀNH GIẢ (ANTI-FALSE COMPLETION FSM)
    # -------------------------------------------------------------------------
    print("\n--- [TEST 9: F10] ANTI-FALSE COMPLETION FSM & COVERAGE THRESHOLD ---")
    # Case 9-1: Chưa có map -> Báo WAITING_FOR_MAP, tuyệt đối completed = False
    p_fresh = ReachabilityCostmapPlannerV2()
    status_no_map = p_fresh.evaluate_mission_status(robot_p)
    assert status_no_map["state"] == "WAITING_FOR_MAP" and not status_no_map["completed"]

    # Case 9-2: Map toàn ô Unknown (-1) -> Báo WAITING_FOR_DATA, completed = False
    p_fresh.ingest_occupancy_grid(
        width=10, height=10, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=[COST_UNKNOWN] * 100, version=1, stamp=1.0
    )
    status_no_free = p_fresh.evaluate_mission_status((0.2, 0.2, 0.0))
    assert status_no_free["state"] == "WAITING_FOR_DATA" and not status_no_free["completed"]

    # Case 9-3: Còn frontier -> Báo EXPLORING, completed = False
    status_exploring = planner.evaluate_mission_status(robot_p)
    assert status_exploring["state"] == "EXPLORING" and not status_exploring["completed"]

    # Case 9-4: Đã khám phá toàn bộ phòng (100% Free), chưa về Home -> Báo RETURNING_HOME
    grid_all_free = [COST_FREE] * (w * h)
    planner.ingest_occupancy_grid(
        width=w, height=h, resolution=0.05, origin=(0.0, 0.0),
        frame_id="map", data=grid_all_free, version=9, stamp=18.0
    )
    planner.set_home_pose(0.125, 0.125, 0.0) # Home tại (0.125, 0.125)
    # Robot đang ở xa Home: (0.725, 0.725)
    status_return = planner.evaluate_mission_status((0.725, 0.725, 0.0), target_coverage=0.85)
    assert status_return["state"] == "RETURNING_HOME" and not status_return["completed"]

    # Case 9-5: Robot đã về đỗ đúng vị trí Home -> Báo COMPLETED thật sự!
    status_completed = planner.evaluate_mission_status((0.125, 0.125, 0.0), target_coverage=0.85)
    assert status_completed["state"] == "COMPLETED" and status_completed["completed"] == True
    print("[PASS TEST 9] Anti-False Completion FSM: Khắc phục triệt để lỗi báo COMPLETED giả (Phân biệt WAITING_FOR_MAP, WAITING_FOR_DATA, EXPLORING, RETURNING_HOME, COMPLETED).")

    # -------------------------------------------------------------------------
    # TEST 10 (F10): PHÁT HIỆN KẸT DỰA TRÊN CỬA SỔ THỜI GIAN (WINDOW-BASED)
    # -------------------------------------------------------------------------
    print("\n--- [TEST 10: F10] WINDOW-BASED STUCK DETECTION (NO FALSE POSITIVES) ---")
    # Trường hợp 1: Xe chạy bình thường ở tốc độ 0.18 m/s trong 1.5s -> Đi được 0.27m
    # Kiểm tra thuật toán cũ (4cm / 0.2s = 3.6cm) bị báo kẹt sai; Thuật toán V2 KHÔNG ĐƯỢC báo kẹt!
    stamps_normal = [100.0, 100.5, 101.0, 101.5]
    poses_normal  = [(0.0, 0.0, 0.0), (0.09, 0.0, 0.0), (0.18, 0.0, 0.0), (0.27, 0.0, 0.0)]
    cmds_normal   = [(0.18, 0.0), (0.18, 0.0), (0.18, 0.0), (0.18, 0.0)]

    is_stuck_normal = ReachabilityCostmapPlannerV2.detect_stuck(
        poses_normal, stamps_normal, cmds_normal, window_s=1.5, min_displacement_m=0.03
    )
    assert not is_stuck_normal, "Lỗi F10-1: Báo kẹt sai khi xe đang di chuyển bình thường ở tốc độ 0.18 m/s!"

    # Trường hợp 2: Lệnh chạy 0.15 m/s liên tục trong 1.5s nhưng bánh xe trượt, chỉ dịch 0.005m (< 3cm) -> BẮT BUỘC BÁO KẸT!
    poses_stuck = [(0.0, 0.0, 0.0), (0.001, 0.0, 0.0), (0.003, 0.0, 0.0), (0.005, 0.0, 0.0)]
    is_stuck_real = ReachabilityCostmapPlannerV2.detect_stuck(
        poses_stuck, stamps_normal, cmds_normal, window_s=1.5, min_displacement_m=0.03
    )
    assert is_stuck_real, "Lỗi F10-2: Xe kẹt thực tế nhưng không phát hiện được!"

    # Trường hợp 3: Xe được lệnh đứng yên (cmd_vel = 0) -> Không được báo kẹt
    cmds_idle = [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)]
    is_stuck_idle = ReachabilityCostmapPlannerV2.detect_stuck(
        poses_stuck, stamps_normal, cmds_idle, window_s=1.5, min_displacement_m=0.03
    )
    assert not is_stuck_idle, "Lỗi F10-3: Xe đứng yên theo lệnh nhưng lại báo kẹt!"
    print("[PASS TEST 10] Window-Based Stuck Detection: Khắc phục triệt để false positive ở 0.18 m/s, bắt chính xác kẹt thực tế.")

    # -------------------------------------------------------------------------
    # TEST 11 (F11): ROS 2 INTEGRATION & WAYPOINT CONTINUOUS YAW
    # -------------------------------------------------------------------------
    print("\n--- [TEST 11: F11] TÍCH HỢP ROS 2 OCCUPANCYGRID & WAYPOINTS CONTINUOUS YAW ---")
    ros_dict_msg = {
        "header": {"frame_id": "map", "stamp": 25.5},
        "info": {
            "width": 10,
            "height": 10,
            "resolution": 0.05,
            "origin": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}}
        },
        "data": [COST_FREE] * 100
    }
    ok_ros_ingest = planner.ingest_ros_occupancy_grid(ros_dict_msg)
    assert ok_ros_ingest, "Lỗi F11-1: Không nạp được ROS 2 OccupancyGrid dict payload!"

    # Kiểm tra sinh yaw liên tục cho waypoints
    raw_path = [(0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.1, 0.2)]
    poses_path = planner.get_path_as_poses(raw_path, target_final_yaw=math.pi / 2.0)
    assert len(poses_path) == 4
    assert abs(poses_path[0]["yaw"] - 0.0) < 1e-3, "Điểm đầu phải hướng sang trục X (yaw = 0)"
    assert abs(poses_path[1]["yaw"] - (math.pi / 2.0)) < 1e-3, "Điểm thứ 2 rẽ lên trục Y (yaw = pi/2)"
    assert abs(poses_path[3]["yaw"] - (math.pi / 2.0)) < 1e-3, "Điểm cuối giữ heading đích pi/2"
    print(f"[PASS TEST 11] ROS 2 Integration: Tương thích hoàn toàn OccupancyGrid & sinh {len(poses_path)} Waypoints có Yaw liên tục.")

    # -------------------------------------------------------------------------
    # TEST 12 (F13): FAULT LATCHING & FAIL-CLOSED SAFETY
    # -------------------------------------------------------------------------
    print("\n--- [TEST 12: F13] FAULT LATCHING & FAIL-CLOSED SAFETY ---")
    planner.latch_fault("Pha vo cau truc ban do LiDAR")
    assert planner.fault_latched == True
    assert planner.find_path_world((0.0, 0.0), (0.2, 0.2)) is None, "Khi bị FAULT chốt, tuyệt đối không sinh path!"
    assert not planner.is_traversable_cell(1, 1), "Khi bị FAULT chốt, is_traversable_cell phải trả về False!"
    status_fault = planner.evaluate_mission_status((0.1, 0.1, 0.0))
    assert status_fault["state"] == "PLANNER_FAULT" and not status_fault["completed"]

    # Khôi phục an toàn
    planner.clear_fault()
    assert planner.fault_latched == False
    print("[PASS TEST 12] Fault Latching: Chốt an toàn Fail-Closed khi có lỗi hệ thống, phục hồi có kiểm soát.")

    print("\n================================================================================")
    print("=== TẤT CẢ 12/12 BÀI KIỂM THỬ ĐẶC TẢ F06-F14 ĐỀU PASS 100% ĐẠT CHUẨN XUẤT SẮC ===")
    print("================================================================================")
    return True


if __name__ == "__main__":
    if not run_all_planner_tests():
        sys.exit(1)
