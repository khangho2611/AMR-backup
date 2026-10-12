"""Independent whole-CLI OFFLINE QA; fake transport and clock only, no hardware."""
import pathlib,sys,json,hashlib,tempfile,io
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agv_preflight_static_collector as m
src=ROOT/'agv_preflight_static_collector.py'
before=hashlib.sha256(src.read_bytes()).hexdigest()
outdir=pathlib.Path(tempfile.mkdtemp(prefix='parent_banner_20261002_0804_',dir=ROOT/'evidence_agv_20261001'))
raw=json.loads((ROOT/'evidence_agv_20261001/preflight_raw_evidence_1790868029770_2625_0.json').read_text())
boot=[bytes.fromhex(r['raw_hex']) for r in raw['records']]
banner='ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)'
d0=dict(safety='DISARMED',l_tgt=0,r_tgt=0,l_pwm=0,r_pwm=0,l_rpm=0,r_rpm=0,v=0,w=0,x=0,y=0,th=0)
def line(d):return (json.dumps(d)+'\n').encode()
class Clock:
 def __init__(self):self.t=100.
 def mono(self):return self.t
 def sleep(self,t):self.t+=t
class Stream:
 def __init__(self,c,lines):self.c=c;self.lines=list(lines);self.closed=False;self.tx=[]
 def readline(self,size):self.c.t+=.1;return self.lines.pop(0) if self.lines else b''
 def close(self):self.closed=True
 def write(self,data):self.tx.append(data);raise AssertionError('TX prohibited')
 def flush(self):self.tx.append('flush');raise AssertionError('TX prohibited')
cases=[]
def run(name,lines,expected_code):
 c=Clock();ser=Stream(c,lines)
 argv=['collector','--mock','--wall-timeout','15','--min-obs','10','--min-samples','80','--max-samples','120','--output-dir',str(outdir)]
 with patch.object(m,'MockSerialStream',return_value=ser),patch.object(m.time,'monotonic',side_effect=c.mono),patch.object(m.time,'sleep',side_effect=c.sleep),patch.object(sys,'argv',argv),patch.object(sys,'stdout',new_callable=io.StringIO) as stdout:
  try:m.main()
  except SystemExit as e:code=e.code
 rep=json.loads(stdout.getvalue());evidence=json.loads(pathlib.Path(rep['evidence_file']).read_text()) if rep.get('evidence_file') else None
 cases.append(dict(id=name,expected_exit=expected_code,actual_exit=code,meets_expectation=code==expected_code,report=rep,tx=list(ser.tx),closed=ser.closed,evidence=evidence))
run('positive_exact_hardware_boot_then_D0',boot+[line(d0)]*120,0)
run('boot_only_never_D0',boot,1)
run('exact_banner_then_unsafe_PWM',[line({'info':banner}),line(dict(d0,l_pwm=1))],1)
run('banner_co_located_ARMED_PWM',[line(dict(d0,info=banner,safety='ARMED',l_pwm=1))]+[line(d0)]*120,1)
run('banner_co_located_FAULT_error',[line({'info':banner,'error':'MKE_M18_INIT_FAILED','safety':'FAULT'})]+[line(d0)]*120,1)
run('forged_substring_banner',[line({'info':'arbitrary BENCH SERIAL ONLY fake'})]+[line(d0)]*120,1)
run('unknown_JSON_missing_safety',[line({'foo':'bar'})]+[line(d0)]*120,1)
after=hashlib.sha256(src.read_bytes()).hexdigest()
assert before==after
assert all(not x['tx'] and x['closed'] for x in cases)
result=dict(scope='OFFLINE actual main CLI/fake stream/fake clock; no Serial hardware',before=before,after=after,outdir=str(outdir),cases=cases)
with (ROOT/'evidence_agv_20261001/review_banner_classifier_20261002_0804.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'before':before,'after':after,'cases':[{k:x[k] for k in ['id','expected_exit','actual_exit','meets_expectation','tx','closed']} for x in cases]},ensure_ascii=False))
