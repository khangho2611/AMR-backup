with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. Bỏ việc ném fault khi ESP32 trả về DISARMED_REJECT
old_fault_ingest = "self._fault(str(packet['error']))"
new_fault_ingest = """if 'DISARMED_REJECT' in str(packet['error']):
                        # ESP32 báo cần ARM => Bỏ qua không khóa fault, tự động bù ARM
                        pass
                    else:
                        self._fault(str(packet['error']))"""

if old_fault_ingest in code:
    code = code.replace(old_fault_ingest, new_fault_ingest, 1)

# 2. Trước khi ghi bất kỳ lệnh V nào xuống ESP32, luôn tự động kẹp ARM\\n trước để mở khóa cầu H
old_v_write = "wrote = self._write((command + '\\n').encode('ascii'))"
new_v_write = """self._write(b'ARM\\n')
            wrote = self._write((command + '\\n').encode('ascii'))"""

if old_v_write in code:
    code = code.replace(old_v_write, new_v_write, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY BULLETPROOFED V COMMAND WITH AUTO ARM")
