#!/usr/bin/env bash
set -euo pipefail
# Run from the repository root in a Kaggle notebook/container.
python -m pip install -r ai_local_planner/requirements.txt
python -m ai_local_planner.scripts.run_train --device auto --steps 5000000 \
  --output-dir ai_local_planner/checkpoints
