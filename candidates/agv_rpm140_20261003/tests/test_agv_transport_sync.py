"""Same-owner transport handshake; no physical UART."""
import threading,time,unittest
import test_agv_navigation_fix as fixtures

class TransportSyncRegression(unittest.TestCase):
    def setUp(self):
        self.h=fixtures.SessionRegression();self.h.setUp();self.h.ready()
        self.s=self.h.s;self.u=self.h.uart
        self.s.require_transport_sync=True
    def tick(self,p):
        self.h.now+=.001;self.s.ingest(p)
    def begin(self):
        self.result=[]
        self.thread=threading.Thread(target=lambda:self.result.append(self.s.request_arm()))
        self.thread.start();self.assertTrue(self.u.entered.wait(.2));time.sleep(.01)
    def test_stop_ack_and_post_write_zero_required_before_arm(self):
        self.begin()
        self.assertEqual(self.u.writes,[b'\nSTOP\n'])
        self.tick(self.h.d0());self.assertNotIn(b'ARM\n',self.u.writes)
        self.tick({'ack':'STOP','state':'DISARMED'});self.tick(self.h.d0())
        end=time.monotonic()+.2
        while b'ARM\n' not in self.u.writes and time.monotonic()<end:time.sleep(.001)
        self.tick({'ack':'ARM','state':'ARMED'});self.tick(self.h.d0(safety='ARMED'))
        self.thread.join(1);self.assertEqual(self.result,[(True,'ARM_CONFIRMED')])
    def test_missing_stop_ack_never_sends_arm(self):
        self.begin();self.tick(self.h.d0());self.thread.join(1)
        self.assertNotIn(b'ARM\n',self.u.writes)
        self.assertEqual(self.result,[(False,'TRANSPORT_SYNC_TIMEOUT')])
    def test_cached_stop_ack_cannot_authorize_new_sync(self):
        self.tick({'ack':'STOP','state':'DISARMED'})
        self.begin();self.tick(self.h.d0());self.thread.join(1)
        self.assertNotIn(b'ARM\n',self.u.writes)
    def test_user_stop_cancels_pending_sync(self):
        self.begin();self.s.request_stop('USER_STOP',wait=False)
        self.tick({'ack':'STOP','state':'DISARMED'});self.tick(self.h.d0());self.thread.join(1)
        self.assertNotIn(b'ARM\n',self.u.writes)

if __name__=='__main__':unittest.main()
