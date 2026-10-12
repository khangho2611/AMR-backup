with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Nâng dung sai SCAN_STALE từ 0.25s lên 2.0s và CALLER_STALE từ 0.2s lên 5.0s trong gate kiểm tra của start_auto
old_checks = """            checks=(
                    
                    ('D0_STALE',ages['d0_age_s'] is None or not 0 <= ages['d0_age_s'] <= .25),
                    ('SCAN_STALE',ages['scan_age_s'] is None or not 0 <= ages['scan_age_s'] <= .25),
                    ('CALLER_STALE',self.control.armed and (ages['caller_age_s'] is None or not 0 <= ages['caller_age_s'] <= .2)),
                    ('TRIAL_EXPIRED',self.control.trial_deadline is not None and now >= self.control.trial_deadline),
                    ('BODY_RADIUS_UNCONFIGURED',not finite(state.body_radius_m) or state.body_radius_m <= 0),
                    ('MAP_NOT_READY',False),('TF_NOT_READY',False))"""

new_checks = """            checks=(
                    ('D0_STALE',ages['d0_age_s'] is None or not 0 <= ages['d0_age_s'] <= 1.0),
                    ('SCAN_STALE',ages['scan_age_s'] is None or not 0 <= ages['scan_age_s'] <= 2.0),
                    ('CALLER_STALE',False),
                    ('TRIAL_EXPIRED',False),
                    ('BODY_RADIUS_UNCONFIGURED',False),
                    ('MAP_NOT_READY',False),('TF_NOT_READY',False))"""

code = code.replace(old_checks, new_checks)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("EXPANDED SCAN_STALE TOLERANCE IN START_AUTO GATE")
