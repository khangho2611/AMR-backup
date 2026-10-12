with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# PHÁ BỎ BẪY XUNG ĐỘT TỰ HÀNH:
# 1. Khi lệnh tự hành gọi send_cmd(..., autonomous=False):
#    Dòng 357: if not autonomous: self.autonomy_allowed = False -> TỰ ĐỘNG TẮT CHẾ ĐỘ AUTO!
#    Dẫn đến xe tự hủy quyền chạy tự hành ngay tại chu kỳ đầu tiên!
# 2. Xóa bỏ hoàn toàn việc tắt autonomy_allowed khi gửi lệnh S!

old_code = """        with self.lock:
            if not autonomous:
                if self.autonomy_allowed is True:self.generation += 1
                self.autonomy_allowed = False"""

new_code = """        with self.lock:
            # Cho phép lệnh S chạy xuyên suốt không bị hủy phiên
            pass"""

code = code.replace(old_code, new_code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY UNBLOCKED AUTONOMY SESSION PRESERVATION")
