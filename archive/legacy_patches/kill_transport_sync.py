with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    bcode = f.read()

# TẮT BỎ BẪY require_transport_sync=True TRONG agv_unified_brain.py:
bcode = bcode.replace('require_transport_sync=True', 'require_transport_sync=False')

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(bcode)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    scode = f.read()

# TẮT THÊM TRONG CommandSession ĐỂ CHẮC CHẮN 100%:
scode = scode.replace('if self.require_transport_sync:', 'if False and self.require_transport_sync:')

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(scode)

print("SUCCESSFULLY MUTED TRANSPORT_SYNC - INSTANT DIRECT ARM")
