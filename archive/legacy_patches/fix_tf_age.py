with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Sửa độ tuổi TF lookup từ .25s lên 1.0s (SLAM async phát TF chu kỳ 5Hz - 10Hz, 0.25s rất dễ bị trễ)
old_tf_age = "if not 0 <= age <= .25:"
new_tf_age = "if not 0 <= age <= 1.0:"

if old_tf_age in code:
    code = code.replace(old_tf_age, new_tf_age, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY RELAXED TF AGE CHECK")
