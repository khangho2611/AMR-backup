target = '/home/khangho/rplidar_c1_test/bridge/lidar_bridge_server.py'
with open(target, 'r', encoding='utf-8') as f:
    lines = f.readlines()

clean_lines = []
for line in lines:
    if "').encode('utf-8'))" in line:
        continue
    clean_lines.append(line)

with open(target, 'w', encoding='utf-8') as f:
    f.writelines(clean_lines)

import py_compile
py_compile.compile(target, doraise=True)
print("COMPILATION SUCCESSFUL!")
