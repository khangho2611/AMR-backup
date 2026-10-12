target = '/home/khangho/rplidar_c1_test/bridge/agv_unified_brain.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Thêm import geometry_msgs TransformStamped và tf2_ros
tf_import = """from nav_msgs.msg import OccupancyGrid, Odometry
from geometry_msgs.msg import TransformStamped, Quaternion
from tf2_ros import TransformBroadcaster"""

if 'TransformBroadcaster' not in code:
    code = code.replace("from nav_msgs.msg import OccupancyGrid", tf_import)

# 2. Thêm broadcaster vào __init__ của AGVROSNode
tf_init = """        self.create_subscription(OccupancyGrid, '/map', self.map_cb, qos_map)

        # 3.1 TF Broadcaster để phát liên tục odom -> base_link -> laser
        self.tf_broadcaster = TransformBroadcaster(self)
        self.create_timer(0.05, self.broadcast_tf) # 20Hz"""

if 'self.tf_broadcaster' not in code:
    code = code.replace("self.create_subscription(OccupancyGrid, '/map', self.map_cb, qos_map)", tf_init)

# 3. Hàm broadcast_tf
tf_func = """    def broadcast_tf(self):
        with state.lock:
            rx = state.robot_x
            ry = state.robot_y
            rth = state.robot_th

        now = self.get_clock().now().to_msg()

        # TF 1: odom -> base_footprint
        t1 = TransformStamped()
        t1.header.stamp = now
        t1.header.frame_id = 'odom'
        t1.child_frame_id = 'base_footprint'
        t1.transform.translation.x = rx
        t1.transform.translation.y = ry
        t1.transform.translation.z = 0.0
        # Quaternion từ Yaw theta
        t1.transform.rotation.z = math.sin(rth / 2.0)
        t1.transform.rotation.w = math.cos(rth / 2.0)
        self.tf_broadcaster.sendTransform(t1)

        # TF 2: base_footprint -> laser
        t2 = TransformStamped()
        t2.header.stamp = now
        t2.header.frame_id = 'base_footprint'
        t2.child_frame_id = 'laser'
        t2.transform.translation.x = 0.05
        t2.transform.translation.y = 0.0
        t2.transform.translation.z = 0.12
        t2.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t2)

    def scan_cb(self, msg):"""

if 'def broadcast_tf(self):' not in code:
    code = code.replace("    def scan_cb(self, msg):", tf_func)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

import py_compile
py_compile.compile(target, doraise=True)
print("SUCCESSFULLY INJECTED TF BROADCASTER FOR SLAM TOOLBOX!")
