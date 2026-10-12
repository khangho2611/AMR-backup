"""Save offline verification and diff without overwriting previous evidence."""
import ast
import difflib
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

root=pathlib.Path(__file__).resolve().parents[1]
backup=root/'evidence_agv_20261001/codex_prompt_fix_20261002_181609'
out=backup/('verification_'+datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y%m%d_%H%M%S'))
out.mkdir()
files=['agv_unified_brain.py','agv_navigation.py','agv_command_session.py','index_cyberpunk.html',
       'tests/test_agv_navigation_fix.py','tests/test_agv_brain_integration.py',
       'tests/test_agv_startup_lifecycle.py','tests/test_agv_scan_adapter.py','tests/test_agv_pid_ui.cjs']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={f:sha(root/f) for f in files}
node=pathlib.Path('C:/Users/Khang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
commands=[[sys.executable,'-B','-X','utf8','-m','unittest','discover','-s','tests','-p','test_agv_*.py','-v'],
          [str(node),'tests/test_agv_pid_ui.cjs']]
if '--python-only' in sys.argv:
    commands=commands[:1]
results=[]
for i,command in enumerate(commands):
    result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf8',timeout=50)
    (out/f'test_{i+1}.txt').write_text(result.stdout+result.stderr,encoding='utf8')
    results.append({'args':command,'exit':result.returncode,'output':f'test_{i+1}.txt'})
for f in files:
    if f.endswith('.py'):ast.parse((root/f).read_text(encoding='utf8'))
after={f:sha(root/f) for f in files}
for f in ('agv_unified_brain.py','index_cyberpunk.html'):
    diff=''.join(difflib.unified_diff((backup/f).read_text(encoding='utf8').splitlines(True),
           (root/f).read_text(encoding='utf8').splitlines(True),fromfile='backup/'+f,tofile='current/'+f))
    (out/(f+'.diff')).write_text(diff,encoding='utf8')
summary={'time':datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(),'scope':'OFFLINE_ONLY; actual reader/HTTP/typed callbacks; mocked Serial and ROS imports; no physical port open',
         'source_sha_before':before,'source_sha_after':after,'stable':before==after,'tests':results,
         'syntax_ast':'PASS','backup':str(backup),'hardware':'NOT_DEPLOYED_NOT_RUN'}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'evidence':str(out),'stable':summary['stable'],'tests':results,'hashes':after},ensure_ascii=False,indent=2))
sys.exit(0 if before==after and all(r['exit']==0 for r in results) else 1)
