// Executes the real dashboard with a fake HTTP peer; never reaches a vehicle.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '..', 'index_cyberpunk.html'), 'utf8')
  .match(/<script>([\s\S]*?)<\/script>/)[1];

function page(stopReason = 'STOP_CONFIRMED', stopOk = true) {
  const commands = [];
  const drawCalls = [];
  const intervals = [];
  let telemetry = {};
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {value:'0', innerText:'', innerHTML:'', style:{},
      classList:{add(){}, remove(){}, toggle(){}}, addEventListener(){},
      getContext:()=>new Proxy({}, {get:(_,name)=>(...args)=>drawCalls.push([name,...args])}), width:600, height:600});
    return elements.get(id);
  };
  const context = {
    console, AbortSignal, Blob, URL,
    fetch:async url=>{
      if (url === '/api/telemetry') return {ok:true,json:async()=>telemetry};
      if (!url.startsWith('/api/cmd?')) return {ok:true,json:async()=>({})};
      const cmd = new URL(url, 'http://offline.test').searchParams.get('val');
      commands.push(cmd);
      return {ok:cmd !== 'STOP' || stopOk,
        json:async()=>({reason:cmd === 'STOP' ? stopReason : 'RESET_SENT_AWAIT_ACK_AND_ZERO_D0'})};
    },
    document:{getElementById:get,querySelectorAll:()=>[],querySelector:()=>get('pid'),
      addEventListener(){},createElement:()=>({click(){}})},
    window:{addEventListener(){}},
    localStorage:{getItem:()=>null,setItem(){},removeItem(){}},
    setTimeout:()=>1,setInterval:(fn,ms)=>{intervals.push({fn,ms});return intervals.length;},clearInterval(){},requestAnimationFrame(){},confirm:()=>false
  };
  vm.createContext(context); vm.runInContext(script,context);
  return {commands,get,drawCalls,run:s=>vm.runInContext(s,context),poll:async ai=>{
    telemetry={robot:{x:0,y:0,th:0,l_rpm:0,r_rpm:0},ranges:[],control:{},ai};
    intervals.find(t=>t.ms===100).fn();
    await new Promise(resolve=>setImmediate(resolve));
  }};
}

(async()=>{
  const cases = [
    ['speed controls reflect backend values and manual directions use RPM',async()=>{
      const p=page();p.run("syncAutoSpeedConfig({speed_config:{speed_rpm:65,turn_rpm:65,cruise_mps:.249128,turn_w:2.595},control:{latest_d0:{l_tgt:40,r_tgt:65}}})");
      assert.equal(p.get('sliderAutoSpeed').value,65);
      assert.match(p.get('valAutoSpeedLbl').innerText,/65 RPM/);
      assert.match(p.get('valAutoTurnLbl').innerText,/65 RPM/);
      assert.match(p.get('valAutoWheelTargets').innerText,/40.0 \/ 65.0 RPM/);
      assert.equal(p.run('CMD_SPEED.W'),'S 65 65');
      assert.equal(p.run('CMD_SPEED.S'),'S -65 -65');
      assert.equal(p.run('CMD_SPEED.Q'),'S -65 65');
      assert.equal(p.run("activeKeys.add('KeyW');activeKeys.add('KeyA');getCombinedKeyCommand()"),'S 40 65');
      assert.deepEqual(p.commands,[]);
    }],
    ['shadow AI roles stay stable while scan readiness and counts fluctuate',async()=>{
      const p=page();
      const ai={ai1_loaded:true,ai2_loaded:true,ai1_mode:'shadow',ai2_mode:'shadow',ai1_active:false};
      await p.poll({...ai,ai1_scan_ready:false,ai1_scan_valid_bins:329,ai1_scan_blocker:'AI1_LIDAR_UNOBSERVED_SECTOR'});
      const before=p.get('valAiStatus').innerText;
      assert.equal(before,'AI1: QUAN SÁT · AI2: QUAN SÁT');
      assert.match(p.get('valAiStatus').title,/329\/360/);
      await p.poll({...ai,ai1_scan_ready:true,ai1_scan_valid_bins:358});
      assert.equal(p.get('valAiStatus').innerText,before);
      assert.match(p.get('valAiStatus').title,/358\/360/);
      assert.deepEqual(p.commands,[]);
    }],
    ['AI2 remains visible when AI1 is not loaded',async()=>{
      const p=page();await p.poll({ai1_loaded:false,ai1_mode:'shadow',ai2_loaded:true,ai2_mode:'shadow'});
      assert.equal(p.get('valAiStatus').innerText,'AI1: CHƯA NẠP · AI2: QUAN SÁT');
    }],
    ['actual AI control failure remains visible immediately',async()=>{
      const p=page();await p.poll({ai1_loaded:true,ai1_mode:'control',ai1_active:false,
        ai1_error:'AI1_LIDAR_UNOBSERVED_SECTOR',ai2_mode:'off'});
      assert.equal(p.get('valAiStatus').innerText,'AI1: A* DỰ PHÒNG · AI2: TẮT');
      assert.match(p.get('valAiStatus').title,/AI1_LIDAR_UNOBSERVED_SECTOR/);
      await p.poll({ai1_loaded:true,ai1_mode:'control',ai1_active:true,ai1_v:.15,ai1_w:.4,ai2_mode:'off'});
      assert.equal(p.get('valAiStatus').innerText,'AI1: ĐANG LÁI · AI2: TẮT');
    }],
    ['SLAM robot marker uses map TF coordinates rather than raw odometry',async()=>{
      const p=page();p.drawCalls.length=0;
      p.run("currentView='slam'; mapData={w:10,h:10,res:.1,ox:0,oy:0,data:Array(100).fill(0)}; teleData={robot:{x:99,y:99,th:0},map_info:{robot_pose:[.2,.3,0]}}; render()");
      const marker=p.drawCalls.find(call=>call[0]==='arc');
      assert.ok(marker);
      assert.ok(Math.abs(marker[1]-120)<1e-6 && Math.abs(marker[2]-360)<1e-6);
    }],
    ['RESET stops and waits for MCU confirmation before clearing faults',async()=>{
      const p=page(); await p.run('resetFault()');
      assert.deepEqual(p.commands,['STOP','RESET']);
      assert.match(p.get('commandNotice').innerText,/CHỜ/);
      assert.doesNotMatch(p.get('commandNotice').innerText,/ĐÃ RESET KHÓA/);
    }],
    ['STOP timeout prevents RESET',async()=>{
      const p=page('STOP_UNCONFIRMED',false); await p.run('resetFault()');
      assert.deepEqual(p.commands,['STOP']);
      assert.match(p.get('commandNotice').innerText,/STOP_UNCONFIRMED/);
    }],
    ['HTTP success without STOP confirmation cannot authorize RESET',async()=>{
      const p=page('STOPPED'); await p.run('resetFault()');
      assert.deepEqual(p.commands,['STOP']);
    }]
  ];
  let failures=0;
  for (const [name,test] of cases) {
    try { await test(); console.log('PASS '+name); }
    catch(error) { failures++; console.error('FAIL '+name+'\n'+error); }
  }
  if (failures) process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
