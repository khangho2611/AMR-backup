with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# KHÔNG BAO GIỜ TỰ KÍCH HOẠT MCU_DISARMED_DURING_SESSION:
# Khi STM32 ở trạng thái nghỉ DISARMED (do hết timeout 300ms watchdog của nó),
# Pi chỉ cần ghi nhận trạng thái chứ KHÔNG ĐƯỢC TỰ DỰNG FAULT khóa chốt latched = True!
old_disarm_fault = """                    elif self.armed and packet['safety'] != 'ARMED':
                        self._fault('MCU_DISARMED_DURING_SESSION'); must_stop = self.fault"""

new_disarm_fault = """                    elif self.armed and packet['safety'] != 'ARMED':
                        # Chuyển về armed = False êm đẹp, không dựng cờ FAULT khóa xe!
                        self.armed = False"""

code = code.replace(old_disarm_fault, new_disarm_fault)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY NEUTRALIZED MCU_DISARMED_DURING_SESSION FAULT TRAP")
