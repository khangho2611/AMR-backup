target = '/home/khangho/rplidar_c1_test/bridge/agv_master_explorer.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# Thay thế hàm send_cmd để gửi bằng S (RPM) thay vì V (m/s)
old_send_cmd = """    def send_cmd(self, cmd_str):
        if self.ser and self.ser.is_open:
            try:
                msg = (cmd_str.strip() + '\\r\\n').encode('utf-8')
                self.ser.write(msg)
            except Exception:
                pass"""

new_send_cmd = """    def send_cmd(self, cmd_str):
        if not self.ser or not self.ser.is_open:
            return
        try:
            parts = cmd_str.strip().split()
            if not parts:
                return
            
            # CHUYỂN ĐỔI LỆNH V (v_m/s, w_rad/s) SANG S (L_RPM, R_RPM) ĐỂ DRIVER ESP32 ĐẠT MÔ-MEN ĐỦ KHỎE
            # Công thức động học vi sai: L = 0.1875m, R = 0.0366m
            # v_l = v - w * L / 2;  v_r = v + w * L / 2
            # rpm = (v / (2 * pi * R)) * 60 = v * 260.91
            if parts[0] == 'V' and len(parts) >= 3:
                v = float(parts[1])
                w = float(parts[2])
                
                v_l = v - w * (0.1875 / 2.0)
                v_r = v + w * (0.1875 / 2.0)
                
                rpm_l = v_l * 260.91
                rpm_r = v_r * 260.91
                
                # BÙ ĐỘNG LỰC HỌC KHỞI ĐỘNG (Deadband Compensation):
                # Động cơ GA25 có hộp số cần tối thiểu +-38 RPM để vượt qua ma sát tĩnh
                MIN_RPM = 38.0
                if abs(rpm_l) > 1.0 and abs(rpm_l) < MIN_RPM:
                    rpm_l = MIN_RPM if rpm_l > 0 else -MIN_RPM
                if abs(rpm_r) > 1.0 and abs(rpm_r) < MIN_RPM:
                    rpm_r = MIN_RPM if rpm_r > 0 else -MIN_RPM
                    
                msg = f"S {rpm_l:.1f} {rpm_r:.1f}\\r\\n".encode('utf-8')
                self.ser.write(msg)
            else:
                msg = (cmd_str.strip() + '\\r\\n').encode('utf-8')
                self.ser.write(msg)
        except Exception:
            pass"""

if 'BÙ ĐỘNG LỰC HỌC KHỞI ĐỘNG (Deadband Compensation)' not in code:
    code = code.replace(old_send_cmd, new_send_cmd)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

import py_compile
py_compile.compile(target, doraise=True)
print("SUCCESSFULLY INJECTED HARDWARE DEADBAND COMPENSATION TO S COMMANDS!")
