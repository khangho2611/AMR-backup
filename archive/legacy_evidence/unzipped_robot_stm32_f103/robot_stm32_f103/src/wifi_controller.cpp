#include "wifi_controller.h"
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Arduino.h>
#include "encoder.h"
#include "pid.h"
#include "robot_motor.h"
#include "mke_m18.h"
#include "mpu6050.h"

#define MODE_PID 1
#define MODE_OPEN_LOOP 0

extern void Execute_Robot_Command(const char *cmd);
extern Encoder_t g_enc_left;
extern Encoder_t g_enc_right;
extern float g_target_rpm_left;
extern float g_target_rpm_right;
extern int16_t g_speed_left;
extern int16_t g_speed_right;
extern uint8_t g_control_mode;

static const char* AP_SSID = "esp32";
static const char* AP_PASS = "12312312";

static WebServer server(80);
static DNSServer dnsServer;

static const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>ESP32 Robot Controller + IMU MPU6050</title>
  <style>
    * {
      box-sizing: border-box;
      -webkit-tap-highlight-color: transparent;
      -webkit-touch-callout: none;
      -webkit-user-select: none;
      user-select: none;
    }
    body {
      margin: 0; padding: 10px; background: #0b1120; color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh; display: flex; flex-direction: column; justify-content: space-between;
      touch-action: pan-y;
    }
    .header {
      display: flex; align-items: center; justify-content: space-between;
      padding-bottom: 6px; border-bottom: 1px solid #1e293b;
    }
    .title { font-size: 15px; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 6px; }
    .badge {
      font-size: 10px; padding: 3px 8px; border-radius: 999px;
      background: #064e3b; color: #34d399; font-weight: 700;
    }

    .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 8px 0; }
    .card { background: #131d31; border: 1px solid #1e293b; border-radius: 10px; padding: 6px 8px; text-align: center; }
    .card-title { font-size: 10px; color: #94a3b8; font-weight: 700; text-transform: uppercase; margin-bottom: 2px; }
    .card-val { font-size: 18px; font-weight: 900; color: #38bdf8; }
    .card-sub { font-size: 9px; color: #64748b; margin-top: 1px; }

    /* KHỐI IMU MPU6050 */
    .imu-grid {
      display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 8px;
    }
    .imu-card {
      background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 6px 4px; text-align: center;
    }
    .imu-title { font-size: 9px; color: #38bdf8; font-weight: 700; text-transform: uppercase; }
    .imu-val { font-size: 15px; font-weight: 900; color: #facc15; }

    .speed-section { background: #131d31; border: 1px solid #1e293b; border-radius: 10px; padding: 8px; margin-bottom: 8px; }
    .speed-header { display: flex; justify-content: space-between; font-size: 11px; color: #cbd5e1; font-weight: 700; margin-bottom: 4px; }
    input[type=range] { width: 100%; height: 6px; accent-color: #38bdf8; }
    .presets { display: flex; gap: 4px; margin-top: 6px; }
    .preset-btn {
      flex: 1; padding: 5px; font-size: 10px; font-weight: 700;
      background: #1e293b; border: 1px solid #334155; color: #f8fafc; border-radius: 6px;
    }
    .preset-btn.active { background: #0284c7; border-color: #38bdf8; }

    /* CỤM PHÍM ĐIỀU KHIỂN CHUẨN WASD: CHẠM GIỮ LÀ CHẠY, BUÔNG LÀ DỪNG */
    .dpad {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
      max-width: 320px; width: 100%; margin: 0 auto;
    }
    .btn {
      height: 62px; border-radius: 16px; border: 2px solid #334155; background: #1e293b;
      color: #f8fafc; font-size: 20px; font-weight: 900; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      touch-action: none;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.4);
      transition: background 0.05s, transform 0.05s;
    }
    .btn.pressed {
      background: #0284c7 !important; border-color: #38bdf8 !important;
      transform: scale(0.94); box-shadow: 0 0 15px rgba(56,189,248,0.7);
    }
    .btn-stop { background: #881337; border-color: #be123c; color: #fda4af; }
    .btn-stop.pressed { background: #e11d48 !important; }
    .btn-sub { font-size: 9px; font-weight: 700; opacity: 0.85; margin-top: 1px; }
    .footer { text-align: center; font-size: 9px; color: #64748b; margin-top: 6px; }
  </style>
</head>
<body>

  <div>
    <div class="header">
      <div class="title">🤖 ROBOT ESP32 + MPU6050</div>
      <button onclick="resetYaw()" style="font-size:10px; font-weight:700; padding:3px 8px; border-radius:6px; background:#1e293b; color:#38bdf8; border:1px solid #334155;">Reset Góc</button>
    </div>

    <!-- KHỐI GÓC TƯ THẾ IMU MPU-6050 -->
    <div class="imu-grid" style="margin-top:8px;">
      <div class="imu-card">
        <div class="imu-title">Góc Lái (Yaw)</div>
        <div class="imu-val" id="imuYaw">0.0°</div>
      </div>
      <div class="imu-card">
        <div class="imu-title">Nghiêng (Pitch)</div>
        <div class="imu-val" id="imuPitch">0.0°</div>
      </div>
      <div class="imu-card">
        <div class="imu-title">Xoay Gyro Z</div>
        <div class="imu-val" id="imuGz">0.0°/s</div>
      </div>
    </div>

    <!-- THÔNG SỐ VẬN TỐC THỜI GIAN THỰC -->
    <div class="stats-grid">
      <div class="card">
        <div class="card-title">Bánh Trái</div>
        <div class="card-val" id="lRpm">0.0</div>
        <div class="card-sub">PWM: <span id="lPwm">0</span> | Xung: <span id="lCnt">0</span></div>
      </div>
      <div class="card">
        <div class="card-title">Bánh Phải</div>
        <div class="card-val" id="rRpm">0.0</div>
        <div class="card-sub">PWM: <span id="rPwm">0</span> | Xung: <span id="rCnt">0</span></div>
      </div>
    </div>

    <!-- THANH TRƯỢT TỐC ĐỘ TARGET -->
    <div class="speed-section">
      <div class="speed-header">
        <span>Tốc Độ Mục Tiêu</span>
        <span id="speedVal" style="color:#38bdf8;">180 RPM</span>
      </div>
      <input type="range" id="speedSlider" min="60" max="280" value="180" step="10" oninput="setSpeed(this.value)">
      <div class="presets">
        <button class="preset-btn" onclick="setSpeed(80)">80</button>
        <button class="preset-btn" onclick="setSpeed(150)">150</button>
        <button class="preset-btn active" id="p180" onclick="setSpeed(180)">180</button>
        <button class="preset-btn" onclick="setSpeed(220)">220</button>
        <button class="preset-btn" onclick="setSpeed(280)">280</button>
      </div>
    </div>
  </div>

  <!-- NÚT ĐIỀU KHIỂN CẢM ỨNG WASD (NHẤN LÀ CHẠY, BUÔNG LÀ DỪNG) -->
  <div class="dpad">
    <button class="btn" id="btnQ"><span>↺</span><span class="btn-sub">[Q] QUAY T</span></button>
    <button class="btn" id="btnW"><span>▲</span><span class="btn-sub">[W] TIẾN</span></button>
    <button class="btn" id="btnE"><span>↻</span><span class="btn-sub">[E] QUAY P</span></button>

    <button class="btn" id="btnA"><span>◄</span><span class="btn-sub">[A] TRÁI</span></button>
    <button class="btn btn-stop" id="btnStop"><span>■</span><span class="btn-sub">DỪNG</span></button>
    <button class="btn" id="btnD"><span>►</span><span class="btn-sub">[D] PHẢI</span></button>

    <div></div>
    <button class="btn" id="btnS"><span>▼</span><span class="btn-sub">[S] LÙI</span></button>
    <div></div>
  </div>

  <div class="footer">Giữ nút để chạy • Thả tay để dừng • MPU6050 (Wire1: 16/17)</div>

  <script>
    let curSpeed = 180;
    let isMoving = false;
    let currentCmdFunc = null;
    let heartbeatTimer = null;

    function setSpeed(v) {
      curSpeed = parseInt(v);
      document.getElementById('speedVal').innerText = curSpeed + " RPM";
      document.getElementById('speedSlider').value = curSpeed;
      document.querySelectorAll('.preset-btn').forEach(b => {
        b.classList.toggle('active', b.innerText == curSpeed);
      });
      if (isMoving && currentCmdFunc) {
        startMotion(currentCmdFunc);
      }
    }

    function sendHttp(cmd) {
      fetch('/cmd?val=' + encodeURIComponent(cmd)).catch(()=>{});
    }

    function resetYaw() {
      sendHttp('RESET_YAW');
    }

    function startMotion(cmdFunc) {
      isMoving = true;
      currentCmdFunc = cmdFunc;
      sendHttp(cmdFunc());

      if (heartbeatTimer) clearInterval(heartbeatTimer);
      heartbeatTimer = setInterval(() => {
        if (isMoving && currentCmdFunc) {
          sendHttp(currentCmdFunc());
        }
      }, 150);
    }

    function stopMotion() {
      isMoving = false;
      currentCmdFunc = null;
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
      document.querySelectorAll('.btn').forEach(b => b.classList.remove('pressed'));
      sendHttp('STOP');
    }

    const motions = {
      'btnW': () => `S ${curSpeed} ${curSpeed}`,
      'btnS': () => `S -${curSpeed} -${curSpeed}`,
      'btnA': () => `S 0 ${curSpeed}`,
      'btnD': () => `S ${curSpeed} 0`,
      'btnQ': () => `S -${curSpeed} ${curSpeed}`,
      'btnE': () => `S ${curSpeed} -${curSpeed}`
    };

    function bindButton(id, cmdFunc) {
      const el = document.getElementById(id);
      if (!el) return;

      el.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        try { el.setPointerCapture(e.pointerId); } catch(err){}
        el.classList.add('pressed');
        startMotion(cmdFunc);
      });

      const releaseHandler = (e) => {
        e.preventDefault();
        try { el.releasePointerCapture(e.pointerId); } catch(err){}
        el.classList.remove('pressed');
        stopMotion();
      };

      el.addEventListener('pointerup', releaseHandler);
      el.addEventListener('pointercancel', releaseHandler);
    }

    Object.keys(motions).forEach(id => bindButton(id, motions[id]));

    document.getElementById('btnStop').addEventListener('click', (e) => {
      e.preventDefault();
      stopMotion();
    });

    const keyMap = {
      'KeyW': 'btnW', 'ArrowUp': 'btnW',
      'KeyS': 'btnS', 'ArrowDown': 'btnS',
      'KeyA': 'btnA', 'ArrowLeft': 'btnA',
      'KeyD': 'btnD', 'ArrowRight': 'btnD',
      'KeyQ': 'btnQ',
      'KeyE': 'btnE'
    };

    let activeKey = null;

    window.addEventListener('keydown', (e) => {
      if (e.repeat) return;
      const btnId = keyMap[e.code];
      if (btnId && motions[btnId]) {
        e.preventDefault();
        activeKey = e.code;
        document.getElementById(btnId).classList.add('pressed');
        startMotion(motions[btnId]);
      } else if (e.code === 'Space' || e.code === 'Escape') {
        e.preventDefault();
        stopMotion();
      }
    });

    window.addEventListener('keyup', (e) => {
      if (e.code === activeKey) {
        e.preventDefault();
        activeKey = null;
        stopMotion();
      }
    });

    // Cập nhật thông số telemetry & IMU mỗi 150ms
    setInterval(() => {
      fetch('/telemetry').then(r => r.json()).then(d => {
        document.getElementById('lRpm').innerText = Math.abs(d.l_rpm || 0).toFixed(1);
        document.getElementById('rRpm').innerText = Math.abs(d.r_rpm || 0).toFixed(1);
        document.getElementById('lPwm').innerText = d.l_pwm || 0;
        document.getElementById('rPwm').innerText = d.r_pwm || 0;
        document.getElementById('lCnt').innerText = d.l_cnt || 0;
        document.getElementById('rCnt').innerText = d.r_cnt || 0;

        if (d.yaw !== undefined) {
          document.getElementById('imuYaw').innerText = d.yaw.toFixed(1) + "°";
          document.getElementById('imuPitch').innerText = (d.pitch || 0).toFixed(1) + "°";
          document.getElementById('imuGz').innerText = (d.gz || 0).toFixed(1) + "°/s";
        }
      }).catch(()=>{});
    }, 150);
  </script>
</body>
</html>
)rawliteral";

static void handleRoot(void)
{
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "text/html", INDEX_HTML);
}

static void handleCmd(void)
{
    server.sendHeader("Access-Control-Allow-Origin", "*");
    if (server.hasArg("val"))
    {
        String val = server.arg("val");
        Execute_Robot_Command(val.c_str());
        server.send(200, "application/json", "{\"status\":\"ok\"}");
    }
    else
    {
        server.send(400, "text/plain", "Missing val");
    }
}

static void handleTelemetry(void)
{
    server.sendHeader("Access-Control-Allow-Origin", "*");
    char buf[220];
    snprintf(buf, sizeof(buf),
        "{\"mode\":\"%s\",\"l_tgt\":%.1f,\"r_tgt\":%.1f,\"l_rpm\":%.2f,\"r_rpm\":%.2f,\"l_pwm\":%d,\"r_pwm\":%d,\"l_cnt\":%ld,\"r_cnt\":%ld,\"yaw\":%.2f,\"pitch\":%.2f,\"roll\":%.2f,\"gz\":%.2f}",
        (g_control_mode == MODE_PID) ? "PID" : "MAN",
        g_target_rpm_left,
        g_target_rpm_right,
        g_enc_left.rpm,
        g_enc_right.rpm,
        g_speed_left,
        g_speed_right,
        (long)Encoder_GetTotalCount(&g_enc_left),
        (long)Encoder_GetTotalCount(&g_enc_right),
        MPU6050_GetYaw(),
        MPU6050_GetPitch(),
        MPU6050_GetRoll(),
        MPU6050_GetGyroZ()
    );
    server.send(200, "application/json", buf);
}

void WiFiController_Init(void)
{
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASS);

    dnsServer.start(53, "*", WiFi.softAPIP());

    server.on("/", handleRoot);
    server.on("/cmd", handleCmd);
    server.on("/telemetry", handleTelemetry);
    server.onNotFound(handleRoot);
    server.enableCORS();
    server.begin();

    Serial.printf("{\"info\":\"WiFi SoftAP Started. SSID: %s, Pass: %s, IP: 192.168.4.1\"}\r\n", AP_SSID, AP_PASS);
}

void WiFiController_Update(void)
{
    dnsServer.processNextRequest();
    server.handleClient();
}
