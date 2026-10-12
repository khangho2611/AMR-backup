"""Single-owner command state for the web/ROS node. No port is opened here.

The firmware has no transaction IDs: a timed-out PID transaction blocks further
tuning until reconnect, so a late ACK cannot apply to a different request.
"""
import csv
import io
import json
import math
import threading
import time
import copy
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

from agv_preflight_static_collector import EXACT_BOOT_BANNER, EXACT_I2C_SCAN_BANNER
from agv_navigation import finite

NUMERIC = ('l_tgt','r_tgt','l_rpm','r_rpm','l_pwm','r_pwm','x','y','th','v','w')
ZERO = ('l_tgt','r_tgt','l_rpm','r_rpm','l_pwm','r_pwm','v','w')


class CommandSession:
    def __init__(self, serial_stream, clock=time.perf_counter, motion_window_s=None):
        if motion_window_s is not None and (not finite(motion_window_s) or not 0 < motion_window_s <= 15):
            raise ValueError('Motion window must be finite and at most 15 seconds')
        self.ser, self.clock = serial_stream, clock
        self.motion_window_s = motion_window_s
        self.trial_deadline = None
        self.trial_armed_once = False
        self.lock, self.writer, self.pid_lock = threading.RLock(), threading.Lock(), threading.Lock()
        self.opened = clock()
        self.stage = 0
        self.diag_time = None
        self.stable_start = None
        self.stable_count = 0
        self.last_d0 = None
        self.latest = None
        self.scan_time = None
        self.scan_clear = False
        self.rotation_clear = False
        # Bound by the ROS node to fresh map/TF/scan geometry. Front clearance
        # alone cannot authorize an arc whose body sweeps sideways.
        self.arc_validator = None
        self.escape_validator = None
        self.latched = True
        self.fault = None
        self.generation = 0
        self.arm_sent = None
        self.arm_ack = False
        self.armed = False
        self.last_command = None
        self.motion = False
        self.stop_op = 0
        self.stop_complete = None
        self.stop_write_ok = False
        self.stop_confirmed = False
        self.stop_observed_zero = False
        self.stop_deadline = None
        self.arm_event, self.stop_event, self.pid_event = (threading.Event() for _ in range(3))
        self.pid_pending = None
        self.pid_uncertain = False
        self.history = []
        self.tuning_sequence = 0
        self.settling_lines = 0
        # In-memory only: UART/watchdog paths never wait on disk or network IO.
        self.events = deque(maxlen=256)
        self.command_events = deque(maxlen=512)
        self.event_sequence = 0
        self.first_fault = None
        self.first_fault_events = None

    def _event(self, kind, **details):
        with self.lock:
            self.event_sequence += 1
            event = dict(sequence=self.event_sequence, mono=self.clock(), kind=kind,
                         generation=self.generation, stop_op=self.stop_op, **details)
            self.events.append(event)
            if kind != 'rx_d0':self.command_events.append(event)
            return event

    def _ages(self, now):
        return {name: None if stamp is None else now-stamp for name,stamp in (
            ('d0_age_s',self.last_d0),('scan_age_s',self.scan_time),
            ('caller_age_s',self.last_command))}

    def diagnostics(self):
        with self.lock:
            return copy.deepcopy(dict(event_capacity=self.events.maxlen,
                events=list(self.events), command_event_capacity=self.command_events.maxlen,
                command_events=list(self.command_events), first_fault=self.first_fault,
                first_fault_events=self.first_fault_events or []))

    def _drive_result(self, command, accepted, reason, blockers=()):
        with self.lock:
            self._event('drive', command=command[:96], accepted=accepted,
                        reason=reason, blockers=list(blockers), **self._ages(self.clock()))
        return accepted,reason

    def ingest_line(self, raw):
        try:
            packet = json.loads(raw.decode('utf8',errors='strict'))
        except (ValueError,UnicodeError):
            with self.lock:
                self.settling_lines += 1
                settling = self.stage == 0 and self.clock()-self.opened <= 2. and self.settling_lines <= 15
            if not settling:
                self.request_stop('MALFORMED_SERIAL_LINE',wait=False)
            return None
        self.ingest(packet)
        return packet

    def _fault(self, reason):
        if self.fault is None:
            self.fault = reason
            self.first_fault = dict(reason=reason, mono=self.clock(),
                                    latest_d0=copy.deepcopy(self.latest),
                                    **self._ages(self.clock()))
            self._event('fault', reason=reason)
            self.first_fault_events = copy.deepcopy(list(self.events))
        self.latched = True
        self.armed = False
        self.motion = False

    def _write(self, payload):
        started = self.clock()
        n, error = None, None
        try:
            if self.ser is not None and self.ser.is_open:
                n = self.ser.write(payload)
            else:
                error = 'NO_OPEN_TRANSPORT'
        except Exception as exc:
            error = type(exc).__name__
        ok = type(n) is int and n == len(payload)
        self._event('tx', command=payload[:96].decode('ascii',errors='replace').strip(),
                    started_mono=started, duration_s=self.clock()-started,
                    requested_bytes=len(payload), written_bytes=n if type(n) is int else None,
                    full_write=ok, error=error)
        return ok

    def ingest(self, packet):
        if not isinstance(packet, dict):
            return
        must_stop = None
        with self.lock:
            now = self.clock()
            if self.stage < 3 and now-self.opened > 3.5:
                self._fault('STARTUP_DEADLINE'); must_stop = self.fault
            elif 'error' in packet:
                if packet['error'] == 'INVALID_TUNING_RANGE' and self.pid_pending is not None and self.pid_pending.get('write_complete') is not None and now > self.pid_pending['write_complete']:
                    self.pid_pending.update(status='REJECTED', reason=packet['error'])
                    self.pid_event.set()
                else:
                    self._fault(str(packet['error']))
                    must_stop = self.fault
            elif 'ack' in packet:
                ack = packet['ack']
                self._event('rx_ack', ack=str(ack)[:160])
                if ack == 'ARM' and packet.get('state') == 'ARMED' and self.arm_sent is not None and now > self.arm_sent:
                    self.arm_ack = True
                elif isinstance(ack, str) and ack.startswith('TUNING ') and self.pid_pending is not None:
                    if (ack == self.pid_pending['cmd'] and self.pid_pending.get('write_complete') is not None and now > self.pid_pending['write_complete']):
                        self.pid_pending.update(status='APPLIED', reason='MCU_ACK_MATCHED')
                        self.pid_event.set()
            elif packet == {'info': EXACT_BOOT_BANNER}:
                if self.stage != 0 or now-self.opened > 3.5:
                    self._fault('UNEXPECTED_OR_LATE_BOOT'); must_stop = self.fault
                else:
                    self.stage = 1
            elif packet == {'info': EXACT_I2C_SCAN_BANNER} and self.stage == 1:
                self.stage = 2
            elif 'i2c_found' in packet and self.stage == 2:
                try:
                    addr = int(packet['i2c_found'],16)
                    if len(packet) != 1 or not 1 <= addr <= 127:
                        raise ValueError()
                    self.stage, self.diag_time = 3, now
                except (ValueError, TypeError):
                    self._fault('INVALID_I2C_DIAGNOSTIC'); must_stop = self.fault
            elif 'vin_mv' in packet:
                if (self.stage != 3 or len(packet) != 1 or type(packet['vin_mv']) is not int or
                        not 0 < packet['vin_mv'] <= 0xffffffff or self.stable_count):
                    self._fault('INVALID_OR_LATE_VIN'); must_stop = self.fault
            elif set(packet) == set(NUMERIC) | {'safety','mode'} and all(finite(packet[k]) for k in NUMERIC):
                if (packet['safety'] not in ('DISARMED','ARMED','FAULT') or
                        packet['mode'] not in ('PID','MAN') or
                        any(type(packet[k]) is not int or abs(packet[k]) > 255 for k in ('l_pwm','r_pwm'))):
                    self._fault('INVALID_D0'); must_stop = self.fault
                else:
                    clean = packet['safety'] == 'DISARMED' and all(packet[k] == 0 for k in ZERO)
                    gap = None if self.last_d0 is None else now-self.last_d0
                    self._event('rx_d0', gap_s=gap, packet=dict(packet))
                    self.latest, self.last_d0 = dict(packet), now
                    if self.stage == 3 and clean and not self.fault:
                        if self.stable_start is None or gap is None or gap > .25:
                            self.stable_start, self.stable_count = now, 0
                        self.stable_count += 1
                    else:
                        self.stable_start, self.stable_count = None, 0
                        if self.stage == 3 and not clean and not self.armed and self.arm_sent is None:
                            self._fault('UNSAFE_PREFLIGHT_D0'); must_stop = self.fault
                    if packet['safety'] == 'FAULT':
                        self._fault('MCU_FAULT'); must_stop = self.fault
                    if (self.motion_window_s is not None and self.armed and
                            max(abs(packet['l_rpm']),abs(packet['r_rpm'])) > 35.):
                        self._fault('TRIAL_OVERSPEED'); must_stop = self.fault
                    if (not self.armed and self.arm_sent is not None and self.arm_ack and now > self.arm_sent and
                            packet['safety'] == 'ARMED' and not self.fault):
                        self.armed, self.latched = True, False
                        self.last_command = now
                        if self.motion_window_s is not None and self.trial_deadline is None:
                            self.trial_deadline = now+self.motion_window_s
                        self.arm_event.set()
                    elif self.armed and packet['safety'] != 'ARMED':
                        self._fault('MCU_DISARMED_DURING_SESSION'); must_stop = self.fault
                    self.stop_observed_zero = clean
                    if clean and self.stop_write_ok and self.stop_complete is not None and now > self.stop_complete:
                        if not self.stop_confirmed:
                            self._event('stop_confirmed', after_tx_s=now-self.stop_complete)
                        self.stop_confirmed = True
                        self.stop_event.set()
            else:
                if self.stage == 3 or self.armed:
                    self._fault('UNCLASSIFIED_PACKET'); must_stop = self.fault
        if must_stop:
            self.request_stop(must_stop, wait=False)

    def preflight_ready(self, now):
        return (self.stage == 3 and not self.fault and self.stable_start is not None and
                self.stable_count >= 80 and self.last_d0 is not None and
                0 <= now-self.last_d0 <= .25 and self.last_d0-self.stable_start >= 10. and
                self.latest['safety'] == 'DISARMED' and all(self.latest[k] == 0 for k in ZERO))

    def request_arm(self):
        if not self.writer.acquire(timeout=.2):
            return False, 'WRITER_BUSY'
        try:
            with self.lock:
                now = self.clock()
                if self.motion_window_s is not None and self.trial_armed_once:
                    return False, 'TRIAL_ALREADY_USED'
                if not self.preflight_ready(now) or self.arm_sent is not None or self.pid_pending is not None:
                    return False, 'PREFLIGHT_NOT_READY'
                self.arm_event.clear()
                self.arm_ack = False
                self.arm_sent = now
                self.generation += 1
                generation = self.generation
            with self.lock:
                wrote = self._write(b'ARM\n')
                if generation != self.generation:
                    self.arm_sent = None
                    return False, 'ARM_CANCELLED_BY_STOP'
                if not wrote:
                    self._fault('ARM_WRITE_FAILED')
                    return False, self.fault
                self.arm_sent = self.clock()
                if self.motion_window_s is not None: self.trial_armed_once = True
        finally:
            self.writer.release()
        if not self.arm_event.wait(.4):
            self.request_stop('ARM_ACK_TIMEOUT', wait=False)
            return False, 'ARM_ACK_TIMEOUT'
        with self.lock:
            return (self.armed and not self.latched), 'ARM_CONFIRMED'

    def drive(self, command, autonomous=False, escape=False):
        parts = command.split()
        if len(parts) != 3 or parts[0] not in ('M','V'):
            return self._drive_result(command, False, 'INVALID_DRIVE')
        try:
            values = [float(p) for p in parts[1:]]
        except ValueError:
            return self._drive_result(command, False, 'INVALID_DRIVE')
        if not all(math.isfinite(v) for v in values):
            return self._drive_result(command, False, 'INVALID_DRIVE')
        if escape and (not autonomous or parts[0]!='V' or abs(values[0])>.04 or values[0]==0):
            return self._drive_result(command,False,'INVALID_ESCAPE_CALLER_OR_COMMAND')
        if self.motion_window_s is not None and (parts[0]=='M' or abs(values[0])>.04):
            return self._drive_result(command, False, 'TRIAL_V_ONLY_MAX_0.04')
        if (parts[0] == 'M' and (autonomous or any(abs(v)>140 or v != int(v) for v in values)) or
                parts[0] == 'V' and (abs(values[0]) > .08 or abs(values[1]) > .35)):
            return self._drive_result(command, False, 'DRIVE_LIMIT')
        with self.lock:
            generation = self.generation
        if not self.writer.acquire(timeout=.1):
            self.request_stop('WRITER_BUSY',wait=False)
            return self._drive_result(command, False, 'WRITER_BUSY')
        try:
            is_arc = parts[0] == 'V' and values[0] > 0 and values[1] != 0
            arc_ok = False
            escape_ok = False
            if escape:
                try:
                    escape_ok = self.escape_validator is not None and self.escape_validator(*values) is True
                except Exception as exc:
                    self._event('escape_validation_error',error=type(exc).__name__)
            elif is_arc:
                # No state lock across geometry/TF work: STOP must be able to
                # cancel this generation while it waits for the sole writer.
                try:
                    arc_ok = self.arc_validator is not None and self.arc_validator(*values) is True
                except Exception as exc:
                    self._event('arc_validation_error',error=type(exc).__name__)
            with self.lock:
                now = self.clock()
                if parts[0] == 'V':
                    needs_forward = values[0] > 0
                    needs_sweep = values[0] <= 0 and (values[0] < 0 or values[1] != 0)
                else:
                    needs_forward = values[0] > 0 and values[1] > 0
                    needs_sweep = (not needs_forward or values[0] != values[1]) and any(v != 0 for v in values)
                checks = (
                    ('LATCHED',self.latched), ('NOT_ARMED',not self.armed),
                    ('FAULT',bool(self.fault)), ('CANCELLED_GENERATION',generation != self.generation),
                    ('TRIAL_EXPIRED',self.trial_deadline is not None and now >= self.trial_deadline),
                    ('D0_STALE',self.last_d0 is None or not 0 <= now-self.last_d0 <= .25),
                    ('SCAN_STALE',self.scan_time is None or not 0 <= now-self.scan_time <= .25),
                    ('FORWARD_NOT_CLEAR',not escape and needs_forward and not self.scan_clear),
                    ('ARC_NOT_VALIDATED',not escape and is_arc and not arc_ok),
                    ('SWEEP_NOT_CLEAR',not escape and needs_sweep and not self.rotation_clear),
                    ('ESCAPE_NOT_VALIDATED',escape and not escape_ok))
                blockers = [name for name,blocked in checks if blocked]
                if blockers:
                    return self._drive_result(command,False,'SESSION_OR_SENSOR_NOT_READY',blockers)
            # The state mutex must remain available to STOP while a physical
            # write is in flight; STOP owns the next write, queued drives expire.
            wrote = self._write((command+'\n').encode('ascii'))
            with self.lock:
                if not wrote:
                    self._fault('DRIVE_WRITE_FAILED')
                    failed = True
                else:
                    if generation != self.generation or self.latched:
                        return self._drive_result(command, False, 'CANCELLED_BY_STOP')
                    self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                    failed = False
        finally:
            self.writer.release()
        if failed:
            self.request_stop('DRIVE_WRITE_FAILED',wait=False)
            return self._drive_result(command, False, 'DRIVE_WRITE_FAILED')
        return self._drive_result(command, True, 'SENT')

    def request_stop(self, reason='USER_STOP', wait=True):
        # Invalidate queued drives BEFORE waiting for the writer. No auto reARM.
        with self.lock:
            self._event('stop_requested', reason=reason, **self._ages(self.clock()))
            self.latched, self.armed, self.motion = True, False, False
            self.stable_start, self.stable_count = None, 0
            self.generation += 1
            self.stop_op += 1
            op = self.stop_op
            self.stop_complete, self.stop_write_ok, self.stop_confirmed = None, False, False
            self.stop_observed_zero = False
            self.stop_event.clear()
            self.stop_deadline = self.clock()+.25
            if reason != 'USER_STOP' and reason != 'HOME_STOP':
                self._fault(reason)
            self.arm_sent = None
        if not self.writer.acquire(timeout=.2):
            with self.lock: self._fault('STOP_WRITER_TIMEOUT')
            return False, 'STOP_WRITER_TIMEOUT'
        try:
            with self.lock:
                if self.stop_op != op:
                    return False, 'STOP_SUPERSEDED'
            ok = self._write(b'STOP\n')
            with self.lock:
                if self.stop_op == op:
                    self.stop_write_ok = ok
                    self.stop_complete = self.clock() if ok else None
                    if not ok: self._fault('STOP_WRITE_FAILED')
        finally:
            self.writer.release()
        if not ok:
            return False, 'STOP_WRITE_FAILED'
        if not wait:
            return False, 'STOP_PENDING'
        self.stop_event.wait(.25)
        with self.lock:
            confirmed = op == self.stop_op and self.stop_confirmed
            if not confirmed: self._fault('STOP_UNCONFIRMED')
            return confirmed, 'STOP_CONFIRMED' if confirmed else 'STOP_UNCONFIRMED'

    def watchdog_tick(self):
        with self.lock:
            now = self.clock()
            reason = None
            if self.stage < 3 and not self.fault and now-self.opened > 3.5:
                reason = 'STARTUP_DEADLINE'
            if self.armed:
                if self.trial_deadline is not None and now >= self.trial_deadline:
                    reason = 'TRIAL_WINDOW_COMPLETE'
                elif self.last_d0 is None or not 0 <= now-self.last_d0 <= .25:
                    reason = 'TELEMETRY_TIMEOUT'
                elif self.scan_time is None or not 0 <= now-self.scan_time <= .25:
                    reason = 'SCAN_TIMEOUT'
                elif self.last_command is None or not 0 <= now-self.last_command <= .2:
                    reason = 'CALLER_TIMEOUT'
            if self.stop_deadline is not None and now > self.stop_deadline and not self.stop_confirmed:
                self._fault('STOP_UNCONFIRMED')
        if reason:
            self.request_stop(reason,wait=False)

    def tuning(self, kp,ki,kd):
        if self.motion_window_s is not None:
            return {'status':'REJECTED','reason':'TRIAL_TUNING_DISABLED'}
        vals = (kp,ki,kd)
        if not all(finite(v) and 0 <= v <= limit for v,limit in zip(vals,(20,50,5))):
            return {'status':'REJECTED','reason':'INVALID_TUNING_RANGE'}
        if not self.pid_lock.acquire(blocking=False):
            return {'status':'REJECTED','reason':'TUNING_BUSY'}
        try:
            with self.lock:
                self.tuning_sequence += 1
                record = {'id':self.tuning_sequence,'time':datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(),
                          'kp':kp,'ki':ki,'kd':kd,'kf':.45,'status':'PENDING','reason':'',
                          'cmd':f'TUNING {kp:.3f} {ki:.3f} {kd:.4f} 0.450'}
                self.history.append(record)
                if len(self.history)>500: self.history.pop(0)
                if self.pid_uncertain or self.armed or self.motion:
                    record.update(status='FAILED',reason='RECONNECT_REQUIRED' if self.pid_uncertain else 'STOP_BEFORE_TUNING')
                    return dict(record)
                self.pid_event.clear()
                self.pid_pending = record
                record['write_complete'] = None
            if not self.writer.acquire(timeout=.2):
                record.update(status='FAILED',reason='WRITER_BUSY')
            else:
                try:
                    # Tuning is DISARMED-only. Commit its bounded full-write
                    # result before a fast reader can classify the matching ACK.
                    with self.lock:
                        if self.armed or self.motion:
                            record.update(status='FAILED',reason='STOP_BEFORE_TUNING')
                        elif not self._write((record['cmd']+'\n').encode('ascii')):
                            record.update(status='FAILED',reason='WRITE_FAILED')
                            self.pid_uncertain = True
                        else:
                            record['write_complete'] = self.clock()
                finally:
                    self.writer.release()
            if record['status']=='PENDING' and not self.pid_event.wait(.5):
                with self.lock:
                    if record['status']=='PENDING':
                        record.update(status='FAILED',reason='MCU_ACK_TIMEOUT')
                        self.pid_uncertain=True
            with self.lock:
                self.pid_pending=None
                return dict(record)
        finally:
            self.pid_lock.release()

    def history_csv(self):
        out = io.StringIO(newline='')
        writer = csv.writer(out)
        fields = ('id','time','kp','ki','kd','kf','status','reason')
        writer.writerow(fields)
        with self.lock:
            for row in self.history: writer.writerow([row[k] for k in fields])
        return out.getvalue()

    def health(self):
        with self.lock:
            return {'latched':self.latched,'armed':self.armed,'fault':self.fault,
                    'motion_window_s':self.motion_window_s,
                    'trial_used':self.trial_armed_once,
                    'trial_remaining_s':None if self.trial_deadline is None else max(0.,self.trial_deadline-self.clock()),
                    'd0_age_s': None if self.last_d0 is None else self.clock()-self.last_d0,
                    'latest_d0':dict(self.latest) if self.latest is not None else None,
                    'startup_stage':self.stage,'preflight_count':self.stable_count,
                    'preflight_ready':self.preflight_ready(self.clock()),
                    'stop_op':self.stop_op,'stop_confirmed':self.stop_confirmed,
                    'stop_write_ok':self.stop_write_ok,'zero_observed':self.stop_observed_zero,
                    'escalation':'CUT_POWER_IF_MOVING' if self.fault and not self.stop_confirmed else None}
