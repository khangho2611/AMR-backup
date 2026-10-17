"""Run exported ONNX mean policy in a randomized closed-loop simulator."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ai_local_planner.scripts.evaluate_policy import evaluate_agent


class ONNXAgent:
    def __init__(self, model: Path):
        manifest = json.loads(model.with_suffix(".json").read_text(encoding="utf-8"))
        if hashlib.sha256(model.read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("ONNX SHA256 mismatch")
        self.metadata = manifest
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def act(self, obs, deterministic=True):
        if not deterministic:
            raise ValueError("Only deterministic ONNX mean policy is exported")
        velocity = self.session.run(None,
                                    {self.input_name: np.asarray(obs[None, :], dtype=np.float32)})[0][0]
        if velocity.shape != (2,) or not np.isfinite(velocity).all():
            raise ValueError("Invalid ONNX motion command")
        # Env.step expects normalized [-1,1], while ONNX emits physical cmd_vel.
        action = np.asarray([2. * velocity[0] / .35 - 1., velocity[1] / 1.5],
                            dtype=np.float32)
        return np.clip(action, -1., 1.), 0., 0.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path,
                        default=Path("ai_local_planner/exported/local_planner.onnx"))
    parser.add_argument("--level", type=int, choices=range(1, 7), required=True)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=300000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be positive")
    agent = ONNXAgent(args.model)
    report = evaluate_agent(agent, level=args.level, episodes=args.episodes,
                            seed=args.seed, randomize=True, max_steps=600)
    report.update(model=str(args.model), checkpoint=str(args.model),
                  training_steps=agent.metadata.get("training_steps", 0),
                  engine="onnxruntime_cpu")
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
