import rclpy
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener

rclpy.init()
node = Node('check_tf_laser')
buf = Buffer()
tl = TransformListener(buf, node)
import time
for i in range(30):
    rclpy.spin_once(node, timeout_sec=0.1)
    try:
        t = buf.lookup_transform('base_footprint', 'laser', Time())
        stamp = t.header.stamp.sec + t.header.stamp.nanosec * 1e-9
        now = node.get_clock().now().nanoseconds * 1e-9
        diff = now - stamp
        print(f"SUCCESS! stamp={stamp}, now={now}, diff={diff}")
        print("Would raise 'Stale scan TF'?", bool(stamp and not (0 <= diff <= 0.25)))
        break
    except Exception as e:
        pass
else:
    print("FAILED TO LOOKUP!")
