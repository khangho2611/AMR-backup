import ast,datetime,difflib,hashlib,json,pathlib,shutil
evidence=pathlib.Path(__file__).resolve().parent;root=evidence.parents[1]
for name in ('manual_tf_targeted_green.log','manual_tf_navigation_green.log'):
    assert (evidence/name).read_text(encoding='utf-8-sig').rstrip().endswith('OK')
remote='/home/khangho/agv_codex_manual_tf_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bundle=evidence/'bundle_manual_tf';bundle.mkdir(exist_ok=False)
hashes={}
for line in (evidence/'bundle_manual_cruise/sources.sha256').read_text().splitlines():
    previous,name=line.split(maxsplit=1)
    content=(root/name).read_bytes() if name!='slam_scan_fix.yaml' else (evidence/'bundle_manual_cruise'/name).read_bytes()
    hashes[name]=hashlib.sha256(content).hexdigest()
    if name.endswith('.py'):ast.parse(content,filename=name)
    if name!='agv_unified_brain.py':assert hashes[name]==previous
    (bundle/name).write_bytes(content)
before=(evidence/'bundle_manual_cruise/agv_unified_brain.py').read_text(encoding='utf8').splitlines(True)
after=(root/'agv_unified_brain.py').read_text(encoding='utf8').splitlines(True)
(evidence/'agv_unified_brain.py.manual_tf.diff').write_text(''.join(difflib.unified_diff(before,after)),encoding='utf8')
(bundle/'sources.sha256').write_text(''.join(f'{h}  {name}\n' for name,h in hashes.items()),encoding='ascii')
assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in hashes.items() if n!='slam_scan_fix.yaml')
(evidence/'manual_tf_verification.json').write_text(json.dumps({'remote':remote,'hashes':hashes,
    'hash_stable':True,'targeted_tests':[{'count':8,'exit':0,'log':'manual_tf_targeted_green.log'},
    {'count':45,'exit':0,'log':'manual_tf_navigation_green.log'}],
    'baseline_full_suite':{'count':90,'exit':0,'log':'speed_manual_final_python.log','applies_to':'bundle_manual_cruise'},
    'full_retest':'rejected by user; not claimed as 92 passing',
    'unchanged_js':'13 assertion groups in manual_cruise_verification.json',
    'limitations':'Not physical cruise/coverage acceptance.'},indent=2),encoding='utf8')
start=(evidence/'start_body.sh').read_text(encoding='utf8').replace('/home/khangho/agv_codex_body_20261003_0106',remote)
start=start.replace('test -d /proc/2107','test -d /proc/27637')
start=start.replace('BODY_OPERATOR_STARTED_DISARMED','MANUAL_TF_STARTED_DISARMED')
(evidence/'start_manual_tf.sh').write_text(start,encoding='utf8',newline='\n')
print(json.dumps({'remote':remote,'hashes':hashes}))
