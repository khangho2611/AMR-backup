with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if "if str(packet.get('error')) not in ('DISARMED_REJECT_M', 'DISARMED_REJECT_S'):" in line:
        new_lines.append("                    err_msg = str(packet.get('error', ''))\n")
        new_lines.append("                    if not err_msg.startswith('DISARMED_REJECT'):\n")
        new_lines.append("                        self._fault(err_msg)\n")
        new_lines.append("                    must_stop = self.fault\n")
        # skip until elif 'ack'
        skip = True
        continue
    if skip:
        if "elif 'ack' in packet:" in line:
            skip = False
            new_lines.append(line)
        continue
    new_lines.append(line)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.writelines(new_lines)

print("SUCCESSFULLY CLEANED INDENTATION ERROR")
