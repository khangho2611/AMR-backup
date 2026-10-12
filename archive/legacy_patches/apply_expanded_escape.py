with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

old_escape = "for v,w in ((.04,.35),(.04,-.35),(.04,0.),(-.04,0.),(-.04,-.35),(-.04,.35)):"
new_escape = """# Dải ứng viên thoát hiểm linh hoạt: xoay tại chỗ, lùi chếch, tiến chếch
        candidates = (
            (-.04, 0.), (-.04, -.25), (-.04, .25), (-.04, -.35), (-.04, .35),
            (0., .35), (0., -.35), (0., .20), (0., -.20),
            (.04, .25), (.04, -.25), (.04, 0.)
        )
        for v, w in candidates:"""

if old_escape in code:
    code = code.replace(old_escape, new_escape, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY EXPANDED ESCAPE CANDIDATES")
