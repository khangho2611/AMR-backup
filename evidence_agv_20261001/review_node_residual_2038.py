"""Exact extended offline QA used for review_node_residual_2038.json; exclusive output."""
from pathlib import Path
p=Path(__file__).with_name('review_node_residual_2028.py')
s=p.read_text(encoding='utf-8')
addition='''
n,g,serial=setup()
m=S(linear=S(x=.04),angular=S(z=0.),lease_id=g.active_token,stamp=100.04,epoch=g.current_epoch)
with patch.object(r.time,'monotonic',return_value=100.05):n.nav_sub.callback(m)
cases.append(dict(id='POS_valid_envelope',writes=list(serial.writes)))
serial.writes.clear()
with patch.object(r.time,'monotonic',return_value=100.06):n.destroy_node()
pre_confirm=g.stop_confirmed
g.process_incoming_line(json.dumps(d0),100.08)
cases.append(dict(id='STOP_write_then_freshD0',writes=list(serial.writes),gate_confirmed_before=pre_confirm,gate_confirmed_after=g.stop_confirmed,public_confirmation=n.watchdog.last_stop_confirmed))
assert all(not case['writes'] and case['exception'] is None for case in cases[:5])
assert cases[5]['reported_failed'] is True and cases[5]['reported_result']=='REJECT_STOP_WRITE_FAILED'
assert cases[6]['writes']==['V 0.040 0.000\\n']
'''
s=s.replace('after=hashes();out=',addition+'\nafter=hashes();out=')
s=s.replace('review_node_residual_2028.json','review_node_residual_2038.json')
exec(compile(s,str(p),'exec'),{'__file__':str(p.resolve())})
