"""Actual reader, HTTP handlers and typed callbacks; no ROS daemon or port OPEN.

The positive test advances real wall-clock time for the entire 10-second
preflight. Node construction/ROS executor and physical UART remain untested.
"""
import csv
import io
import json
import math
import queue
import threading
import time
import types
import unittest
import urllib.error
import urllib.parse
import urllib.request

from test_agv_navigation_fix import load_brain
from agv_command_session import CommandSession
from agv_preflight_static_collector import EXACT_BOOT_BANNER, EXACT_I2C_SCAN_BANNER

N = types.SimpleNamespace


def d0(**changes):
    p=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0.,r_rpm=0.,
           l_pwm=0,r_pwm=0,x=1.3,y=1.25,th=0.,v=0.,w=0.)
    p.update(changes)
    return p


def header(frame='map',age=0.):
    t=time.time()-age
    return N(frame_id=frame,stamp=N(sec=int(t),nanosec=int((t-int(t))*1e9)))


class LoopbackUART:
    def __init__(self):
        self.rx=queue.Queue();self.writes=[];self.is_open=True;self.armed=False
        self.partial=False;self.reject_pid=False

    @property
    def in_waiting(self):
        return self.rx.qsize()

    def emit(self,p):
        self.rx.put((json.dumps(p)+'\n').encode())

    def readline(self,size):
        try:return self.rx.get_nowait()
        except queue.Empty:return b''

    def write(self,payload):
        self.writes.append(payload)
        if self.partial:return 1
        if payload==b'ARM\n':
            self.armed=True
            self.emit({'ack':'ARM','state':'ARMED'})
            self.emit(d0(safety='ARMED'))
        elif payload==b'STOP\n':
            self.armed=False;self.emit(d0())
        elif payload.startswith(b'TUNING '):
            self.emit({'error':'INVALID_TUNING_RANGE'} if self.reject_pid else {'ack':payload.decode().strip()})
        return len(payload)

    def close(self):self.is_open=False


class BrainIntegration(unittest.TestCase):
    def setUp(self):
        self.m=load_brain();self.m.state=self.m.AGVSharedState()
        self.node=self.m.AGVROSNode.__new__(self.m.AGVROSNode)
        self.uart=LoopbackUART();self.node.ser=self.uart
        self.node.control=CommandSession(self.uart)
        self.node.initialize_navigation();self.node._rx_line=b''
        self.node._reader_stop=threading.Event()
        self.node._reader_thread=threading.Thread(target=self.node._reader_worker,daemon=True)
        self.node._watchdog_thread=threading.Thread(target=self.node._watchdog_worker,daemon=True)
        self.node.get_clock=lambda:N(now=lambda:N(nanoseconds=time.time_ns()))
        q=N(x=0.,y=0.,z=0.,w=1.)
        self.node.tf_buffer=N(lookup_transform=lambda *a:N(header=header(),transform=N(
            translation=N(x=1.3,y=1.25,z=0.),rotation=q)))
        self.m.ros_node=self.node
        self.server=self.m.ThreadedHTTPServer(('127.0.0.1',0),self.m.WebHandler)
        self.http=threading.Thread(target=self.server.serve_forever,daemon=True);self.http.start()
        self.node._reader_thread.start();self.node._watchdog_thread.start()
        self.producer_stop=threading.Event();self.producer=None

    def tearDown(self):
        # Keep the fake reader alive until product STOP/cleanup has completed.
        self.node.close_control()
        self.producer_stop.set()
        if self.producer:self.producer.join(.5)
        self.server.shutdown();self.server.server_close();self.http.join(.5)
        self.assertFalse(self.node._reader_thread.is_alive())
        self.assertFalse(self.node._watchdog_thread.is_alive())
        self.assertFalse(self.uart.is_open)

    def get(self,path):
        try:
            response=urllib.request.urlopen(f'http://127.0.0.1:{self.server.server_port}'+path,timeout=2)
        except urllib.error.HTTPError as response:
            return response.code,json.loads(response.read())
        with response:return response.status,json.loads(response.read())

    def scan(self,age=0.):
        return N(header=header('base_footprint',age),angle_min=-math.pi,
                 angle_increment=math.pi/180,range_min=.05,range_max=8.,ranges=[2.]*360)

    def map(self,frame='map',age=0.):
        data=[0]*(70*50)
        for y in range(50):data[y*70]=data[y*70+69]=-1
        return N(header=header(frame,age),info=N(width=70,height=50,resolution=.05,
                 origin=N(position=N(x=0.,y=0.),orientation=N(x=0.,y=0.,z=0.,w=1.))),data=data)

    def test_actual_reader_http_ack_drive_stop_and_pid_real_ten_seconds(self):
        self.m.state.body_radius_m=.05  # Synthetic fixture, not a vehicle measurement.
        for p in ({'info':EXACT_BOOT_BANNER},{'info':EXACT_I2C_SCAN_BANNER},
                  {'i2c_found':'0x42'},{'vin_mv':12033}):self.uart.emit(p)
        def produce():
            while not self.producer_stop.is_set():
                self.uart.emit(d0(safety='ARMED' if self.uart.armed else 'DISARMED'))
                self.node.scan_cb(self.scan());self.node.map_cb(self.map())
                self.producer_stop.wait(.10)
        self.producer=threading.Thread(target=produce,daemon=True);self.producer.start()
        deadline=time.monotonic()+12.
        while not self.node.control.preflight_ready(self.node.control.clock()) and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue(self.node.control.preflight_ready(self.node.control.clock()))
        self.assertGreaterEqual(self.node.control.last_d0-self.node.control.stable_start,10.)
        self.assertGreaterEqual(self.node.control.stable_count,80)
        arm_result=self.get('/api/cmd?val=ARM')
        self.assertEqual(arm_result[0],200,(arm_result,self.node.control.health(),self.uart.writes))
        self.assertEqual(self.get('/api/auto?act=START')[0],200)
        self.assertEqual(self.node.home,(1.3,1.25,0.))
        self.assertTrue(self.m.state.auto_mode)
        self.node.auto_nav_loop()
        self.assertIsNotNone(self.node.goal)
        first=self.node.goal;self.node._exclude_goal(time.monotonic())
        self.node.auto_nav_loop()
        self.assertGreater(self.node.goal[0],3.)
        self.assertGreater(math.dist(first,self.node.goal),2.)
        self.assertEqual(self.get('/api/cmd?val='+urllib.parse.quote('V 0.040 0.000'))[0],200)
        # Real product watchdog thread must stop a silent caller even though
        # the fake MCU and scan producer continue sending fresh data.
        time.sleep(.26)
        self.assertEqual(self.node.control.fault,'CALLER_TIMEOUT')
        self.assertTrue(self.node.control.latched)
        self.assertIn(b'STOP\n',self.uart.writes)
        self.assertEqual(self.get('/api/cmd?val=STOP')[0],200)
        health=self.get('/api/telemetry')[1]['control']
        self.assertTrue(health['stop_confirmed']);self.assertTrue(health['latched'])
        pid_result=self.get('/api/pid?kp=0&ki=0&kd=0')[1]
        self.assertEqual(pid_result['status'],'APPLIED',(pid_result,self.uart.writes,self.node.control.health()))
        self.uart.reject_pid=True
        reject_result=self.get('/api/pid?kp=1&ki=2&kd=.01')[1]
        self.assertEqual(reject_result['status'],'REJECTED',(reject_result,self.node.control.health(),self.uart.writes))
        records=list(csv.reader(io.StringIO(self.node.control.history_csv())))
        self.assertTrue(all(len(row)==8 for row in records))
        self.assertEqual(self.uart.writes.count(b'ARM\n'),1)
        self.assertFalse(any(p.startswith(b'M ') for p in self.uart.writes))

    def test_map_epoch_preserves_home_on_expansion_but_not_frame_change(self):
        self.node.map_cb(self.map());self.node.home=(1.,1.,.5)
        expanded=self.map();expanded.info.width=71
        expanded.data=[0]*(71*50);expanded.info.origin.position.x=-.05
        self.node.map_cb(expanded)
        self.assertEqual(self.node.home,(1.,1.,.5))
        self.node.map_cb(self.map(frame='other_map'))
        self.assertIsNone(self.node.home);self.assertFalse(self.m.state.auto_mode)

    def test_old_stamped_map_and_scan_are_not_made_fresh_by_callback(self):
        self.node.map_cb(self.map(age=3.))
        self.assertFalse(self.m.state.map_received)
        self.node.scan_cb(self.scan(age=.5))
        self.assertEqual(self.node.control.fault,'STALE_SCAN_STAMP')
        self.assertIsNone(self.node.control.scan_time)

    def test_http_partial_stop_has_immediate_fault_and_no_confirmation(self):
        self.uart.partial=True
        code,_=self.get('/api/cmd?val=STOP')
        self.assertEqual(code,422)
        health=self.get('/api/telemetry')[1]['control']
        self.assertEqual(health['fault'],'STOP_WRITE_FAILED')
        self.assertFalse(health['stop_confirmed'])
        self.assertEqual(health['escalation'],'CUT_POWER_IF_MOVING')

    def test_http_diagnostics_is_read_only_in_observe_mode(self):
        self.m.observe_only = True
        before = list(self.uart.writes)
        with urllib.request.urlopen(f'http://127.0.0.1:{self.server.server_port}/api/diagnostics',timeout=2) as response:
            self.assertEqual(response.headers.get_content_type(),'application/json')
            report = json.loads(response.read())
        self.assertEqual(report['event_capacity'],256)
        self.assertIsNone(report['first_fault'])
        self.assertEqual(self.uart.writes,before)
        self.assertFalse(self.node.control.armed)


if __name__=='__main__':unittest.main()
