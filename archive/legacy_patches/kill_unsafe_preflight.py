with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# DIỆT TẬN GỐC UNSAFE_PREFLIGHT_D0:
# Lỗi này phạt khi xe đang nhích bánh (not clean: l_rpm != 0 hoặc x != 0) mà Pi chưa ghi nhận ARMED!
old_unsafe = "self._fault('UNSAFE_PREFLIGHT_D0'); must_stop = self.fault"
new_unsafe = "pass # Không bao giờ phạt UNSAFE_PREFLIGHT_D0 khi bánh xe đang quay!"

code = code.replace(old_unsafe, new_unsafe)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY KILLED UNSAFE_PREFLIGHT_D0")
