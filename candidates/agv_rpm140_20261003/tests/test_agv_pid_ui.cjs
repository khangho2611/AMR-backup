// Executes the actual dashboard script against a minimal DOM. No network/vehicle.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname,'..','index_cyberpunk.html'),'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function page(fetch) {
  const elements = new Map();
  const listeners = {};
  const storage = {};
  const intervals = [];
  const get = id => {
    if (!elements.has(id)) elements.set(id,{value:'0',innerText:'',innerHTML:'',style:{},
      classList:{add(){},remove(){},toggle(){}},addEventListener(){},
      getContext:()=>new Proxy({}, {get:()=>()=>{}}),width:600,height:600});
    return elements.get(id);
  };
  const context = {console,fetch,AbortSignal,Blob,URL,
    document:{getElementById:get,querySelectorAll:()=>['btnQ','btnW','btnE','btnA','btnD','btnS'].map(get),querySelector:()=>get('pidButton'),addEventListener:(n,f)=>{listeners[n]=f;},
      createElement:()=>({click(){}})},
    window:{addEventListener:(n,f)=>{listeners[n]=f;}},
    localStorage:{getItem:k=>storage[k],setItem:(k,v)=>{storage[k]=v;},removeItem:k=>delete storage[k]},
    setTimeout:()=>1,setInterval:(fn,ms)=>{intervals.push({fn,ms});return intervals.length;},clearInterval(){},requestAnimationFrame(){},confirm:()=>false};
  vm.createContext(context);vm.runInContext(script,context);
  return {context,get,storage,listeners,intervals,run:s=>vm.runInContext(s,context)};
}

(async () => {
  let calls=0;
  const p=page(async url=>{calls++;assert.match(url,/kp=0&ki=0&kd=0&kf=0\.45/);
    return {ok:true,json:async()=>({status:'APPLIED',reason:'MCU_ACK_MATCHED'})};});
  await p.run('applyPidMini()');
  assert.equal(JSON.parse(p.storage.agv_pid_history)[0].status,'APPLIED');
  assert.equal(calls,1);
  console.log('PASS zero PID and fixed Kf');

  for (const status of ['FAILED','REJECTED']) {
    const p=page(async()=>({ok:false,json:async()=>({status,reason:'real, failure'})}));
    await p.run('applyPidMini()');
    assert.equal(JSON.parse(p.storage.agv_pid_history)[0].status,status);
    assert.match(p.get('historyTableBody').innerHTML,new RegExp(status));
  }
  console.log('PASS FAILED vs REJECTED are distinct and persisted');

  const disconnected=page(async()=>{throw new Error('offline');});
  await disconnected.run('applyPidMini()');
  assert.equal(JSON.parse(disconnected.storage.agv_pid_history)[0].status,'FAILED');
  console.log('PASS disconnect recorded without synthetic MCU success');

  let forbidden=false;
  const invalid=page(async()=>{forbidden=true;throw new Error('should not fetch');});
  invalid.get('inputKpMini').value='';await invalid.run('applyPidMini()');assert.equal(forbidden,false);
  invalid.get('inputKpMini').value='Infinity';await invalid.run('applyPidMini()');assert.equal(forbidden,false);
  console.log('PASS empty/nonfinite input rejected before fetch');

  let release;
  const busy=page(()=>new Promise(resolve=>{release=resolve;}));
  const pending=busy.run('applyPidMini()');
  assert.equal(JSON.parse(busy.storage.agv_pid_history)[0].status,'PENDING');
  await busy.run('applyPidMini()');
  assert.equal(JSON.parse(busy.storage.agv_pid_history).length,1);
  release({ok:true,json:async()=>({status:'APPLIED',reason:'MCU_ACK_MATCHED'})});await pending;
  console.log('PASS pending is persistent; duplicate clicks do not dispatch');

  let drive=0;
  const keyboard=page(async()=>{drive++;return {ok:true,json:async()=>({})};});
  keyboard.listeners.keydown({target:{tagName:'INPUT'},code:'KeyW',preventDefault(){}});
  assert.equal(drive,0);
  assert.ok(keyboard.listeners.blur);
  keyboard.listeners.blur();
  await Promise.resolve();
  assert.equal(drive,0,'Idle browser blur must not reset a healthy preflight via STOP');
  console.log('PASS typing PID does not drive; blur has release handler');

  const stopped=[];
  const emergency=page(async url=>{stopped.push(url);return {ok:true,json:async()=>({status:'SENT'})};});
  emergency.run('emergencyStop()');
  await Promise.resolve();
  assert.equal(stopped.length,1);
  assert.match(stopped[0],/val=STOP/);
  console.log('PASS emergency stop dispatches exactly one STOP transaction');

  emergency.run('updateTrialUI({auto:false,control:{motion_window_s:15,preflight_ready:false,trial_used:false,armed:false}})');
  assert.equal(emergency.get('btnArm').disabled,true);
  emergency.run('updateTrialUI({auto:false,control:{motion_window_s:15,preflight_ready:true,trial_used:false,armed:false}})');
  assert.equal(emergency.get('btnArm').disabled,false);
  assert.equal(emergency.get('btnAuto').disabled,true);
  assert.equal(emergency.get('pidButton').disabled,true);
  emergency.run('updateTrialUI({auto:false,control:{motion_window_s:15,preflight_ready:true,trial_used:true,armed:false,fault:"TRIAL_WINDOW_COMPLETE"}})');
  assert.equal(emergency.get('btnArm').disabled,true);
  assert.equal(emergency.get('btnAuto').disabled,true);
  assert.equal(emergency.run('isAutoRunning'),false);
  console.log('PASS trial UI waits for preflight, blocks reARM and reflects stopped AUTO');

  const continuous=page(async()=>({ok:true,json:async()=>({})}));
  continuous.run('updateTrialUI({auto:false,control:{motion_window_s:null,preflight_ready:true,armed:false,latched:true,fault:null}})');
  assert.equal(continuous.get('btnArm').disabled,false);
  assert.equal(continuous.get('btnAuto').disabled,true);
  assert.doesNotMatch(continuous.get('btnArm').innerText,/15|TEST/);
  continuous.run('updateTrialUI({auto:true,control:{motion_window_s:null,preflight_ready:false,armed:true,latched:false,fault:null}})');
  assert.equal(continuous.get('btnArm').disabled,true);
  assert.equal(continuous.get('btnAuto').disabled,false);
  assert.equal(continuous.get('btnW').disabled,false,'MAN takeover stays available while AUTO runs');
  assert.match(continuous.get('autoText').innerText,/DỪNG/);
  continuous.run('updateTrialUI({auto:false,control:{motion_window_s:null,preflight_ready:false,armed:false,latched:true,fault:"TELEMETRY_TIMEOUT"}})');
  assert.equal(continuous.get('btnArm').disabled,true);
  assert.equal(continuous.get('btnAuto').disabled,true);
  console.log('PASS continuous operator UI has no trial timer and keeps ARM/FAULT gating');

  const manualCalls=[];
  const manual=page(async url=>{manualCalls.push(url);return {ok:true,json:async()=>({status:'SENT'})};});
  manual.run("startDrive('M 140 140'); stopDrive(); startDrive('M -140 -140'); stopDrive()");
  await new Promise(setImmediate);
  assert.equal(manualCalls.filter(url=>/val=STOP/.test(url)).length,0);
  assert.equal(manualCalls.filter(url=>url.includes('V%200.000%200.000')).length,2);
  assert.ok(manualCalls.some(url=>url.includes('M%20-140%20-140')));
  manual.listeners.blur();await Promise.resolve();
  assert.equal(manualCalls.filter(url=>/val=STOP/.test(url)).length,1);
  console.log('PASS release stops wheels without DISARM; next direction works; focus loss sends STOP');

  const rpmCalls=[];
  const rpmPage=page(async url=>{rpmCalls.push(decodeURIComponent(url));return {ok:true,json:async()=>({status:'SENT'})};});
  rpmPage.listeners.keydown({code:'KeyW',repeat:false,preventDefault(){}});
  await new Promise(setImmediate);
  assert.ok(rpmCalls.includes('/api/cmd?val=V 0.536 0.000'));
  rpmPage.listeners.keyup({code:'KeyW',preventDefault(){}});
  rpmPage.listeners.keydown({code:'KeyS',repeat:false,preventDefault(){}});
  await new Promise(setImmediate);
  assert.ok(rpmCalls.includes('/api/cmd?val=V -0.536 0.000'));
  console.log('PASS candidate forward/reverse keys request velocity, not PWM140');

  const rejectedAuto=page(async()=>({ok:false,json:async()=>({status:'FAILED',auto:false,
    reason:'EXPLICIT_ARM_FRESH_MAP_TF_AND_BODY_RADIUS_REQUIRED',blockers:['NOT_ARMED','TF_NOT_READY'],
    journal:{id:'test-id',saved:true}})}));
  await rejectedAuto.run('toggleAuto()');
  assert.match(rejectedAuto.get('statusBadge').innerText,/NOT_ARMED/);
  assert.match(rejectedAuto.get('statusBadge').innerText,/TF_NOT_READY/);
  assert.match(rejectedAuto.get('commandNotice').innerText,/TF_NOT_READY/);
  console.log('PASS AUTO rejection shows each gate instead of a generic message');

  const confirmedArm=page(async()=>({ok:true,json:async()=>({status:'SENT',reason:'ARM_CONFIRMED'})}));
  await confirmedArm.run("sendCmd('ARM')");
  assert.doesNotMatch(confirmedArm.get('statusBadge').innerText,/CHỜ ACK/);
  console.log('PASS confirmed ARM is not mislabeled as waiting for ACK');

  const retained=page(async url=>({ok:url==='/api/telemetry',json:async()=>url==='/api/telemetry'
    ? {auto:false,robot:{x:0,y:0,th:0,l_rpm:0,r_rpm:0},min_m:1,min_ang:0,status:'SAFE'}
    : {status:'FAILED',auto:false,reason:'TF_NOT_READY',blockers:['TF_NOT_READY']}}));
  await retained.run('toggleAuto()');
  retained.intervals.find(x=>x.ms===100).fn();
  await new Promise(setImmediate);
  assert.match(retained.get('commandNotice').innerText,/TF_NOT_READY/);
  assert.doesNotMatch(retained.get('statusBadge').innerText,/TF_NOT_READY/);
  console.log('PASS live telemetry does not erase the last command rejection');
})().catch(e=>{console.error(e);process.exitCode=1;});
