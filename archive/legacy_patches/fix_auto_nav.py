with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Khi nhận error DISARMED_REJECT_V, KHÔNG được set FAULT làm chết hệ thống
# mà chỉ cần gửi ARM xuống để bật lại!
old_err = """                else:
                    self._fault(str(packet['error']))
                    must_stop = self.fault"""

new_err = """                elif packet.get('error') == 'DISARMED_REJECT_V':
                    self.armed = False
                    self._write(b'ARM\\n')
                else:
                    self._fault(str(packet['error']))
                    must_stop = self.fault"""

code = code.replace(old_err, new_err)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    bcode = f.read()

# Sửa start_auto: Phải đợi MCU xác nhận ARMED rồi mới chuyển sang EXPLORING
old_start = """    def start_auto(self):
        \"\"\"Expose each failed START gate at the moment of the decision.\"\"\"
        if not self.control.armed:
            self.control.request_arm()
            time.sleep(0.05)
        self.control.latched = False
        self.control.fault = None
        pose,grid=self._pose_map(),self._grid()"""

new_start = """    def start_auto(self):
        \"\"\"Expose each failed START gate at the moment of the decision.\"\"\"
        self.control.latched = False
        self.control.fault = None
        self.control.request_arm()
        t0 = time.time()
        while time.time() - t0 < 0.5:
            if self.control.armed: break
            time.sleep(0.02)
        pose,grid=self._pose_map(),self._grid()"""

bcode = bcode.replace(old_start, new_start)

# Quan trọng nhất: Trong auto_nav_loop, nếu MCU bị rớt ARM thì gửi ARM lại ngay
old_loop = """        if not auto:
            return"""

new_loop = """        if not auto:
            return
        if not self.control.armed and not self.control.fault:
            self.control.request_arm()"""

bcode = bcode.replace(old_loop, new_loop)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(bcode)

print("FIXED AUTO ARM LOOP AND REJECT_V HANDLING")
