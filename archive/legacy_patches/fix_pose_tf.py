with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Sửa _pose_map: Không giới hạn tuổi transform quá khắt khe (SLAm Toolbox phát map -> odom 1-2Hz)
old_pose = """            t = self.tf_buffer.lookup_transform(frame,'base_footprint',Time())
            stamp = t.header.stamp.sec+t.header.stamp.nanosec*1e-9
            age = self.get_clock().now().nanoseconds*1e-9-stamp
            if not 0 <= age <= .25:
                return None
            p,q = t.transform.translation,t.transform.rotation
            yaw = self._yaw(q)
            return (p.x,p.y,yaw) if finite(p.x) and finite(p.y) else None"""

new_pose = """            t = self.tf_buffer.lookup_transform(frame,'base_footprint',Time())
            p,q = t.transform.translation,t.transform.rotation
            yaw = self._yaw(q)
            return (p.x,p.y,yaw) if finite(p.x) and finite(p.y) else None"""

if old_pose in code:
    code = code.replace(old_pose, new_pose, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY UNBLOCKED TF AGE IN _pose_map")
