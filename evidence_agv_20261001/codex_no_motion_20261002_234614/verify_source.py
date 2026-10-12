"""Bind offline verification/diffs to the exact local sources; no hardware."""
import ast
import datetime
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FILES=['agv_unified_brain.py','agv_command_session.py','agv_navigation.py',
       'agv_command_journal.py','index_cyberpunk.html']

def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}

before=hashes()
for path in [ROOT/f for f in FILES if f.endswith('.py')]+list((ROOT/'tests').glob('test_agv_*.py')):
    ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
html=(ROOT/'index_cyberpunk.html').read_text(encoding='utf8')
script=re.search(r'<script>([\s\S]*?)</script>',html).group(1)
js=HERE/'dashboard_script.js';js.write_text(script,encoding='utf8')
syntax=subprocess.run(['node','--check',str(js)],capture_output=True,text=True)
(HERE/'node_syntax.txt').write_text(syntax.stdout+syntax.stderr,encoding='utf8')
if syntax.returncode:raise RuntimeError('Dashboard JS syntax failed')
after=hashes()
if before!=after:raise RuntimeError('Source changed during static verification')
for name in FILES:
    original=(HERE/name).read_text(encoding='utf-8-sig').splitlines(keepends=True) if (HERE/name).exists() else []
    current=(ROOT/name).read_text(encoding='utf-8-sig').splitlines(keepends=True)
    diff=''.join(difflib.unified_diff(original,current,fromfile='before/'+name,tofile='after/'+name))
    (HERE/(name+'.diff')).write_text(diff,encoding='utf8')
tests=(HERE/'full_python_tests_final.txt').read_text(encoding='utf-8-sig')
if not re.search(r'Ran 75 tests in [0-9.]+s\s+OK\s*$',tests):raise RuntimeError('Final test log did not pass')
ui=(HERE/'green_ui.txt').read_text(encoding='utf-8-sig')
if len(re.findall(r'^PASS ',ui,re.M))!=11:raise RuntimeError('UI assertion groups did not pass')
result=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    mode='SOURCE_OFFLINE_NO_MOTION',source_hashes=after,
    static_hash_before=before,static_hash_after=after,ast='PASS',node_syntax_exit=syntax.returncode,
    python=dict(command="python -B -X utf8 -m unittest discover -s tests -p 'test_agv_*.py' -v",
                tests=75,exit=0,log='full_python_tests_final.txt'),
    ui=dict(command='node tests/test_agv_pid_ui.cjs',groups=11,exit=0,log='green_ui.txt'),
    limitations=['FakeUART/ROS imports replaced; no physical Serial OPEN or TX',
                 'No deployment/restart/ARM/AUTO/motion this turn',
                 'No physical braking/whole-room/home acceptance',
                 'No original ARM/AUTO failure timeline recovered'],
    pi_readonly=json.loads((HERE/'pi_readonly_status.json').read_text(encoding='utf-8-sig')))
(HERE/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
