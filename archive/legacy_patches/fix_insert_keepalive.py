with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Chèn định nghĩa _idle_keepalive ngay trước request_stop
keepalive_code = """    def _idle_keepalive(self):
        # Phát lệnh nhịp tim V 0 0 nuôi ESP32 mỗi 150ms để không bị watchdog 300ms tự ngắt cầu H
        if not self.writer.acquire(blocking=False): return
        try:
            with self.lock:
                now = self.clock()
                if not self.armed or self.latched or self.fault is not None:
                    return
                if self.last_command is not None and now - self.last_command < 0.15:
                    return
                generation = self.generation
            ok = self._write(b'V 0.000 0.000\\n')
            with self.lock:
                if ok and generation == self.generation and not self.latched:
                    self.last_command = self.clock()
        finally:
            self.writer.release()

    def request_stop(self,"""

if "def request_stop(self," in code and "def _idle_keepalive(self):" not in code:
    code = code.replace("    def request_stop(self,", keepalive_code, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY INSERTED _idle_keepalive INTO CommandSession")
