import rclpy
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener

rclpy.init()
node = Node('check_tf_stamp')
buf = Buffer()
tl = TransformListener(buf, node)
for _ in range(25):
    rclpy.spin_once(node, timeout_sec=0.1)
    if buf.can_transform('base_footprint', 'laser', Time()):
        break

t = buf.lookup_transform('base_footprint', 'laser', Time())
stamp = t.header.stamp.sec + t.header.stamp.nanosec * 1e-9
now = node.get_clock().now().nanoseconds * 1e-9
diff = now - stamp
print(f"TF stamp: {stamp:.3f}, now: {now:.3f}, diff: {diff:.3f}")
print("Is diff > 0.25?", diff > 0.25)
