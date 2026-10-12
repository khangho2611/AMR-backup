with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# TẮT BỎ BẪY require_transport_sync=True!
# Bẫy này bắt vi điều khiển phải gửi chuỗi STOP và đợi đồng bộ 0.4s trước khi ARM,
# khiến request_arm() luôn bị timeout và xe bị kẹt vĩnh viễn ở DISARMED!

code = code.replace("require_transport_sync=True", "require_transport_sync=False")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY DISABLED require_transport_sync")
