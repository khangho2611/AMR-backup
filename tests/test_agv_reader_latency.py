import io,json,threading,types,unittest
from unittest.mock import patch
from test_agv_navigation_fix import load_brain
from agv_command_session import CommandSession
from agv_preflight_static_collector import EXACT_BOOT_BANNER,EXACT_I2C_SCAN_BANNER

class BulkUART:
    is_open=True
    def __init__(self,data):self.data=data;self.reads=0;self.writes=[]
    @property
    def in_waiting(self):return len(self.data)
    def read(self,n):
        self.reads+=1;out=self.data[:n];self.data=self.data[n:];return out
    def readline(self,n):raise AssertionError('Per-byte readline must not run in production reader')
    def write(self,p):self.writes.append(p);return len(p)

class ReaderLatency(unittest.TestCase):
    def node(self):
        self.m=load_brain();self.m.state=self.m.AGVSharedState()
        n=self.m.AGVROSNode.__new__(self.m.AGVROSNode)
        p=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=1.,y=2.,th=0.,v=0.,w=0.)
        rows=[{'info':EXACT_BOOT_BANNER},{'info':EXACT_I2C_SCAN_BANNER},{'i2c_found':'0x42'},p,p]
        n.ser=BulkUART(b''.join((json.dumps(x)+'\n').encode() for x in rows));n.control=CommandSession(n.ser);n._rx_line=b''
        return n,p
    def test_bulk_multiple_lines_and_partial_tail(self):
        n,p=self.node();n.ser.data+=b'{"ack":'
        n.serial_read_loop();self.assertEqual(n.control.latest,p);self.assertEqual(n.ser.reads,1)
        n.ser.data=b'"PONG"}\n';n.serial_read_loop();self.assertIsNone(n.control.fault)
    def test_dashboard_lock_does_not_block_uart_ingestion(self):
        n,p=self.node();done=threading.Event()
        self.m.state.lock.acquire()
        try:
            t=threading.Thread(target=lambda:(n.serial_read_loop(),done.set()));t.start()
            self.assertTrue(done.wait(.1));self.assertEqual(n.control.latest,p)
        finally:self.m.state.lock.release();t.join(1)
    def test_http_journal_does_not_duplicate_entire_command_ring(self):
        n,p=self.node();self.m.ros_node=n
        n.control.diagnostics=lambda:(_ for _ in ()).throw(AssertionError('Full diagnostics in each command'))
        records=[];h=self.m.WebHandler.__new__(self.m.WebHandler)
        h.server=types.SimpleNamespace(command_journal=types.SimpleNamespace(record=lambda *a:records.append(a) or {}));h._json=lambda *a:None
        h._command_reply(200,{'status':'SENT'},'COMMAND',{'val':'V 0 0'})
        self.assertIn('event_sequence',records[0][-1]);self.assertNotIn('command_events',records[0][-1])
    def test_snapshot_copies_outside_control_mutex(self):
        n,p=self.node();real=__import__('copy').deepcopy;acquired=[]
        def check(value):
            t=threading.Thread(target=lambda:(n.control.lock.acquire(),acquired.append(True),n.control.lock.release()))
            t.start();t.join(.1)
            self.assertTrue(acquired,'Deepcopy holds control lock');return real(value)
        with patch('agv_command_session.copy.deepcopy',side_effect=check):n.control.diagnostics()

if __name__=='__main__':unittest.main()
