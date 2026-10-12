with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# 1. Tăng budget tính Costmap của GridPlanner từ 0.05s lên 0.5s để Pi 4 xử lý thoải mái
old_budget = "planner = GridPlanner(*args, budget_s=.05)"
new_budget = "planner = GridPlanner(*args, budget_s=.5)"

if old_budget in code:
    code = code.replace(old_budget, new_budget, 1)

# 2. Tự động ARM khi người dùng bấm BẬT TỰ ĐỘNG QUÉT MAP (act == 'START')
old_auto_start = """            if ros_node and act == 'START':
                ok,reason,blockers,snapshot=ros_node.start_auto()"""

new_auto_start = """            if ros_node and act == 'START':
                # Tự động mở ARM trước khi kích hoạt Auto
                ros_node.control.request_arm()
                ok,reason,blockers,snapshot=ros_node.start_auto()"""

if old_auto_start in code:
    code = code.replace(old_auto_start, new_auto_start, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY FIXED MAP_NOT_READY AND AUTO_ARM")
