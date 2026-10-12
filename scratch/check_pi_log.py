import json
import sys

log_path = '/home/khangho/agv_codex_reader_20261003_0652/logs/command_outcomes.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total entries: {len(lines)}")
for l in lines[-25:]:
    try:
        d = json.loads(l)
        print(f"{d.get('utc')} | {d.get('operation')} | {d.get('arguments')} | {d.get('response')}")
    except Exception as e:
        print("Error:", e)
