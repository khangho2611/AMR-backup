with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Đổi timeout=.05 thành timeout=0 (Non-blocking) để serial.read không bao giờ block luồng
code = code.replace("self.ser = serial.Serial(port=None, baudrate=BAUDRATE, timeout=.05,",
                    "self.ser = serial.Serial(port=None, baudrate=BAUDRATE, timeout=0,")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SWITCHED SERIAL TO NON-BLOCKING FOR ZERO LATENCY")
