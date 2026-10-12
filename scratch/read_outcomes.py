import json
with open('logs/command_outcomes.jsonl') as f:
    lines = f.readlines()
for line in lines[-25:]:
    d = json.loads(line)
    print(d.get('utc'), d.get('operation'), d.get('arguments'), d.get('response'))
