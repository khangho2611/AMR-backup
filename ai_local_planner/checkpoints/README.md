# Checkpoint AI1 (PyTorch PPO)

Mỗi lượt chạy `python -m ai_local_planner.scripts.run_train` có một
`--output-dir` riêng để tránh ghi đè kết quả khác.

- `latest_model.pth`: trạng thái huấn luyện mới nhất (chứa model, optimizer,
  `steps`, `level`, metadata); dùng với `--resume`.
- `best_level_N.pth`: checkpoint ứng viên tốt nhất theo metric **level N**;
  có thể chưa vượt gate hoặc đã quên kỹ năng level cũ.
- `best_model.pth`: chỉ sinh khi **Level 1..N đều vượt gate** với >=100 episode
  randomization/level, success >=99% (L1), >=98% (L2), >=90% (L3..L6),
  collision <=2%.
- `checkpoint_step_N.pth`: snapshot định kỳ theo `--save-every`.
- `episodes.csv`: rollout exploration, tính success window riêng theo level;
  **không** dùng làm acceptance gate.
- `evaluations.jsonl`: báo cáo held-out và retention gate.

Nạp checkpoint đúng schema:

```python
import torch
from ai_local_planner.models.actor_critic import ActorCritic

state = torch.load("ai_local_planner/checkpoints/ppo_six_level/best_model.pth",
                   map_location="cpu", weights_only=True)
network = ActorCritic().eval()
network.load_state_dict(state["model"])
```

Đường dẫn trong ví dụ chỉ tồn tại khi huấn luyện đã đạt gate. Gate mô phỏng
chưa chứng nhận điều khiển robot thật hoặc đáp ứng latency Raspberry Pi 4.
