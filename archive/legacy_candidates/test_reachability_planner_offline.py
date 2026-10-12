import sys
from agv_reachability_frontier_planner import ReachabilityPlanner

def run_planner_tests():
    print("=== BẮT ĐẦU KIỂM THỬ REACHABILITY & FRONTIER PLANNER OFFLINE ===")

    # Bản đồ 10x10 ô
    planner = ReachabilityPlanner(10, 10, resolution=0.05)
    planner.home_cell = (1, 1)

    # Dựng bức tường chắn hoàn toàn chia đôi bản đồ từ x=5, y=0..9
    # để tạo ra phân vùng không thể vươn tới (Unreachable)
    for y in range(10):
        planner.set_cell(5, y, 100) # Ô bị chiếm (Tường chắn)

    current_pos = (2, 2)

    # Test 1: Điểm đích nằm cùng phía với Start -> Vươn tới được
    goal_reachable = (3, 3)
    path = planner.find_path(current_pos, goal_reachable)
    assert path is not None and len(path) > 0, "Test 1 Thất bại"
    print(f"[PASS 1/4] Tìm đường nội bộ cùng phân vùng thành công ({len(path)} bước)")

    # Test 2: Điểm đích nằm sau bức tường (x=7, y=7) -> Bắt buộc trả về None (Không thể tới)
    goal_unreachable = (7, 7)
    path_blocked = planner.find_path(current_pos, goal_unreachable)
    assert path_blocked is None, "Test 2 Thất bại: Điểm bị tường chặn nhưng vẫn tìm thấy đường"
    print("[PASS 2/4] Điểm sau tường bị chặn được xác nhận là Unreachable (trả về None)")

    # Test 3: Lọc danh sách Frontier: Chỉ chấp nhận các Frontier có đường đi thực tế
    candidates = [(3, 2), (4, 4), (7, 2), (8, 5)]
    valid_frontiers = planner.filter_reachable_frontiers(current_pos, candidates)
    assert (3, 2) in valid_frontiers and (4, 4) in valid_frontiers
    assert (7, 2) not in valid_frontiers and (8, 5) not in valid_frontiers
    print(f"[PASS 3/4] Lọc Frontier chính xác: Loại bỏ 2 frontier sau tường, giữ lại 2 frontier hợp lệ {valid_frontiers}")

    # Test 4: Kiểm tra tính liên thông về điểm xuất phát (Home Reachability)
    assert planner.check_home_reachability(current_pos) == True
    # Thử cô lập vị trí hiện tại bằng tường
    planner.set_cell(1, 2, 100)
    planner.set_cell(3, 2, 100)
    planner.set_cell(2, 1, 100)
    planner.set_cell(2, 3, 100)
    assert planner.check_home_reachability(current_pos) == False
    print("[PASS 4/4] Kiểm tra Home Reachability: Phát hiện chính xác khi bị mất đường lùi về Home")

    print("\n=== TOÀN BỘ 4/4 BÀI TEST PLANNER REACHABILITY ĐỀU PASS ĐẠT CHUẨN ===")
    return True

if __name__ == "__main__":
    if not run_planner_tests():
        sys.exit(1)
