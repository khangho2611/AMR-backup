"""Evaluate simulation release criteria from independent closed-loop JSON reports.

This gate is necessary for experimental policy promotion, but does not certify
real-robot safety, Pi 4 latency, or performance on unseen map geometries.
"""

import argparse
import json
from pathlib import Path


MIN_SUCCESS = {1: .99, 2: .98, 3: .90, 4: .90, 5: .90, 6: .90}
MAX_COLLISION = {i: .02 for i in range(1, 7)}
MAX_COLLISION[4] = .12


def assess(reports: dict[int, dict], min_episodes: int = 100) -> dict:
    if set(reports) not in ({1, 2, 3}, set(range(1, 6)), set(range(1, 7))):
        raise ValueError("Provide all Levels 1-3, 1-5, or 1-6")
    checkpoint_names = {str(r["checkpoint"]) for r in reports.values()}
    if len(checkpoint_names) != 1:
        raise ValueError("All reports must evaluate the same checkpoint")
    checks = {}
    for level, report in sorted(reports.items()):
        if int(report["level"]) != level:
            raise ValueError(f"Report labeled Level {level} contains Level {report['level']}")
        n = int(report["episodes"])
        success = float(report["success_rate"])
        collision = float(report["collision_rate"])
        timeout = float(report["timeout_rate"])
        if n <= 0 or any(not 0 <= v <= 1 for v in (success, collision, timeout)):
            raise ValueError(f"Invalid episode count or rates for Level {level}")
        if abs(success + collision + timeout - 1.) > 1e-6:
            raise ValueError(f"Rates do not sum to 1 for Level {level}")
        randomized = report.get("domain_randomization") is True
        passed = (n >= min_episodes and randomized and
                  success >= MIN_SUCCESS[level] - 1e-9 and
                  collision <= MAX_COLLISION[level] + 1e-9)
        checks[str(level)] = {
            "passed": passed, "episodes": n, "domain_randomization": randomized,
            "success_rate": success, "collision_rate": collision,
            "timeout_rate": timeout, "minimum_success_rate": MIN_SUCCESS[level],
            "maximum_collision_rate": MAX_COLLISION[level],
        }
    return {"checkpoint": checkpoint_names.pop(),
            "simulation_gate_passed": all(v["passed"] for v in checks.values()),
            "full_six_level_gate": set(reports) == set(range(1, 7)),
            "levels": checks,
            "scope": "Fixed curriculum geometry; simulation only; not real-robot approval"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for level in range(1, 4):
        parser.add_argument(f"--level{level}", type=Path, required=True)
    for level in range(4, 7):
        parser.add_argument(f"--level{level}", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reports = {i: json.loads(getattr(args, f"level{i}").read_text(encoding="utf-8"))
               for i in range(1, 4)}
    requested_extra = [i for i in range(4, 7) if getattr(args, f'level{i}')]
    if requested_extra and requested_extra not in ([4, 5], [4, 5, 6]):
        parser.error('Provide Levels 4-5 together (with optional Level 6)')
    reports.update({i: json.loads(getattr(args, f"level{i}").read_text(encoding="utf-8"))
                    for i in requested_extra})
    result = assess(reports)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["simulation_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
