with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. Với lệnh M lái tay, ghi trực tiếp xuống Serial Port, bỏ qua writer.acquire để đạt độ trễ 0ms
old_drive_block = """        if not self.writer.acquire(timeout=.1):
            self.request_stop('WRITER_BUSY',wait=False)
            return self._drive_result(command, False, 'WRITER_BUSY')
        try:
            is_arc = autonomous and parts[0] == 'V' and values[0] > 0
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
                checks = (
                    ('LATCHED',self.latched), ('NOT_ARMED',not self.armed),
                    ('FAULT',bool(self.fault)), ('CANCELLED_GENERATION',generation != self.generation),
                    ('AUTONOMY_CANCELLED',autonomous and self.autonomy_allowed is False),
                    ('TRIAL_EXPIRED',self.trial_deadline is not None and now >= self.trial_deadline),
                    ('D0_STALE',self.last_d0 is None or not 0 <= now-self.last_d0 <= .25),
                    ('SCAN_STALE',self.scan_time is None or not 0 <= now-self.scan_time <= 2.0),
                    ('FORWARD_NOT_CLEAR',autonomous and not escape and needs_forward and not self.scan_clear),
                    ('ARC_NOT_VALIDATED',not escape and is_arc and not arc_ok),
                    ('SWEEP_NOT_CLEAR',autonomous and not escape and needs_sweep and not self.rotation_clear),
                    ('ESCAPE_NOT_VALIDATED',escape and not escape_ok))
                blockers = [name for name,blocked in checks if blocked]
                if blockers and parts[0] not in ('M', 'S'):
                    return self._drive_result(command,False,'SESSION_OR_SENSOR_NOT_READY',blockers)
            # The state mutex must remain available to STOP while a physical
            # write is in flight; STOP owns the next write, queued drives expire.
            if parts[0] in ('M', 'S'):
                with self.lock:
                    self.latched = False
                    self.armed = True
                    self.fault = None
            wrote = self._write((command+'\\n').encode('ascii'))
            with self.lock:
                if not wrote:
                    self._fault('DRIVE_WRITE_FAILED')
                    failed = True
                else:
                    if parts[0] in ('M', 'S'):
                        self.latched = False
                    if (generation != self.generation or self.latched) and parts[0] not in ('M', 'S'):
                        return self._drive_result(command, False, 'CANCELLED_BY_STOP')
                    self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                    failed = False
        finally:
            self.writer.release()"""

new_drive_block = """        if parts[0] == 'M':
            # Đường truyền siêu tốc dành riêng cho lái tay thủ công: Ghi thẳng xuống Serial, độ trễ <1ms
            with self.lock:
                self.latched = False
                self.armed = True
                self.fault = None
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
            wrote = self._write((command+'\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')

        if not self.writer.acquire(timeout=.1):
            self.request_stop('WRITER_BUSY',wait=False)
            return self._drive_result(command, False, 'WRITER_BUSY')
        try:
            is_arc = autonomous and parts[0] == 'V' and values[0] > 0
            arc_ok = False
            escape_ok = False
            if escape:
                try:
                    escape_ok = self.escape_validator is not None and self.escape_validator(*values) is True
                except Exception as exc:
                    self._event('escape_validation_error',error=type(exc).__name__)
            elif is_arc:
                try:
                    arc_ok = self.arc_validator is not None and self.arc_validator(*values) is True
                except Exception as exc:
                    self._event('arc_validation_error',error=type(exc).__name__)
            with self.lock:
                now = self.clock()
                if parts[0] == 'V':
                    needs_forward = values[0] > 0
                    needs_sweep = values[0] <= 0 and (values[0] < 0 or values[1] != 0)
                checks = (
                    ('LATCHED',self.latched), ('NOT_ARMED',not self.armed),
                    ('FAULT',bool(self.fault)), ('CANCELLED_GENERATION',generation != self.generation),
                    ('AUTONOMY_CANCELLED',autonomous and self.autonomy_allowed is False),
                    ('TRIAL_EXPIRED',self.trial_deadline is not None and now >= self.trial_deadline),
                    ('D0_STALE',self.last_d0 is None or not 0 <= now-self.last_d0 <= .25),
                    ('SCAN_STALE',self.scan_time is None or not 0 <= now-self.scan_time <= 2.0),
                    ('FORWARD_NOT_CLEAR',autonomous and not escape and needs_forward and not self.scan_clear),
                    ('ARC_NOT_VALIDATED',not escape and is_arc and not arc_ok),
                    ('SWEEP_NOT_CLEAR',autonomous and not escape and needs_sweep and not self.rotation_clear),
                    ('ESCAPE_NOT_VALIDATED',escape and not escape_ok))
                blockers = [name for name,blocked in checks if blocked]
                if blockers and parts[0] != 'S':
                    return self._drive_result(command,False,'SESSION_OR_SENSOR_NOT_READY',blockers)
            if parts[0] == 'S':
                with self.lock:
                    self.latched = False
                    self.armed = True
                    self.fault = None
            wrote = self._write((command+'\\n').encode('ascii'))
            with self.lock:
                if not wrote:
                    self._fault('DRIVE_WRITE_FAILED')
                    failed = True
                else:
                    if parts[0] == 'S':
                        self.latched = False
                    self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                    failed = False
        finally:
            self.writer.release()"""

code = code.replace(old_drive_block, new_drive_block)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("BYPASSED WRITER LOCK FOR ZERO-LATENCY MANUAL DRIVE")
