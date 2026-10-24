"""Offline-testable adapters between learned policies and the AGV navigator.

The bridge does not open serial devices or command motors. In particular,
the local planner's filtered zero-velocity command must remain a STOP.
"""

import math


def ai1_prepare_scan(ranges, max_gap=2, max_missing=36):
    """Fill only tiny (<=2 degree) LiDAR sampling holes for AI1.

    Zero/non-finite bins are unobserved, not a measured collision or free
    space. Conservatively copy the nearer observed neighbor into tiny holes;
    reject wide or excessive gaps before inference. Motor safety remains
    enforced by the independent controller.
    """
    try:
        scan = [float(v) for v in ranges]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid AI1 LiDAR frame') from exc
    if len(scan) != 360 or not 0 <= max_gap <= 3 or not 0 <= max_missing <= 36:
        raise ValueError('Invalid AI1 LiDAR dimensions/limits')
    # The ROS aggregator uses 16.0 for an unobserved LiDAR bin. It is not
    # evidence of 12m of free space: feeding it to the learned policy would
    # fabricate clear rays in blind sectors.
    valid = [math.isfinite(v) and .05 <= v < 16.0 for v in scan]
    missing = len(scan) - sum(valid)
    if missing > max_missing or not any(valid):
        raise ValueError('AI1_LIDAR_INSUFFICIENT_COVERAGE')
    scan = [min(v, 12.0) if good else 0.0 for v, good in zip(scan, valid)]
    start = valid.index(True)
    i = (start + 1) % 360
    while i != start:
        if valid[i]:
            i = (i + 1) % 360
            continue
        gap = []
        while not valid[i]:
            gap.append(i)
            if len(gap) > max_gap:
                raise ValueError('AI1_LIDAR_UNOBSERVED_SECTOR')
            i = (i + 1) % 360
        conservatively_near = min(scan[(gap[0] - 1) % 360], scan[i])
        for k in gap:
            scan[k] = conservatively_near
        if i != start:
            i = (i + 1) % 360
    return scan


def measured_twist(telemetry):
    """Use measured ESP32 velocities rather than an always-zero placeholder."""
    if not isinstance(telemetry, dict):
        return 0.0, 0.0
    try:
        v, w = float(telemetry['v']), float(telemetry['w'])
    except (KeyError, TypeError, ValueError):
        return 0.0, 0.0
    return (v, w) if math.isfinite(v) and math.isfinite(w) else (0.0, 0.0)


def ai1_velocity(filtered_action, cruise_speed, turn_limit):
    """Respect the ONNX runtime's safety-filtered m/s and rad/s commands.

    Never impose a forward speed floor or slew a commanded emergency zero.
    The existing command writer remains the final motion/geometry arbiter.
    """
    try:
        if len(filtered_action) != 2:
            raise ValueError('AI1 action must contain v and w')
        v, w = (float(x) for x in filtered_action)
        cruise_speed, turn_limit = float(cruise_speed), float(turn_limit)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid AI1 action') from exc
    if not all(map(math.isfinite, (v, w, cruise_speed, turn_limit))):
        raise ValueError('Non-finite AI1 action or limits')
    if v < 0 or cruise_speed < 0 or turn_limit < 0:
        raise ValueError('Negative AI1 forward speed or limits')
    if v == 0.0 and w == 0.0:
        return 0.0, 0.0
    return min(v, cruise_speed, 0.35), max(-min(turn_limit, 1.5), min(min(turn_limit, 1.5), w))


def ai2_action_direction(action):
    """Grid training uses row 0 at the top; ROS map +Y is physically up."""
    return ((0.0, 1.0), (0.0, -1.0), (-1.0, 0.0), (1.0, 0.0))[action]


def ai2_valid_action_mask(grid, start_cell):
    """Training's four cardinal actions, gated by the inflated ROS costmap."""
    if start_cell is None:
        return (False,) * 4
    x, y = start_cell
    return tuple(bool(grid.traversable((x + dx, y + dy)))
                 for dx, dy in ((0, 1), (0, -1), (-1, 0), (1, 0)))


def ai2_ranked_candidates(candidates, q_values, rx, ry, map_yaw=0.0,
                          valid_actions=None):
    """Give a finite, four-action AI2 policy a bounded directional vote."""
    try:
        values = [float(x) for x in q_values]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid AI2 Q-values') from exc
    if len(values) != 4 or not all(map(math.isfinite, values)):
        raise ValueError('AI2 requires four finite Q-values')
    if not math.isfinite(map_yaw):
        raise ValueError('Invalid map yaw')
    mask = (True,) * 4 if valid_actions is None else tuple(valid_actions)
    if len(mask) != 4 or not any(mask):
        raise ValueError('AI2 has no safe cardinal action')
    action = max((i for i in range(4) if mask[i]), key=lambda i: values[i])
    dx, dy = ai2_action_direction(action)
    c, s = math.cos(map_yaw), math.sin(map_yaw)
    dx, dy = c * dx - s * dy, s * dx + c * dy
    ranked = sorted(candidates, key=lambda c: c[0] - 0.5 * (
        (c[1][0] - rx) * dx + (c[1][1] - ry) * dy))
    return action, ranked


def reproject_visited_cells(cells, old_map, new_map, new_data):
    """Keep physical coverage attached to the world when a ROS grid resizes.

    Map metadata: (frame, width, height, resolution, origin_x, origin_y,
    origin_yaw). A different TF frame cannot be converted without TF lookup.
    Previously visited cells which become occupied/unknown are discarded.
    """
    old_frame, _, _, old_res, old_x, old_y, old_yaw = old_map
    new_frame, width, height, new_res, new_x, new_y, new_yaw = new_map
    if old_frame != new_frame or not old_frame or len(new_data) != width * height:
        return set()
    oc, os = math.cos(old_yaw), math.sin(old_yaw)
    nc, ns = math.cos(new_yaw), math.sin(new_yaw)
    out = set()
    for x, y in cells:
        a, b = (x + .5) * old_res, (y + .5) * old_res
        wx, wy = old_x + oc * a - os * b, old_y + os * a + oc * b
        dx, dy = wx - new_x, wy - new_y
        cx = math.floor((nc * dx + ns * dy) / new_res)
        cy = math.floor((-ns * dx + nc * dy) / new_res)
        if (0 <= cx < width and 0 <= cy < height and
                new_data[cy * width + cx] == 0):
            out.add((cx, cy))
    return out


def ai2_observation(grid, start_cell, candidates, visited_cells, robot_xy,
                    world_yaw, no_progress_steps, free_cell_count):
    """Convert ROS coordinates to the 3x9x9 + 8-feature training convention.

    Returns None when no path-backed target is available. The 32x32 training
    grid uses a 64-step normalized geodesic distance and 100-step stall scale.
    This fixes coordinate/feature mismatch but does not prove sim-to-real.
    """
    import numpy as np

    cx, cy = start_cell
    rx, ry = robot_xy
    patch = np.zeros((3, 9, 9), dtype=np.float32)
    for row in range(9):
        for col in range(9):
            cell = (cx + col - 4, cy + 4 - row)  # north is top row
            if not grid.traversable(cell):
                patch[1, row, col] = 1.0
            elif cell in visited_cells:
                patch[2, row, col] = 1.0
            else:
                patch[0, row, col] = 1.0

    path = None
    for _, target in sorted(candidates, key=lambda item: item[0])[:5]:
        path = grid.path((rx, ry), target)
        if path is not None and len(path) > 1:
            break
    if not path or len(path) < 2:
        return None

    map_yaw = float(getattr(grid, 'origin', (0., 0., 0.))[2])
    step_x = path[1][0] - path[0][0]
    step_y = path[1][1] - path[0][1]
    c, s = math.cos(map_yaw), math.sin(map_yaw)
    step_x, step_y = c * step_x + s * step_y, -s * step_x + c * step_y
    # Project an 8-connected A* first step onto the 4-way training action space.
    if abs(step_x) >= abs(step_y):
        path_dx, path_dy = (1.0 if step_x >= 0 else -1.0), 0.0
    else:
        path_dx, path_dy = 0.0, (-1.0 if step_y > 0 else 1.0)
    grid_yaw = map_yaw - world_yaw
    features = np.array([
        path_dx, path_dy, min(1.0, (len(path) - 1) / 64.0), 1.0,
        math.sin(grid_yaw), math.cos(grid_yaw),
        min(1.0, len(visited_cells) / max(1, free_cell_count)),
        min(1.0, max(0, no_progress_steps) / 100.0),
    ], dtype=np.float32)
    return patch, features
