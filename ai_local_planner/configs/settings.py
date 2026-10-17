"""Single source of truth for simulator and PPO settings."""

from pathlib import Path
import yaml


DEFAULT_CONFIG = Path(__file__).with_name("default_config.yaml")


def load_config(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if config["lidar"]["num_rays"] != 360:
        raise ValueError("Actor and observation contract require exactly 360 LiDAR rays")
    if config["robot"]["v_min"] != 0.0:
        raise ValueError("The fixed 2-action policy uses forward-only v in [0, 0.35]")
    if config["sim_to_real"]["latency_steps"] != 1:
        raise ValueError("This simulator models the required one-step UART delay")
    return config
