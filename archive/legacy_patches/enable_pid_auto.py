# 1. agv_command_session.py: Cho phép lệnh 'S' (Closed-loop PID RPM)
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Chấp nhận parts[0] in ('M', 'V', 'S')
code = code.replace("if len(parts) != 3 or parts[0] not in ('M','V'):",
                    "if len(parts) != 3 or parts[0] not in ('M','V','S'):")

# Bỏ chặn DRIVE_LIMIT cho S (giới hạn RPM an toàn tối đa 65 RPM của firmware)
old_limit = """        if (parts[0] == 'M' and (autonomous or any(abs(v)>140 or v != int(v) for v in values)) or
                parts[0] == 'V' and (abs(values[0]) > .20 or abs(values[1]) > .35)):"""

new_limit = """        if (parts[0] == 'M' and (autonomous or any(abs(v)>140 or v != int(v) for v in values)) or
                parts[0] == 'V' and (abs(values[0]) > .20 or abs(values[1]) > .35) or
                parts[0] == 'S' and any(abs(v) > 65.0 for v in values)):"""

code = code.replace(old_limit, new_limit)

# Ghi lệnh S mà chưa ARMED thì tự động mồi ARM
code = code.replace("if parts[0] == 'M' and not self.armed:",
                    "if parts[0] in ('M', 'S') and not self.armed:")

# Thêm xử lý lỗi DISARMED_REJECT_S
code = code.replace("('DISARMED_REJECT_V', 'DISARMED_REJECT_M')",
                    "('DISARMED_REJECT_V', 'DISARMED_REJECT_M', 'DISARMED_REJECT_S')")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

# 2. agv_unified_brain.py: Chuyển toàn bộ điều khiển của auto sang lệnh S (PID VÒNG KÍN)
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    bcode = f.read()

# Thay thế lệnh M trong auto_nav_loop thành lệnh S với tốc độ RPM chuẩn
old_auto_drive = """            if avg_left >= avg_right:
                with state.lock: state.explore_phase = "NE TUONG (<15cm): Xoay trai sang vung thoang"
                self.send_cmd("M -110 110", autonomous=False)
            else:
                with state.lock: state.explore_phase = "NE TUONG (<15cm): Xoay phai sang vung thoang"
                self.send_cmd("M 110 -110", autonomous=False)
        else:
            with state.lock: state.explore_phase = f"QUET MAP TIEN TOI (Trong: {min_front*100:.0f}cm)"
            self.send_cmd("M 120 120", autonomous=False)"""

new_auto_drive = """            if avg_left >= avg_right:
                with state.lock: state.explore_phase = "NE TUONG [PID]: Xoay trai 30 RPM"
                self.send_cmd("S -30.0 30.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = "NE TUONG [PID]: Xoay phai 30 RPM"
                self.send_cmd("S 30.0 -30.0", autonomous=False)
        else:
            with state.lock: state.explore_phase = f"QUET MAP [PID] TIEN TOI 45 RPM (Trong: {min_front*100:.0f}cm)"
            self.send_cmd("S 45.0 45.0", autonomous=False)"""

bcode = bcode.replace(old_auto_drive, new_auto_drive)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(bcode)

print("SUCCESSFULLY SWITCHED AUTO NAVIGATION TO CLOSED-LOOP PID VIA 'S' RPM COMMANDS")
