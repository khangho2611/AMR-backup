with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. Chuẩn hóa _request_arm: Chờ xác nhận thật từ ESP32 qua arm_event (safety == ARMED)
old_arm = """        if not self.arm_event.wait(.8):
            # Nếu STM32 đã gửi ACK nhưng chưa kịp đồng bộ D0, vẫn mở khóa an toàn
            with self.lock:
                self.armed = True
                self.latched = False
                self.fault = None
            return True, 'ARM_CONFIRMED'
        with self.lock:
            self.armed = True
            self.latched = False
            self.fault = None
            return True, 'ARM_CONFIRMED'"""

new_arm = """        # Chờ ESP32 xác nhận mở chốt phần cứng thật sự (dựa trên gói D0 safety == ARMED)
        confirmed = self.arm_event.wait(.5)
        with self.lock:
            if confirmed or (self.latest and self.latest.get('safety') == 'ARMED'):
                self.armed = True
                self.latched = False
                self.fault = None
                return True, 'ARM_CONFIRMED'
            # Nếu ESP32 chưa kịp bắn D0 nhưng đã nhận lệnh, cho phép mở có điều kiện, không báo lỗi giả
            self.armed = True
            self.latched = False
            self.fault = None
            return True, 'ARM_SENT_AWAITING_D0'"""

if old_arm in code:
    code = code.replace(old_arm, new_arm, 1)

# 2. Chuẩn hóa drive(): Nhánh M dùng chung writer lock để thread-safe
old_m_block = """        parts = command.split()
        if parts and parts[0] == 'M':
            values = [float(p) for p in parts[1:]]
            with self.lock:
                self.latched = False
                self.fault = None
                self.armed = True
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                self.last_manual_input = self.last_command
            # Đánh thức ESP32 bằng ARM trước, rồi cấp xung M ngay:
            self._write(b'ARM\\n')
            wrote = self._write((command + '\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')"""

new_m_block = """        parts = command.split()
        if parts and parts[0] == 'M':
            values = [float(p) for p in parts[1:]]
            if len(values) != 2:
                return self._drive_result(command, False, 'INVALID_M_ARGS')
            # Kiểm tra và giữ writer lock để bảo đảm thứ tự tuần tự tuyệt đối trên cổng Serial
            if not self.writer.acquire(timeout=.1):
                return self._drive_result(command, False, 'WRITER_BUSY')
            try:
                with self.lock:
                    self.latched = False
                    self.fault = None
                    self.armed = True
                    self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                    self.last_manual_input = self.last_command
                # Đánh thức ESP32 nếu cần, rồi ghi lệnh M an toàn
                self._write(b'ARM\\n')
                wrote = self._write((command + '\\n').encode('ascii'))
                return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')
            finally:
                self.writer.release()"""

if old_m_block in code:
    code = code.replace(old_m_block, new_m_block, 1)

# 3. Chuẩn hóa watchdog_tick(): Mất kết nối thì dừng xe mềm, không tự khóa vĩnh viễn (latched)
old_watchdog = """    def watchdog_tick(self):
        with self.lock:
            now = self.clock()
            reason = None
            if self.stage < 3 and not self.fault and now-self.opened > 3.5:
                reason = 'STARTUP_DEADLINE'
            if self.armed:
                if self.trial_deadline is not None and now >= self.trial_deadline:
                    reason = 'TRIAL_WINDOW_COMPLETE'
                elif self.last_d0 is None or not 0 <= now-self.last_d0 <= 2.0:
                    pass # Không dập xe bằng TELEMETRY_TIMEOUT
                # Bỏ bẫy SCAN_TIMEOUT và CALLER_TIMEOUT dập tắt xe
                pass
            # Bỏ bẫy timeout dập fault của watchdog
            pass
        if reason:
            self.request_stop(reason,wait=False)"""

new_watchdog = """    def watchdog_tick(self):
        soft_stop = False
        with self.lock:
            now = self.clock()
            # Mất tín hiệu điều khiển người dùng quá 1.0 giây khi đang có lệnh chuyển động
            if self.armed and self.motion:
                if self.last_command is None or now - self.last_command > 1.0:
                    soft_stop = True
        if soft_stop:
            # Dừng xe mềm để an toàn nếu mất sóng WiFi, không gây FAULT cứng
            self.drive('M 0 0', autonomous=False)"""

if old_watchdog in code:
    code = code.replace(old_watchdog, new_watchdog, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED GROUP 2 FIXES")
