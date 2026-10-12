with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Khi chưa chọn được Frontier xa hợp lệ, xe phải TỰ ĐỘNG XOAY QUANH ĐỂ QUÉT RỘNG MAP (Active Mapping)
old_no_frontier = """            if remaining == 0:
                self.explore_state = 'RETURNING_HOME'
                self._hold('Hết frontier reachable; về home, unknown khác còn chưa nghiệm thu')
            else:
                self._hold('HOLD: frontier còn nhưng chưa có mục tiêu an toàn mới')
            return"""

new_no_frontier = """            if remaining == 0:
                self.explore_state = 'RETURNING_HOME'
                self._hold('Hết frontier reachable; về home, unknown khác còn chưa nghiệm thu')
                return
            else:
                # VỪA CHẠY VỪA QUÉT: Xoay tại chỗ góc nhẹ để LiDAR quét mở rộng biên bản đồ tìm Frontier mới!
                w_turn = max(0.15, min(0.35, (state.auto_target_turn_rpm / 60.0) * (2 * math.pi)))
                self.send_cmd(f'V 0.000 {w_turn:.3f}', autonomous=True)
                with state.lock: state.explore_phase = 'TỰ HÀNH: đang xoay quét mở rộng bản đồ'
                return"""

if old_no_frontier in code:
    code = code.replace(old_no_frontier, new_no_frontier, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED ACTIVE ROTATION FOR AUTO MAPPING")
