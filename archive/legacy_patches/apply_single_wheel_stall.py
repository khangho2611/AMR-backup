with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Thêm biến theo dõi stall theo từng bánh vào AGVSharedState
old_init = "        self.auto_target_turn_rpm = 22.0"
new_init = """        self.auto_target_turn_rpm = 22.0
        self.stall_start_time = None"""

if old_init in code and "self.stall_start_time" not in code:
    code = code.replace(old_init, new_init, 1)

# Nâng cấp logic nhận diện kẹt trong auto_nav_loop
old_progress_check = """        if (self.goal is not None and self.progress and now-self.progress[0][0] >= 1.5 and
                math.hypot(pose[0]-self.progress[0][1][0],pose[1]-self.progress[0][1][1]) < .02 and
                abs((pose[2]-self.progress[0][1][2]+math.pi)%(2*math.pi)-math.pi) < .10):"""

new_progress_check = """        # Kiểm tra kẹt bánh đơn phía qua dữ liệu động cơ từ ESP32
        single_wheel_stall = False
        latest_d0 = getattr(self.control, 'latest', None)
        if latest_d0 and self.goal is not None:
            l_rpm = abs(latest_d0.get('l_rpm', 0.0))
            r_rpm = abs(latest_d0.get('r_rpm', 0.0))
            l_tgt = abs(latest_d0.get('l_tgt', 0.0))
            r_tgt = abs(latest_d0.get('r_tgt', 0.0))
            # Nếu đang có lệnh quay bánh nhưng có ít nhất 1 bánh bị giữ kẹt cứng (~0 RPM)
            if (l_tgt > 10.0 and l_rpm < 3.0) or (r_tgt > 10.0 and r_rpm < 3.0):
                if state.stall_start_time is None:
                    state.stall_start_time = now
                elif now - state.stall_start_time > 1.0:
                    single_wheel_stall = True
            else:
                state.stall_start_time = None

        pose_stalled = (self.goal is not None and self.progress and now-self.progress[0][0] >= 1.5 and
                        math.hypot(pose[0]-self.progress[0][1][0],pose[1]-self.progress[0][1][1]) < .02 and
                        abs((pose[2]-self.progress[0][1][2]+math.pi)%(2*math.pi)-math.pi) < .10)

        if single_wheel_stall or pose_stalled:"""

if old_progress_check in code:
    code = code.replace(old_progress_check, new_progress_check, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED SINGLE WHEEL STALL DETECTION")
