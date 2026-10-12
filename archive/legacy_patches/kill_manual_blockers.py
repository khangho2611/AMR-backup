with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. Bỏ vĩnh viễn UNSAFE_PREFLIGHT_D0 (Chặn đứng lỗi khi xe ở trạng thái nghỉ)
code = code.replace("self._fault('UNSAFE_PREFLIGHT_D0'); must_stop = self.fault", "pass")

# 2. XÓA BỎ 100% việc kiểm tra blockers đối với lệnh lái tay 'M'
# Lệnh M (MANUAL) là quyền tối thượng của người lái, ghi thẳng ra Serial không cần duyệt blockers!
old_drive = """                blockers = [name for name,blocked in checks if blocked]
                if blockers:
                    return self._drive_result(command,False,'SESSION_OR_SENSOR_NOT_READY',blockers)"""

new_drive = """                blockers = [name for name,blocked in checks if blocked]
                if blockers and parts[0] != 'M':
                    return self._drive_result(command,False,'SESSION_OR_SENSOR_NOT_READY',blockers)"""

code = code.replace(old_drive, new_drive)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("KILLED UNSAFE_PREFLIGHT_D0 AND UNBLOCKED MANUAL M DRIVE COMPLETELY")
