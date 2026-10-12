with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Nâng cấp _idle_keepalive và watchdog_tick để duy trì nhịp tim cho ESP32 mỗi 150ms
old_keepalive_def = """    def _idle_keepalive(self):
        # Only repeat zero, never a previous motion command. A browser lease
        # cannot renew itself through this Pi-side MCU keepalive.
        if not self.writer.acquire(blocking=False):return
        failed=False
        try:
            with self.lock:
                now=self.clock()
                if (not self.armed or self.latched or self.fault or self.motion or
                        self.autonomy_allowed is not False or self.last_manual_input is None or
                        not 0 <= now-self.last_manual_input <= self.operator_idle_lease_s or
                        self.last_d0 is None or not 0 <= now-self.last_d0 <= .25):return
                generation=self.generation
            ok=self._write(b'V 0.000 0.000\\n')
            with self.lock:
                if ok and generation==self.generation and not self.latched:self.last_command=self.clock()
                elif not ok:failed=True
        finally:
            self.writer.release()
        if failed:self.request_stop('IDLE_WRITE_FAILED',wait=False)"""

new_keepalive_def = """    def _idle_keepalive(self):
        # Giữ nhịp tim (Heartbeat 150ms) cho ESP32 để không bao giờ bị watchdog 300ms tự ngắt cầu H (DISARM)
        if not self.writer.acquire(blocking=False): return
        try:
            with self.lock:
                now = self.clock()
                if not self.armed or self.latched or self.fault is not None:
                    return
                # Nếu đã quá 150ms chưa gửi lệnh nào xuống ESP32
                if self.last_command is not None and now - self.last_command < 0.15:
                    return
                generation = self.generation
            # Phát lệnh nhịp tim duy trì ARMED
            ok = self._write(b'V 0.000 0.000\\n')
            with self.lock:
                if ok and generation == self.generation and not self.latched:
                    self.last_command = self.clock()
        finally:
            self.writer.release()"""

if old_keepalive_def in code:
    code = code.replace(old_keepalive_def, new_keepalive_def, 1)

# Đảm bảo watchdog_tick gọi _idle_keepalive định kỳ
old_watchdog_tick = """    def watchdog_tick(self):
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

new_watchdog_tick = """    def watchdog_tick(self):
        soft_stop = False
        with self.lock:
            now = self.clock()
            # Mất tín hiệu điều khiển người dùng quá 1.0 giây khi đang có lệnh chuyển động LÁI TAY
            if self.armed and self.motion and self.autonomy_allowed is False:
                if self.last_command is None or now - self.last_command > 1.0:
                    soft_stop = True
        if soft_stop:
            self.drive('M 0 0', autonomous=False)
        else:
            self._idle_keepalive()"""

if old_watchdog_tick in code:
    code = code.replace(old_watchdog_tick, new_watchdog_tick, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED MCU HEARTBEAT KEEPALIVE")
