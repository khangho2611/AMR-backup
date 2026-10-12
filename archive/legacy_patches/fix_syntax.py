target = '/home/khangho/rplidar_c1_test/bridge/lidar_bridge_server.py'
with open(target, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if 'ser.write((cmd_str.strip()' in line:
        new_lines.append('                msg = cmd_str.strip() + "\\r\\n"\n')
        new_lines.append('                ser.write(msg.encode("utf-8"))\n')
    else:
        new_lines.append(line)

with open(target, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("REPAIRED SERIAL WRITE LINE!")
