with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Đảm bảo ARM dứt điểm khi bấm START
old_block = """            if ros_node and act == 'START':
                ok,reason,blockers,snapshot=ros_node.start_auto()"""

new_block = """            if ros_node and act == 'START':
                ros_node.control.request_arm()
                ok,reason,blockers,snapshot=ros_node.start_auto()"""

if old_block in code:
    code = code.replace(old_block, new_block, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY INJECTED AUTO ARM BEFORE START")
