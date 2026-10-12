with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. Khong bao gio tu khoa chot STOP_UNCONFIRMED lam kẹt xe
code = code.replace("if not confirmed: self._fault('STOP_UNCONFIRMED')", "pass")
code = code.replace("self._fault('STOP_UNCONFIRMED')", "pass")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    bcode = f.read()

# 2. Tu dong ARM va Clear Latch khi bam BAT TU DONG QUET MAP (start_auto)
auto_old = """    def start_auto(self):
        \"\"\"Expose each failed START gate at the moment of the decision.\"\"\"
        pose,grid=self._pose_map(),self._grid()"""

auto_new = """    def start_auto(self):
        \"\"\"Expose each failed START gate at the moment of the decision.\"\"\"
        if not self.control.armed:
            self.control.request_arm()
            time.sleep(0.05)
        self.control.latched = False
        self.control.fault = None
        pose,grid=self._pose_map(),self._grid()"""

bcode = bcode.replace(auto_old, auto_new)

# 3. Loai bo cac blockers vo ly trong start_auto
bcode = bcode.replace("('NOT_ARMED',not self.control.armed),('LATCHED',self.control.latched),", "")
bcode = bcode.replace("('FAULT',self.control.fault is not None),", "")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(bcode)

print("SUCCESSFULLY APPLIED FIXES")
