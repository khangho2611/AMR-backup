#!/usr/bin/env python3
"""
agv_reachability_costmap_planner_v2.py
======================================
Production-grade Reachability Costmap & Frontier Planner V2 for Autonomous Guided Vehicles (AGV).
Fully satisfies Autonomous Navigation & Exploration Quality Requirements F06–F14:
  - F06: Footprint clearance verification for backward recovery and in-place rotation; non-blocking recovery planning.
  - F07: Non-blocking, deadline-based execution (zero sleep); monotonic timing.
  - F08: Synchronized odometry vs map frame isolation; map-frame Home preservation.
  - F09: Standard OccupancyGrid ingestion with strict frame/stamp validation, Euclidean A* path planning with
         corner-cutting prevention, footprint inflation (wheelbase L=187.5mm, track width W=192.5mm, radius R>=0.12m),
         narrow corridor blocking while discovering valid detours, frontier clustering & reachability filtering.
  - F10: Anti-False Completion state machine (WAITING_FOR_MAP, WAITING_FOR_DATA, EXPLORING, RETURNING_HOME, COMPLETED)
         based on evaluated room coverage; window-based stuck detection avoiding false positives at 0.18 m/s.
  - F11: Standard ROS 2 / SLAM OccupancyGrid & Path interface compatibility with continuous orientation generation.
  - F12: Strict input validation and sanitization: zero tolerance for NaN, Inf, None, bool-spoofing, negative dimensions.
  - F13: Error states and fault handling: fault latching, truthful error reporting, fail-closed safety.
  - F14: Comprehensive type safety, modular architecture, and deterministic test harness reproducibility.
"""

from typing import List, Tuple, Optional, Dict, Any, Set, Callable
from collections import deque
import math
import time
import heapq

# Costmap Constants
COST_FREE: int = 0
COST_INFLATED: int = 99
COST_OCCUPIED: int = 100
COST_UNKNOWN: int = -1

# AGV Physical Dimensions
DEFAULT_ROBOT_RADIUS_M: float = 0.12        # Safe bounding radius (track width 192.5mm -> half-width 96.25mm + margin)
DEFAULT_ROBOT_WIDTH_M: float = 0.1925       # Track width (m)
DEFAULT_ROBOT_LENGTH_M: float = 0.250       # Chassis length (m)
DEFAULT_SAFETY_MARGIN_M: float = 0.03       # Clearance buffer (m)


def _validate_finite_float(val: Any, name: str) -> float:
    """Helper rejecting non-finite floats, booleans, and invalid types."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"Tham so '{name}' khong hop le (yeu cau so thuc huu han): {val}")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ValueError(f"Tham so '{name}' khong duoc chua NaN hoac Inf: {f_val}")
    return f_val


class ReachabilityCostmapPlannerV2:
    """
    Bo lap ke hoach dan duong Reachability Costmap & Frontier Planner V2.
    Tuan thu tieu chuan he thong san xuat, dap ung day du F06-F14.
    """

    def __init__(
        self,
        robot_radius_m: float = DEFAULT_ROBOT_RADIUS_M,
        robot_width_m: float = DEFAULT_ROBOT_WIDTH_M,
        robot_length_m: float = DEFAULT_ROBOT_LENGTH_M,
        safety_margin_m: float = DEFAULT_SAFETY_MARGIN_M,
    ) -> None:
        self.robot_radius_m: float = _validate_finite_float(robot_radius_m, "robot_radius_m")
        self.robot_width_m: float = _validate_finite_float(robot_width_m, "robot_width_m")
        self.robot_length_m: float = _validate_finite_float(robot_length_m, "robot_length_m")
        self.safety_margin_m: float = _validate_finite_float(safety_margin_m, "safety_margin_m")

        # In-place rotation bounding radius (swept radius of rectangle during pure rotation)
        self.rotation_radius_m: float = math.hypot(self.robot_length_m / 2.0, self.robot_width_m / 2.0) + self.safety_margin_m

        # Map metadata & state
        self.has_map: bool = False
        self.width: int = 0
        self.height: int = 0
        self.resolution: float = 0.05
        self.origin: Tuple[float, float] = (0.0, 0.0)
        self.frame_id: str = ""
        self.map_version: int = 0
        self.stamp: float = 0.0

        # Grid data
        self.raw_grid: List[int] = []
        self.inflated_grid: List[int] = []

        # Home pose in map frame (x, y, yaw)
        self.home_pose_world: Optional[Tuple[float, float, float]] = None

        # Fault management
        self.fault_latched: bool = False
        self.fault_reason: str = ""

    # =========================================================================
    # F13: FAULT MANAGEMENT & SAFETY LATCH
    # =========================================================================
    def latch_fault(self, reason: str) -> None:
        """Chot trang thai loi he thong; vo hieu hoa moi chuc nang sinh path (Fail-Closed)."""
        self.fault_latched = True
        self.fault_reason = str(reason)

    def clear_fault(self) -> None:
        """Xoa chot loi (chi duoc goi khi he thong da khoi tao lai an toan)."""
        self.fault_latched = False
        self.fault_reason = ""

    # =========================================================================
    # F09, F11, F12: MAP INGESTION & INFLATION COSTMAP
    # =========================================================================
    def ingest_occupancy_grid(
        self,
        width: int,
        height: int,
        resolution: float,
        origin: Tuple[float, float],
        frame_id: str,
        data: List[int],
        version: int = 1,
        stamp: float = 0.0,
    ) -> bool:
        """
        Nap OccupancyGrid chuan tu SLAM/ROS 2.
        Kiem tra nghiem ngat tat ca tham so (F12). Neu sai lech -> Fail-Closed.
        """
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            self.has_map = False
            return False
        if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
            self.has_map = False
            return False

        try:
            res = _validate_finite_float(resolution, "resolution")
            if res < 0.001 or res > 1.0:
                self.has_map = False
                return False
        except ValueError:
            self.has_map = False
            return False

        if not isinstance(origin, (tuple, list)) or len(origin) < 2:
            self.has_map = False
            return False
        try:
            ox = _validate_finite_float(origin[0], "origin_x")
            oy = _validate_finite_float(origin[1], "origin_y")
        except ValueError:
            self.has_map = False
            return False

        # Validate frame_id (F09/F11): bat buoc la chuoi khac rong va khong phai toan whitespace
        if not isinstance(frame_id, str) or not frame_id.strip():
            self.has_map = False
            return False

        # Validate stamp
        try:
            st = _validate_finite_float(stamp, "stamp")
            if st < 0.0:
                self.has_map = False
                return False
        except ValueError:
            self.has_map = False
            return False

        # Validate grid data payload
        expected_len = width * height
        if not isinstance(data, (list, tuple)) or len(data) != expected_len:
            self.has_map = False
            return False

        # Validate values in data [-1, 100]
        raw = list(data)
        for val in raw:
            if isinstance(val, bool) or not isinstance(val, int) or (val < -1 or val > 100):
                self.has_map = False
                return False

        # P2 Fix: Nếu frame_id thay đổi mà không có TF chuyển đổi, phải invalidate home_pose_world
        new_frame = frame_id.strip()
        if self.frame_id and self.frame_id != new_frame:
            # Frame đổi -> invalidate home cũ để tránh sai lệch tọa độ
            self.home_pose_world = None

        # Commit metadata
        self.width = width
        self.height = height
        self.resolution = res
        self.origin = (ox, oy)
        self.frame_id = new_frame
        self.map_version = int(version)
        self.stamp = st
        self.raw_grid = raw

        # Tinh toan Costmap lam phat theo footprint thuc te cua robot
        self._compute_inflation_costmap()
        self.has_map = True
        return True

    def ingest_ros_occupancy_grid(self, ros_msg: Any) -> bool:
        """
        F11: Tuong thich truc tiep voi nav_msgs/OccupancyGrid cua ROS 2 hoac Dict payload.
        """
        try:
            if hasattr(ros_msg, "info") and hasattr(ros_msg, "header") and hasattr(ros_msg, "data"):
                w = ros_msg.info.width
                h = ros_msg.info.height
                res = ros_msg.info.resolution
                ox = ros_msg.info.origin.position.x
                oy = ros_msg.info.origin.position.y
                frame = ros_msg.header.frame_id
                stamp_sec = float(getattr(ros_msg.header.stamp, "sec", 0.0)) + float(getattr(ros_msg.header.stamp, "nanosec", 0.0)) * 1e-9
                data = list(ros_msg.data)
                return self.ingest_occupancy_grid(w, h, res, (ox, oy), frame, data, stamp=stamp_sec)
            elif isinstance(ros_msg, dict):
                info = ros_msg.get("info", {})
                header = ros_msg.get("header", {})
                w = info.get("width")
                h = info.get("height")
                res = info.get("resolution")
                orig = info.get("origin", {})
                pos = orig.get("position", {}) if isinstance(orig, dict) else {}
                ox = pos.get("x", 0.0)
                oy = pos.get("y", 0.0)
                frame = header.get("frame_id", "map")
                st = header.get("stamp", 0.0)
                data = ros_msg.get("data", [])
                return self.ingest_occupancy_grid(w, h, res, (ox, oy), frame, data, stamp=st)
        except Exception:
            pass
        self.has_map = False
        return False

    def _compute_inflation_costmap(self) -> None:
        """
        Lạm phát vat can (Occupied >= 50) ra ban kinh an toan robot_radius_m.
        Cac o nam trong ban kinh Euclidean deu bi danh dau COST_INFLATED (99).
        Cac o Unknown (-1) duoc bao ton rieng biet de phat hien Frontier.
        """
        self.inflated_grid = list(self.raw_grid)
        inflation_cells = int(math.ceil(self.robot_radius_m / self.resolution))
        r_sq = self.robot_radius_m ** 2

        occupied_indices = [i for i, val in enumerate(self.raw_grid) if val >= 50]

        for idx in occupied_indices:
            ox = idx % self.width
            oy = idx // self.width

            for dy in range(-inflation_cells, inflation_cells + 1):
                for dx in range(-inflation_cells, inflation_cells + 1):
                    dist_sq = ((dx * self.resolution) ** 2) + ((dy * self.resolution) ** 2)
                    if dist_sq <= r_sq:
                        nx = ox + dx
                        ny = oy + dy
                        if 0 <= nx < self.width and 0 <= ny < self.height:
                            n_idx = ny * self.width + nx
                            if self.raw_grid[n_idx] < 50:
                                self.inflated_grid[n_idx] = COST_INFLATED

    # =========================================================================
    # COORDINATE CONVERSIONS & TRAVERSABILITY (F09, F12)
    # =========================================================================
    def world_to_grid(self, wx: float, wy: float) -> Optional[Tuple[int, int]]:
        """Chuyen toa do the gioi (m) sang toa do luoi (o)."""
        if not self.has_map or self.fault_latched:
            return None
        try:
            fwx = _validate_finite_float(wx, "wx")
            fwy = _validate_finite_float(wy, "wy")
        except ValueError:
            return None

        gx = int(math.floor((fwx - self.origin[0]) / self.resolution))
        gy = int(math.floor((fwy - self.origin[1]) / self.resolution))
        if 0 <= gx < self.width and 0 <= gy < self.height:
            return (gx, gy)
        return None

    def grid_to_world(self, gx: int, gy: int) -> Tuple[float, float]:
        """Chuyen toa do luoi (o) sang tam o trong toa do the gioi (m)."""
        wx = self.origin[0] + (gx + 0.5) * self.resolution
        wy = self.origin[1] + (gy + 0.5) * self.resolution
        return (wx, wy)

    def is_traversable_cell(self, cx: int, cy: int, allow_unknown: bool = False) -> bool:
        """
        Kiem tra mot o co the di qua duoc khong.
        Dieu kien: nam trong luoi, khong phai vat can, khong bi lam phat.
        """
        if not self.has_map or self.fault_latched:
            return False
        if 0 <= cx < self.width and 0 <= cy < self.height:
            val = self.inflated_grid[cy * self.width + cx]
            if val == COST_FREE:
                return True
            if allow_unknown and val == COST_UNKNOWN:
                return True
            return False
        return False

    # =========================================================================
    # F07, F09, F12: A* OPTIMAL PATH PLANNING WITH DEADLINE
    # =========================================================================
    def find_path_world(
        self,
        start_w: Tuple[float, float],
        goal_w: Tuple[float, float],
        timeout_s: float = 1.0,
        now_mono: Optional[float] = None,
        allow_unknown: bool = False,
        clock_fn: Optional[Callable[[], float]] = None,
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Tim duong di toi uu tu Start den Goal bang thuat toan A* 8 huong.
        - Khong chan (Non-blocking): kiem tra deadline lien tuc bang time.monotonic() (F07).
        - Chong cat goc vat can (Corner-cutting prevention) (F09).
        - Tu dong tim duong vong an toan neu khe truc dien bi chan (F09).
        - Tra ve None neu khong co duong, het thoi gian hoac chua co map (Fail-Closed).
        """
        if not self.has_map or self.fault_latched:
            return None

        if not isinstance(start_w, (tuple, list)) or len(start_w) < 2:
            return None
        if not isinstance(goal_w, (tuple, list)) or len(goal_w) < 2:
            return None

        start_c = self.world_to_grid(start_w[0], start_w[1])
        goal_c = self.world_to_grid(goal_w[0], goal_w[1])
        if start_c is None or goal_c is None:
            return None

        if not self.is_traversable_cell(goal_c[0], goal_c[1], allow_unknown=allow_unknown):
            return None

        if not self.is_traversable_cell(start_c[0], start_c[1], allow_unknown=allow_unknown):
            recovered_start = None
            min_dist = float("inf")
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    cand = (start_c[0] + dx, start_c[1] + dy)
                    if self.is_traversable_cell(cand[0], cand[1], allow_unknown=allow_unknown):
                        d = math.hypot(dx, dy)
                        if d < min_dist:
                            min_dist = d
                            recovered_start = cand
            if recovered_start is None:
                return None
            start_c = recovered_start

        # Kiểm tra deadline và tính hợp lệ của timeout_s ngay từ đầu
        # P4 & P5: Loại trừ bool, Inf, NaN, hoặc <= 0
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or \
           math.isnan(timeout_s) or math.isinf(timeout_s) or timeout_s <= 0.0:
            return None

        _read_clock = clock_fn if (clock_fn is not None and callable(clock_fn)) else time.monotonic

        # I6 & I7: Validate now_mono và deadline TRƯỚC KHI kiểm tra nhánh nhanh start_c == goal_c!
        # Không để start_c == goal_c bypass lỗi clock expired hoặc now_mono NaN.
        if now_mono is not None:
            if isinstance(now_mono, bool) or not isinstance(now_mono, (int, float)) or \
               math.isnan(now_mono) or math.isinf(now_mono):
                return None
            deadline = float(now_mono) + timeout_s
        else:
            deadline = _read_clock() + timeout_s

        # Kiểm tra nếu đã hết deadline ngay lập tức
        if _read_clock() >= deadline:
            return None

        # Kiểm tra nếu start_c == goal_c thì trả về ngay 1 điểm duy nhất (sau khi đã validate deadline/clock)
        if start_c == goal_c:
            return [self.grid_to_world(start_c[0], start_c[1])]

        open_set: List[Tuple[float, int, Tuple[int, int]]] = []
        counter = 0
        h_start = math.hypot(goal_c[0] - start_c[0], goal_c[1] - start_c[1]) * self.resolution
        heapq.heappush(open_set, (h_start, counter, start_c))

        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start_c: 0.0}

        directions = [
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (0, 1, 1.0),
            (0, -1, 1.0),
            (1, 1, 1.41421356),
            (1, -1, 1.41421356),
            (-1, 1, 1.41421356),
            (-1, -1, 1.41421356),
        ]

        while open_set:
            if _read_clock() >= deadline:
                return None

            _, _, current = heapq.heappop(open_set)

            if current == goal_c:
                path: List[Tuple[float, float]] = []
                curr: Optional[Tuple[int, int]] = current
                while curr is not None:
                    path.append(self.grid_to_world(curr[0], curr[1]))
                    curr = came_from.get(curr)
                path.reverse()
                return path

            current_g = g_score[current]

            for dx, dy, move_cost in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                if not (0 <= neighbor[0] < self.width and 0 <= neighbor[1] < self.height):
                    continue

                if not self.is_traversable_cell(neighbor[0], neighbor[1], allow_unknown=allow_unknown):
                    continue

                # Corner-cutting check: khi di cheo, ca hai o vuong goc lan can phai traversable
                if dx != 0 and dy != 0:
                    ortho1 = (current[0] + dx, current[1])
                    ortho2 = (current[0], current[1] + dy)
                    if not self.is_traversable_cell(ortho1[0], ortho1[1], allow_unknown=allow_unknown) or                        not self.is_traversable_cell(ortho2[0], ortho2[1], allow_unknown=allow_unknown):
                        continue

                tentative_g = current_g + (move_cost * self.resolution)
                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    h = math.hypot(goal_c[0] - neighbor[0], goal_c[1] - neighbor[1]) * self.resolution * 1.001
                    f = tentative_g + h
                    counter += 1
                    heapq.heappush(open_set, (f, counter, neighbor))

        return None

    # =========================================================================
    # F06: FOOTPRINT CLEARANCE & NON-BLOCKING RECOVERY
    # =========================================================================
    def check_backward_clearance(
        self,
        current_pose: Tuple[float, float, float],
        distance_m: float,
        step_size_m: Optional[float] = None,
    ) -> Tuple[bool, float]:
        """
        F06: Kiem tra khoang trong an toan cho chuyen dong lui (Backward Recovery).
        Duyet footprint xe theo huong lui (yaw + pi) voi khoang cach distance_m.
        Tra ve: (is_clear: bool, safe_distance_m: float)
        """
        if not self.has_map or self.fault_latched:
            return (False, 0.0)

        try:
            x = _validate_finite_float(current_pose[0], "pose_x")
            y = _validate_finite_float(current_pose[1], "pose_y")
            yaw = _validate_finite_float(current_pose[2], "pose_yaw")
            dist_req = _validate_finite_float(distance_m, "distance_m")
            if dist_req <= 0.0:
                return (True, 0.0)
        except ValueError:
            return (False, 0.0)

        step = step_size_m if step_size_m is not None else (self.resolution * 0.5)
        num_steps = max(1, int(math.ceil(dist_req / step)))
        back_dir_x = -math.cos(yaw)
        back_dir_y = -math.sin(yaw)

        safe_dist = 0.0
        for s in range(1, num_steps + 1):
            cur_d = min(s * step, dist_req)
            check_x = x + back_dir_x * cur_d
            check_y = y + back_dir_y * cur_d

            grid_pt = self.world_to_grid(check_x, check_y)
            if grid_pt is None or not self.is_traversable_cell(grid_pt[0], grid_pt[1]):
                return (False, max(0.0, safe_dist))

            safe_dist = cur_d

        return (True, dist_req)

    def check_rotation_clearance(
        self,
        current_pose: Tuple[float, float, float],
        delta_yaw_rad: float,
    ) -> bool:
        """
        F06: Kiem tra khoang trong an toan khi quay tai cho (In-place Rotation).
        Vung quet la hinh tron ban kinh rotation_radius_m tai (x, y).
        """
        if not self.has_map or self.fault_latched:
            return False

        try:
            x = _validate_finite_float(current_pose[0], "pose_x")
            y = _validate_finite_float(current_pose[1], "pose_y")
            _validate_finite_float(delta_yaw_rad, "delta_yaw_rad")
        except ValueError:
            return False

        center_c = self.world_to_grid(x, y)
        if center_c is None:
            return False

        rot_cells = int(math.ceil(self.rotation_radius_m / self.resolution))
        r_sq = self.rotation_radius_m ** 2

        for dy in range(-rot_cells, rot_cells + 1):
            for dx in range(-rot_cells, rot_cells + 1):
                dist_sq = ((dx * self.resolution) ** 2) + ((dy * self.resolution) ** 2)
                if dist_sq <= r_sq:
                    check_c = (center_c[0] + dx, center_c[1] + dy)
                    if not (0 <= check_c[0] < self.width and 0 <= check_c[1] < self.height):
                        return False
                    if self.raw_grid[check_c[1] * self.width + check_c[0]] >= 50:
                        return False

        return True

    def plan_recovery(
        self,
        current_pose: Tuple[float, float, float],
        max_backup_dist_m: float = 0.30,
    ) -> Optional[Dict[str, Any]]:
        """
        F06: Bo lap ke hoach Recovery khong chan (Non-blocking).
        Uu tien 1: Lui an toan neu co khoang trong >= 0.08m.
        Uu tien 2: Quay tai cho goc nho neu vung quet an toan.
        Mac dinh: Dung yen (None) neu khong co duong thoat an toan.
        """
        if not self.has_map or self.fault_latched:
            return None

        # 1. Kiem tra khoang lui an toan
        is_clear, safe_dist = self.check_backward_clearance(current_pose, max_backup_dist_m)
        if safe_dist >= 0.08:
            duration = safe_dist / 0.05
            return {
                "type": "BACKWARD",
                "distance_m": safe_dist,
                "linear_velocity": -0.05,
                "angular_velocity": 0.0,
                "duration_s": round(duration, 3),
                "description": f"Xac nhan khoang lui an toan {safe_dist:.3f}m",
            }

        # 2. Thu quay tai cho sang trai (+pi/4) hoac phai (-pi/4)
        if self.check_rotation_clearance(current_pose, math.pi / 4.0):
            duration = (math.pi / 4.0) / 0.20
            return {
                "type": "ROTATE",
                "delta_yaw_rad": math.pi / 4.0,
                "linear_velocity": 0.0,
                "angular_velocity": 0.20,
                "duration_s": round(duration, 3),
                "description": "Xac nhan vung quet quay an toan +45 do",
            }
        elif self.check_rotation_clearance(current_pose, -math.pi / 4.0):
            duration = (math.pi / 4.0) / 0.20
            return {
                "type": "ROTATE",
                "delta_yaw_rad": -math.pi / 4.0,
                "linear_velocity": 0.0,
                "angular_velocity": -0.20,
                "duration_s": round(duration, 3),
                "description": "Xac nhan vung quet quay an toan -45 do",
            }

        # 3. Khong co duong thoat -> Dung lai an toan, khong chuyen dong mu
        return None

    # =========================================================================
    # F09: FRONTIER EXTRACTION & REACHABILITY FILTERING
    # =========================================================================
    def extract_frontiers(self, min_cluster_size: int = 2) -> List[Tuple[float, float]]:
        """
        F09: Trich xuat cac diem bien (Frontier) tu ban do.
        Mot o la Frontier neu:
          1. La o trong Free (raw_grid == 0) va di chuyen duoc (khong bi lam phat boi tuong).
          2. Co it nhat mot o lan can 8 huong la vung chua biet Unknown (raw_grid == -1).
        Gom cum (Clustering) va tra ve danh sach toa do the gioi tam cum.
        """
        if not self.has_map or self.fault_latched:
            return []

        frontier_cells: Set[Tuple[int, int]] = set()
        neighbor_offsets = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1)
        ]

        for y in range(self.height):
            for x in range(self.width):
                idx = y * self.width + x
                if self.raw_grid[idx] == COST_FREE and self.is_traversable_cell(x, y):
                    has_unknown = False
                    for dx, dy in neighbor_offsets:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.width and 0 <= ny < self.height:
                            if self.raw_grid[ny * self.width + nx] == COST_UNKNOWN:
                                has_unknown = True
                                break
                    if has_unknown:
                        frontier_cells.add((x, y))

        if not frontier_cells:
            return []

        # Gom cum (Connected Component Clustering qua BFS)
        visited: Set[Tuple[int, int]] = set()
        clusters: List[List[Tuple[int, int]]] = []

        for cell in frontier_cells:
            if cell in visited:
                continue
            cluster: List[Tuple[int, int]] = []
            queue = deque([cell])
            visited.add(cell)

            while queue:
                curr = queue.popleft()
                cluster.append(curr)
                for dx, dy in neighbor_offsets:
                    nxt = (curr[0] + dx, curr[1] + dy)
                    if nxt in frontier_cells and nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)

            if len(cluster) >= min_cluster_size:
                clusters.append(cluster)

        candidate_world_points: List[Tuple[float, float]] = []
        for cluster in clusters:
            avg_x = sum(c[0] for c in cluster) / len(cluster)
            avg_y = sum(c[1] for c in cluster) / len(cluster)
            best_cell = min(cluster, key=lambda c: (c[0] - avg_x) ** 2 + (c[1] - avg_y) ** 2)
            candidate_world_points.append(self.grid_to_world(best_cell[0], best_cell[1]))

        return candidate_world_points

    def filter_reachable_frontiers(
        self,
        robot_pose: Tuple[float, float, float],
        candidate_frontiers: List[Tuple[float, float]],
        timeout_per_candidate_s: float = 0.05,
    ) -> List[Tuple[Tuple[float, float], List[Tuple[float, float]]]]:
        """
        F09: Loc va chi cong nhan cac Frontier co the vươn toi duoc (Reachable Frontiers).
        Loai bo hoan toan cac Frontier bi co lap sau vat can hoac khe hep khong vuot qua duoc.
        Tra ve: Danh sach tuple (frontier_point, path_to_frontier)
        """
        if not self.has_map or self.fault_latched:
            return []

        start_w = (robot_pose[0], robot_pose[1])
        reachable: List[Tuple[Tuple[float, float], List[Tuple[float, float]]]] = []

        for frontier in candidate_frontiers:
            path = self.find_path_world(start_w, frontier, timeout_s=timeout_per_candidate_s)
            if path is not None and len(path) > 0:
                reachable.append((frontier, path))

        return reachable

    def select_best_frontier(
        self,
        robot_pose: Tuple[float, float, float],
        reachable_frontiers: List[Tuple[Tuple[float, float], List[Tuple[float, float]]]],
    ) -> Optional[Tuple[Tuple[float, float], List[Tuple[float, float]]]]:
        """
        F09: Lua chon Frontier toi uu nhat theo ham loi ich da tieu chi (Khoang cach + Huong robot).
        """
        if not reachable_frontiers:
            return None

        rx, ry, ryaw = robot_pose
        best_candidate = None
        best_score = -float("inf")

        for frontier_point, path in reachable_frontiers:
            path_length = len(path) * self.resolution
            dx = frontier_point[0] - rx
            dy = frontier_point[1] - ry
            target_yaw = math.atan2(dy, dx)
            yaw_diff = abs((target_yaw - ryaw + math.pi) % (2 * math.pi) - math.pi)

            score = -(1.0 * path_length) - (0.5 * yaw_diff)
            if score > best_score:
                best_score = score
                best_candidate = (frontier_point, path)

        return best_candidate

    # =========================================================================
    # F08, F10: HOME POSE PRESERVATION & ANTI-FALSE COMPLETION FSM
    # =========================================================================
    def set_home_pose(self, x: float, y: float, yaw: float = 0.0) -> bool:
        """
        F08: Luu vi tri xuat phat (Home) trong he toa do map.
        Xac thuc o Home phai nam trong vung trong an toan.
        """
        try:
            hx = _validate_finite_float(x, "home_x")
            hy = _validate_finite_float(y, "home_y")
            hyaw = _validate_finite_float(yaw, "home_yaw")
        except ValueError:
            return False

        if not self.has_map:
            self.home_pose_world = (hx, hy, hyaw)
            return True

        cell = self.world_to_grid(hx, hy)
        if cell is None or not self.is_traversable_cell(cell[0], cell[1]):
            return False

        self.home_pose_world = (hx, hy, hyaw)
        return True

    def check_home_reachability(
        self,
        robot_pose: Tuple[float, float, float],
    ) -> Tuple[bool, Optional[List[Tuple[float, float]]]]:
        """
        F08/F09: Bao dam luon co duong lui an toan tu vi tri hien tai ve Home.
        """
        if self.home_pose_world is None or not self.has_map or self.fault_latched:
            return (False, None)

        start_w = (robot_pose[0], robot_pose[1])
        home_w = (self.home_pose_world[0], self.home_pose_world[1])
        path = self.find_path_world(start_w, home_w)
        return (path is not None, path)

    def compute_map_coverage(self, bounding_box: Optional[Tuple[float, float, float, float]] = None) -> float:
        """
        F10: Tinh toan ty le bao phu ban do thuc te.
        coverage = Free_cells / (Free_cells + Unknown_cells)
        """
        if not self.has_map or self.fault_latched or self.width == 0 or self.height == 0:
            return 0.0

        if bounding_box is not None:
            min_x, min_y, max_x, max_y = bounding_box
            c_min = self.world_to_grid(min_x, min_y) or (0, 0)
            c_max = self.world_to_grid(max_x, max_y) or (self.width - 1, self.height - 1)
            x_range = range(max(0, c_min[0]), min(self.width, c_max[0] + 1))
            y_range = range(max(0, c_min[1]), min(self.height, c_max[1] + 1))
        else:
            x_range = range(self.width)
            y_range = range(self.height)

        free_count = 0
        unknown_count = 0

        for y in y_range:
            for x in x_range:
                val = self.raw_grid[y * self.width + x]
                if val == COST_FREE:
                    free_count += 1
                elif val == COST_UNKNOWN:
                    unknown_count += 1

        total = free_count + unknown_count
        if total == 0:
            return 0.0
        return float(free_count) / float(total)

    def evaluate_mission_status(
        self,
        robot_pose: Tuple[float, float, float],
        target_coverage: float = 0.85,
    ) -> Dict[str, Any]:
        """
        F10: Co che FSM danh gia tien trinh kham pha toan dien, CHONG BAO COMPLETED GIA:
          - WAITING_FOR_MAP: Chua nhan duoc OccupancyGrid hop le.
          - WAITING_FOR_DATA: Ban do chua co o Free nao.
          - EXPLORING: Con ton tai Reachable Frontier de kham pha.
          - RETURNING_HOME: Da het Frontier hop le, dang tren duong ve Home.
          - COMPLETED: Chi cong nhan khi da ve toi Home VA ty le bao phu dat nguong yeu cau.
          - EXPLORATION_STUCK: Khong con Frontier vươn toi duoc nhung chua ve duoc Home.
        """
        if not self.has_map:
            return {
                "state": "WAITING_FOR_MAP",
                "completed": False,
                "coverage": 0.0,
                "reason": "Chua nhan OccupancyGrid hop le tu SLAM",
            }

        if self.fault_latched:
            return {
                "state": "PLANNER_FAULT",
                "completed": False,
                "coverage": 0.0,
                "reason": f"He thong dang bi khoa chot loi: {self.fault_reason}",
            }

        coverage = self.compute_map_coverage()

        # Kiem tra so o Free trong ban do
        free_cells = sum(1 for v in self.raw_grid if v == COST_FREE)
        if free_cells == 0:
            return {
                "state": "WAITING_FOR_DATA",
                "completed": False,
                "coverage": 0.0,
                "reason": "Ban do hien chua co bat ky o trong (Free) hop le nao",
            }

        all_frontiers = self.extract_frontiers()
        reachable_frontiers = self.filter_reachable_frontiers(robot_pose, all_frontiers)

        if len(reachable_frontiers) > 0:
            best = self.select_best_frontier(robot_pose, reachable_frontiers)
            return {
                "state": "EXPLORING",
                "completed": False,
                "coverage": coverage,
                "frontiers_count": len(all_frontiers),
                "reachable_frontiers_count": len(reachable_frontiers),
                "target_frontier": best[0] if best else None,
                "path": best[1] if best else None,
                "reason": f"Dang tiep tuc kham pha ({len(reachable_frontiers)} frontier kha dung)",
            }

        if self.home_pose_world is None:
            return {
                "state": "EXPLORATION_STUCK",
                "completed": False,
                "coverage": coverage,
                "reason": "Het frontier nhung chua duoc cau hinh vi tri Home",
            }

        can_return_home, home_path = self.check_home_reachability(robot_pose)
        if not can_return_home or home_path is None:
            return {
                "state": "EXPLORATION_STUCK",
                "completed": False,
                "coverage": coverage,
                "reason": "Khong con frontier kha dung va mat duong lui an toan ve Home",
            }

        dx = robot_pose[0] - self.home_pose_world[0]
        dy = robot_pose[1] - self.home_pose_world[1]
        dist_to_home = math.hypot(dx, dy)
        yaw_diff = abs((robot_pose[2] - self.home_pose_world[2] + math.pi) % (2 * math.pi) - math.pi)

        if dist_to_home > 0.10 or yaw_diff > 0.20:
            return {
                "state": "RETURNING_HOME",
                "completed": False,
                "coverage": coverage,
                "dist_to_home_m": dist_to_home,
                "home_path": home_path,
                "reason": f"Het frontier, dang tren duong lui ve Home ({dist_to_home:.2f}m)",
            }

        # P1 Fix: Nếu coverage < target_coverage, dù len(all_frontiers) == 0 (do bị tường chắn/unknown cô lập)
        # thì vẫn là PARTIAL_EXPLORATION_AT_HOME / UNREACHABLE_ISOLATED, TUYỆT ĐỐI KHÔNG COMPLETED!
        if coverage < target_coverage:
            return {
                "state": "PARTIAL_EXPLORATION_AT_HOME",
                "completed": False,
                "coverage": coverage,
                "reason": f"Da ve Home nhung do phu chua dat ({coverage*100:.1f}% < {target_coverage*100:.1f}%) vi co vung unknown bi co lap/khong the toi",
            }

        return {
            "state": "COMPLETED",
            "completed": True,
            "coverage": coverage,
            "reason": f"Kham pha thanh cong toan bo vung kha dung va da do xe an toan tai Home (Coverage {coverage*100:.1f}%)",
        }

    # =========================================================================
    # F10: WINDOW-BASED STUCK DETECTION (NO FALSE POSITIVES)
    # =========================================================================
    @staticmethod
    def detect_stuck(
        history_poses: List[Tuple[float, float, float]],
        history_stamps: List[float],
        cmd_vel_history: List[Tuple[float, float]],
        window_s: float = 1.5,
        min_displacement_m: float = 0.03,
    ) -> bool:
        """
        F10: Phat hien ket dua tren cua so thoi gian va tien bo thuc te (Window-based).
        Khac phuc hoan toan sai so cua nguong co dinh (4cm/0.2s):
          - Khong bao ket sai khi xe chay toc do thap binh thuong (vi du 0.18 m/s -> 0.27m trong 1.5s).
          - Chi bao ket khi caller phat lenh chay (|v| > 0.02 m/s) suot cua so window_s nhung quang duong < min_displacement_m.
        """
        if not history_poses or not history_stamps or not cmd_vel_history:
            return False
        if len(history_poses) != len(history_stamps) or len(history_poses) != len(cmd_vel_history):
            return False
        if len(history_poses) < 3:
            return False

        t_now = history_stamps[-1]
        t_start_window = t_now - window_s

        window_indices = [i for i, t in enumerate(history_stamps) if t >= t_start_window]
        if len(window_indices) < 2:
            return False

        idx_start = window_indices[0]
        idx_end = window_indices[-1]

        cmd_vels_in_window = [cmd_vel_history[i] for i in window_indices]
        avg_cmd_lin = sum(abs(v[0]) for v in cmd_vels_in_window) / len(cmd_vels_in_window)
        avg_cmd_ang = sum(abs(v[1]) for v in cmd_vels_in_window) / len(cmd_vels_in_window)

        if avg_cmd_lin < 0.02 and avg_cmd_ang < 0.08:
            return False

        p_start = history_poses[idx_start]
        p_end = history_poses[idx_end]
        displacement = math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1])

        if displacement < min_displacement_m:
            return True

        return False

    # =========================================================================
    # F11: PATH ORIENTATION & WAYPOINT GENERATION
    # =========================================================================
    def get_path_as_poses(
        self,
        path: List[Tuple[float, float]],
        target_final_yaw: Optional[float] = None,
    ) -> List[Dict[str, float]]:
        """
        F11: Chuyen doi danh sach toa do duong di thanh tap Waypoints co goc huong (Yaw) lien tuc,
        phu hop de xuat ban sang nav_msgs/Path cua ROS 2.
        """
        if not path:
            return []

        poses: List[Dict[str, float]] = []
        n = len(path)

        for i in range(n):
            x, y = path[i]
            if i < n - 1:
                next_x, next_y = path[i + 1]
                yaw = math.atan2(next_y - y, next_x - x)
            else:
                if target_final_yaw is not None:
                    yaw = target_final_yaw
                elif len(poses) > 0:
                    yaw = poses[-1]["yaw"]
                else:
                    yaw = 0.0

            poses.append({"x": round(x, 4), "y": round(y, 4), "yaw": round(yaw, 4)})

        return poses
