"""Entry/constructor regressions; physical port OPEN is replaced by a fake."""
import types
import json
import threading
import tempfile
from pathlib import Path
import urllib.request
import urllib.error
import unittest
from unittest.mock import patch
from test_agv_navigation_fix import load_brain
from agv_command_session import CommandSession

N = types.SimpleNamespace

class FakeNode:
    def __init__(self, name): pass
    def get_logger(self): return N(info=lambda *a:None, error=lambda *a:None)
    def create_timer(self, *a): pass
    def create_subscription(self, *a): pass
    def create_publisher(self,*a): return N(publish=lambda *a:None)

class Lifecycle(unittest.TestCase):
    def test_operator_control_starts_disarmed_without_a_trial_deadline(self):
        m=load_brain();events=[]
        server=N(serve_forever=lambda:events.append('serve'),server_close=lambda:events.append('http_close'))
        node=N(close_control=lambda:(events.append('close') or True),destroy_node=lambda:None)
        m.rclpy.init=lambda:None
        m.rclpy.spin=lambda n:None
        m.rclpy.shutdown=lambda:None
        with patch.object(m,'ThreadedHTTPServer',return_value=server), \
             patch.object(m,'AGVROSNode',return_value=node):
            m.main(['--operator-control'])
        self.assertIsNone(m.motion_window_s_config)
        self.assertFalse(m.observe_only)
        self.assertEqual(events,['serve','close','http_close'])

    def test_observe_mode_http_rejects_arm_drive_pid_auto_before_dispatch(self):
        m=load_brain();calls=[]
        m.observe_only=True
        control=CommandSession(None)
        control.tuning=lambda *a:calls.append(a)
        m.ros_node=N(send_cmd=lambda *a:calls.append(a),control=control)
        journal_folder=tempfile.TemporaryDirectory()
        server=m.ThreadedHTTPServer(('127.0.0.1',0),m.WebHandler,
                                   journal_path=Path(journal_folder.name)/'commands.jsonl')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for path in ['/api/cmd?val=ARM','/api/cmd?val=V%200.04%200',
                         '/api/pid?kp=1&ki=1&kd=0','/api/auto?act=START']:
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}'+path,timeout=1)
                self.assertEqual(raised.exception.code,423)
                self.assertEqual(json.loads(raised.exception.read())['reason'],'OBSERVE_ONLY')
            self.assertEqual(calls,[])
        finally:
            server.shutdown();server.server_close();thread.join(.5)
            journal_folder.cleanup()

    def test_dashboard_only_never_initializes_ros_or_opens_serial(self):
        m=load_brain()
        closed=[]
        server=N(serve_forever=lambda:None, server_close=lambda:closed.append(True))
        with patch.object(m,'ThreadedHTTPServer',return_value=server), \
             patch.object(m,'AGVROSNode',side_effect=AssertionError('must not construct robot')):
            m.main(['--dashboard-only'])
        self.assertEqual(closed,[True])
        self.assertIsNone(m.ros_node)

    def test_http_bind_failure_never_opens_hardware_or_initializes_ros(self):
        m=load_brain()
        events=[]
        m.rclpy.init=lambda:events.append('init')
        m.rclpy.shutdown=lambda:events.append('shutdown')
        with patch.object(m,'ThreadedHTTPServer',side_effect=OSError('port occupied')), \
             patch.object(m,'AGVROSNode',side_effect=AssertionError('must not construct robot')):
            with self.assertRaisesRegex(OSError,'port occupied'): m.main(['--observe-only'])
        self.assertEqual(events,[])

    def test_constructor_failure_closes_http_and_ros(self):
        m=load_brain();events=[]
        server=N(server_close=lambda:events.append('http_close'))
        m.rclpy.init=lambda:events.append('init')
        m.rclpy.shutdown=lambda:events.append('shutdown')
        with patch.object(m,'ThreadedHTTPServer',return_value=server), \
             patch.object(m,'AGVROSNode',side_effect=RuntimeError('TF init failed')):
            with self.assertRaisesRegex(RuntimeError,'TF init failed'):m.main(['--observe-only'])
        self.assertEqual(events,['init','http_close','shutdown'])

    def constructor_module(self):
        m=load_brain(FakeNode)
        m.TransformBroadcaster=lambda *a:N()
        m.Buffer=lambda:N()
        m.TransformListener=lambda *a:N()
        m.QoSProfile=lambda **kw:N()
        m.ReliabilityPolicy=N(BEST_EFFORT=1,RELIABLE=2)
        m.HistoryPolicy=N(KEEP_LAST=1)
        m.DurabilityPolicy=N(TRANSIENT_LOCAL=1)
        return m

    def test_tf_constructor_failure_occurs_before_serial_open(self):
        m=self.constructor_module();calls=[]
        m.TransformBroadcaster=lambda *a:(_ for _ in ()).throw(RuntimeError('TF failed'))
        m.serial.Serial=lambda *a,**kw:calls.append(kw)
        with self.assertRaisesRegex(RuntimeError,'TF failed'):m.AGVROSNode()
        self.assertEqual(calls,[])

    def test_serial_is_configured_closed_with_low_rts_dtr_before_open(self):
        m=self.constructor_module();events=[]
        class UART:
            is_open=False
            def open(self):
                events.append(('open',self.port,self.rts,self.dtr));self.is_open=True
            def close(self):events.append('close');self.is_open=False
        def factory(*a,**kw):
            self.assertIsNone(kw.get('port'))
            self.assertEqual(kw['write_timeout'],.2)
            self.assertTrue(kw['exclusive'])
            return UART()
        m.serial.Serial=factory
        with patch.object(m,'acquire_port_lock',return_value=('owner','path')), \
             patch.object(m,'cleanup_lock'), \
             patch.object(m.AGVROSNode,'_reader_worker'), \
             patch.object(m.AGVROSNode,'_watchdog_worker'):
            node=m.AGVROSNode()
        self.assertTrue(hasattr(node,'pub_slam_scan'))
        self.assertEqual(events,[('open',m.SERIAL_PORT,False,False)])
        node.ser.close()

    def test_failed_open_releases_owner_and_closes_stream(self):
        m=self.constructor_module();events=[]
        class UART:
            def open(self):raise OSError('USB unavailable')
            def close(self):events.append('close')
        m.serial.Serial=lambda **kw:UART()
        with patch.object(m,'acquire_port_lock',return_value=('owner','path')), \
             patch.object(m,'cleanup_lock',side_effect=lambda *a:events.append('unlock')):
            with self.assertRaisesRegex(OSError,'USB unavailable'):m.AGVROSNode()
        self.assertEqual(events,['close','unlock'])

if __name__=='__main__':unittest.main()
