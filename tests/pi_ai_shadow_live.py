"""Read-only ROS 2 shadow probe for a stationary AGV.

No controller import, UART access, motion API, ROS publisher or motor commands.
Subscribes to /scan and /map and reads TF; map-based AI2 requires a real map pose.
Without a fresh TF pose, AI1 uses a LABELLED fixed-goal synthetic pose probe;
do not interpret the result as robot navigation or obstacle avoidance acceptance.

Example (after sourcing ROS 2 Jazzy):
  PYTHONPATH="$PWD:/path/to/model/root" python3 -B tests/pi_ai_shadow_live.py \
    --model-root /path/to/model/root --duration 20 --output scan_shadow.jsonl
"""

import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np


def rasterize_scan(ranges, angle_min, angle_increment, range_min, range_max):
    """Nearest valid return per CCW robot-forward degree. Missing bins block.

    This is a conservative read-only probe assuming zero sensor mount yaw.
    The production controller uses a separate TF-aware LaserScan transform.
    """
    if (not math.isfinite(angle_min) or not math.isfinite(angle_increment) or
            angle_increment == 0 or not 0 <= range_min < range_max or
            not math.isfinite(range_min) or not math.isfinite(range_max)):
        raise ValueError('Invalid scan geometry')
    scan = np.full(360, .12, dtype=np.float64)
    seen = np.zeros(360, dtype=np.bool_)
    valid = 0
    for i, value in enumerate(ranges):
        # +inf is a no-return ray. NaN, -inf, too-close and negative are invalid.
        if value == math.inf:
            value = range_max
        if not math.isfinite(value) or value < range_min or value > range_max:
            continue
        deg = round(math.degrees(angle_min + i * angle_increment)) % 360
        value = float(np.clip(value, .12, 12.))
        if not seen[deg] or value < scan[deg]:
            scan[deg] = value
        seen[deg] = True
        valid += 1
    return scan, int(seen.sum()), valid


def percentile(values, p):
    return round(float(np.percentile(values, p)), 4) if values else None


def summarize(events):
    scans = [e for e in events if e.get('event') == 'scan']
    lat = [e['ai1_latency_ms'] for e in scans if e.get('ai1_latency_ms') is not None]
    modes = sorted({e.get('pose_source', '?') for e in scans})
    return dict(
        scans=len(scans), inference_count=len(lat),
        lidar_bins_min=min((e['observed_bins'] for e in scans), default=None),
        lidar_bins_max=max((e['observed_bins'] for e in scans), default=None),
        min_obstacle_m=min((e['min_obstacle_m'] for e in scans
                            if e['min_obstacle_m'] is not None), default=None),
        ai1_zero_commands=sum(e.get('ai1_filtered') == [0.0, 0.0] for e in scans),
        ai1_p50_ms=percentile(lat, 50), ai1_p95_ms=percentile(lat, 95),
        ai1_p99_ms=percentile(lat, 99), ai1_max_ms=max(lat) if lat else None,
        pose_sources=modes, map_count=sum(e.get('event') == 'map' for e in events),
        ai2_count=sum(e.get('event') == 'ai2' for e in events),
        map_skips=sum(e.get('event') == 'map_skip' for e in events),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-root', required=True, type=pathlib.Path)
    ap.add_argument('--duration', type=float, default=20.)
    ap.add_argument('--output', required=True, type=pathlib.Path)
    args = ap.parse_args()
    if not 0 < args.duration <= 120:
        raise SystemExit('duration must be in (0,120] s')
    sys.path.insert(0, str(args.model_root.resolve()))
    from ai_local_planner.runtime import LocalPlannerRuntime
    from agv_ai_bridge import ai1_velocity
    from agv_ai_bridge import ai2_observation, ai2_ranked_candidates
    from agv_navigation import GridPlanner

    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
    from rclpy.time import Time
    from sensor_msgs.msg import LaserScan
    from nav_msgs.msg import OccupancyGrid
    from tf2_ros import Buffer, TransformListener
    import onnxruntime as ort

    class Shadow(Node):
        def __init__(self):
            super().__init__('agv_ai_shadow_readonly')
            self.ai1 = LocalPlannerRuntime(args.model_root / 'ai_local_planner/exported/local_planner.onnx')
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            self.ai2 = ort.InferenceSession(str(args.model_root / 'models/coverage_model.onnx'),
                                             sess_options=opts, providers=['CPUExecutionProvider'])
            self.tf_buffer = Buffer()
            self.tf_listener = TransformListener(self.tf_buffer, self)
            self.events = []
            self.last_map_mono = -float('inf')
            qos = QoSProfile(depth=5, reliability=QoSReliabilityPolicy.BEST_EFFORT)
            self.sub = self.create_subscription(LaserScan, '/scan', self.on_scan, qos)
            qos_map = QoSProfile(depth=1,
                                 reliability=QoSReliabilityPolicy.RELIABLE,
                                 durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
            self.sub_map = self.create_subscription(OccupancyGrid, '/map', self.on_map,
                                                    qos_map)

        def emit(self, record):
            self.events.append(record)
            with args.output.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')

        def on_scan(self, msg):
            recv_time = time.time()
            try:
                scan, bins, valid = rasterize_scan(msg.ranges, msg.angle_min,
                                                    msg.angle_increment, msg.range_min,
                                                    msg.range_max)
                measured_rays = [float(r) for r in msg.ranges
                                 if math.isfinite(r) and msg.range_min <= r <= msg.range_max]
                # Deliberately stationary, hypothetical goal 2 m ahead. No odometry.
                t0 = time.perf_counter_ns()
                action = self.ai1.predict_from_sensors(scan, (0., 0., 0.),
                                                        (2., 0.), 0., 0.)
                filtered = ai1_velocity(action, .35, 1.5)
                ms = (time.perf_counter_ns() - t0) / 1e6
                record = dict(event='scan', time_unix=recv_time,
                              frame=msg.header.frame_id, total_rays=len(msg.ranges),
                              valid_rays=valid, observed_bins=bins,
                              missing_bins=360-bins,
                              min_obstacle_m=round(min(measured_rays), 3) if measured_rays else None,
                              ai1_filtered=[round(float(v), 5) for v in filtered],
                              ai1_latency_ms=round(ms, 4),
                              pose_source='synthetic_stationary_goal_2m',
                              **{'actuators_touched': False})
                self.emit(record)
            except Exception as exc:
                self.emit(dict(event='scan_error', time_unix=recv_time,
                               error=f'{type(exc).__name__}: {exc}'))

        def on_map(self, msg):
            # Maps are expensive to inflate; cap this purely observational probe.
            if time.monotonic() - self.last_map_mono < 4.:
                return
            self.last_map_mono = time.monotonic()
            now = time.time()
            try:
                if not msg.header.frame_id or not 0 < msg.info.width * msg.info.height <= 250000:
                    raise ValueError('Invalid map size/frame')
                tf = self.tf_buffer.lookup_transform(msg.header.frame_id,
                                                      'base_footprint', Time())
                x = float(tf.transform.translation.x)
                y = float(tf.transform.translation.y)
                q = tf.transform.rotation
                yaw = math.atan2(2*(q.w*q.z + q.x*q.y),
                                 1-2*(q.y*q.y + q.z*q.z))
                oq = msg.info.origin.orientation
                map_yaw = math.atan2(2*(oq.w*oq.z + oq.x*oq.y),
                                     1-2*(oq.y*oq.y + oq.z*oq.z))
                grid = GridPlanner(int(msg.info.width), int(msg.info.height),
                                   float(msg.info.resolution),
                                   (float(msg.info.origin.position.x),
                                    float(msg.info.origin.position.y), map_yaw),
                                   [int(v) for v in msg.data], .20, .15, budget_s=.75)
                cell = grid.world_to_cell(x, y)
                if not grid.traversable(cell):
                    raise ValueError('Real robot map pose is not in known-clear inflated map')
                candidates = []
                for cy in range(max(0, cell[1]-30), min(grid.h, cell[1]+31)):
                    for cx in range(max(0, cell[0]-30), min(grid.w, cell[0]+31)):
                        if grid.traversable((cx, cy)):
                            xy = grid.cell_to_world(cx, cy)
                            dist = math.hypot(xy[0]-x, xy[1]-y)
                            if .35 <= dist <= 1.5:
                                candidates.append((dist, xy))
                candidates.sort(key=lambda pair: pair[0])
                if not candidates:
                    raise ValueError('No map-backed AI2 candidate')
                t0 = time.perf_counter_ns()
                obs = ai2_observation(grid, cell, candidates, set(), (x, y), yaw,
                                      0, sum(v == 0 for v in msg.data))
                if obs is None:
                    raise ValueError('No reachable AI2 candidate')
                patch, feat = obs
                ins = self.ai2.get_inputs()
                q_values = self.ai2.run(None, {ins[0].name: patch[None],
                                                ins[1].name: feat[None]})[0].reshape(-1)
                action, ranked = ai2_ranked_candidates(candidates, q_values, x, y,
                                                       map_yaw=map_yaw)
                self.emit(dict(event='ai2', time_unix=now, pose_source='live_map_tf',
                               visited_state='unknown_all_assumed_unvisited',
                               map_frame=msg.header.frame_id,
                               pose_map=[round(x, 3), round(y, 3), round(yaw, 3)],
                               candidates=len(candidates), action=int(action),
                               finite_q=True, q_values=q_values.tolist(),
                               ai2_ranked_goal=list(ranked[0][1]),
                               baseline_nearest=list(candidates[0][1]),
                               ai2_pipeline_ms=round((time.perf_counter_ns()-t0)/1e6, 4),
                               actuators_touched=False))
            except Exception as exc:
                self.emit(dict(event='map_skip', time_unix=now,
                               error=f'{type(exc).__name__}: {exc}',
                               actuators_touched=False))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('', encoding='utf-8')
    rclpy.init()
    node = None
    try:
        node = Shadow()
        start = time.monotonic()
        while time.monotonic() - start < args.duration:
            rclpy.spin_once(node, timeout_sec=.3)
        result = dict(event='summary', **summarize(node.events))
        node.emit(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result['scans']:
            raise SystemExit('No /scan messages were received')
    finally:
        if node:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
