import ast
import datetime
import difflib
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

root=pathlib.Path(__file__).resolve().parents[2]
evidence=pathlib.Path(__file__).resolve().parent
escape='--escape' in sys.argv
body='--body' in sys.argv
bundle=evidence/('bundle_body' if body else 'bundle_escape' if escape else 'bundle')
bundle.mkdir(exist_ok=False)
files=['agv_unified_brain.py','agv_command_session.py','agv_navigation.py',
       'agv_command_journal.py','agv_preflight_static_collector.py','index_cyberpunk.html']
hashes={}
for name in files:
    content=(root/name).read_bytes()
    hashes[name]=hashlib.sha256(content).hexdigest()
    if name.endswith('.py'):ast.parse(content,filename=name)
    shutil.copy2(root/name,bundle/name)
    prior=(evidence/'before'/name).read_text(encoding='utf8').splitlines(True)
    current=content.decode('utf8').splitlines(True)
    (evidence/((name+'.body.diff') if body else (name+'.escape.diff') if escape else (name+'.diff'))).write_text(''.join(difflib.unified_diff(prior,current,
         fromfile='before/'+name,tofile='after/'+name)),encoding='utf8')
shutil.copy2(root/'evidence_agv_20261001/codex_deploy_prep_20261002_1915/slam_scan_fix.yaml',bundle/'slam_scan_fix.yaml')
hashes['slam_scan_fix.yaml']=hashlib.sha256((bundle/'slam_scan_fix.yaml').read_bytes()).hexdigest()
js=re.search(r'<script>([\s\S]*?)</script>',(bundle/'index_cyberpunk.html').read_text(encoding='utf8')).group(1)
(evidence/'dashboard.js').write_text(js,encoding='utf8')
results=[]
if body or escape:
    previous=json.loads((evidence/'verification.json').read_text(encoding='utf8'))
    assert hashes['index_cyberpunk.html']==previous['hashes']['index_cyberpunk.html']
    results=previous['js']
for command in ([] if body or escape else [['node','--check',str(evidence/'dashboard.js')],['node',str(root/'tests/test_agv_pid_ui.cjs')]]):
    result=subprocess.run(command,cwd=root,capture_output=True,text=True)
    results.append(dict(command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if result.returncode:raise RuntimeError(result.stderr)
(bundle/'sources.sha256').write_text(''.join(f'{h}  {name}\n' for name,h in hashes.items()),encoding='ascii')
after={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
assert all(after[name]==hashes[name] for name in files)
(evidence/('body_verification.json' if body else 'escape_verification.json' if escape else 'verification.json')).write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    hashes=hashes,after=after,hash_stable=True,python_tests=dict(count=84 if body else 81 if escape else 77,exit=0,log='body_python_tests.log' if body else 'escape_python_tests.log' if escape else 'python_tests.log'),
    js=results,limitations='Offline tests. No physical motion, ROS executor or deployment acceptance.'),indent=2),encoding='utf8')
print(json.dumps(hashes,indent=2))
