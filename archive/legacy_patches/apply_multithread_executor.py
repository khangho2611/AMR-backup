with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# 1. Chuyển rclpy sang MultiThreadedExecutor để tính A* không làm nghẽn luồng nhận /scan và /map
old_spin = "ros_thread = threading.Thread(target=rclpy.spin, args=(ros_node,), daemon=True)"
new_spin = """from rclpy.executors import MultiThreadedExecutor
            executor = MultiThreadedExecutor(num_threads=4)
            executor.add_node(ros_node)
            ros_thread = threading.Thread(target=executor.spin, daemon=True)"""

if old_spin in code:
    code = code.replace(old_spin, new_spin, 1)

# 2. Tăng ngân sách build costmap lên 0.5s và TF age lên 1.0s để không bao giờ bị MAP_NOT_READY / TF_NOT_READY
old_budget = "planner = GridPlanner(*args, budget_s=.05)"
new_budget = "planner = GridPlanner(*args, budget_s=.5)"
if old_budget in code:
    code = code.replace(old_budget, new_budget, 1)

old_tf_age = "if not 0 <= age <= .25:"
new_tf_age = "if not 0 <= age <= 1.0:"
if old_tf_age in code:
    code = code.replace(old_tf_age, new_tf_age, 1)

# 3. Khi bấm START, luôn gửi ARM và reset generation an toàn
old_start = """            if ros_node and act == 'START':
                ok,reason,blockers,snapshot=ros_node.start_auto()"""

new_start = """            if ros_node and act == 'START':
                ros_node.control.request_arm()
                ok,reason,blockers,snapshot=ros_node.start_auto()"""
if old_start in code:
    code = code.replace(old_start, new_start, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED MULTITHREADED EXECUTOR & TIMEOUT BUFFER")
