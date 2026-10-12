#include "wifi_controller.h"
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <Arduino.h>
#include "encoder.h"
#include "pid.h"
#include "robot_motor.h"
#include "mke_m18.h"
#include "odometry.h"

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
extern Odometry_t g_odometry;

static const char* AP_SSID = "esp32";
static const char* AP_PASS = "12312312";

static WebServer server(80);
static DNSServer dnsServer;
static Preferences prefs;

enum AutoTestState {
    TEST_IDLE = 0,
    TEST_STRAIGHT_1M,
    TEST_ROTATE_360,
    TEST_SQUARE_STAGE
};

static AutoTestState s_test_state = TEST_IDLE;
static int s_square_step = 0;
static float s_start_x = 0.0f;
static float s_start_y = 0.0f;
static float s_start_theta = 0.0f;
static uint32_t s_test_stage_start_ms = 0;

static float NormAngle(float a) {
    while (a > 3.14159265f) a -= 2.0f * 3.14159265f;
    while (a < -3.14159265f) a += 2.0f * 3.14159265f;
    return a;
}

static const char WIFI_CONFIG_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Cấu Hình Wi-Fi Robot AGV</title>
  <style>
    * { box-sizing: border-box; font-family: -apple-system, sans-serif; }
    body { background: #0f172a; color: #f8fafc; padding: 20px; display: flex; flex-direction: column; justify-content: center; min-height: 100vh; margin: 0; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 24px; max-width: 400px; width: 100%; margin: 0 auto; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
    h2 { color: #38bdf8; margin-top: 0; text-align: center; }
    p { font-size: 13px; color: #94a3b8; text-align: center; margin-bottom: 20px; }
    label { font-size: 12px; font-weight: 700; color: #cbd5e1; text-transform: uppercase; margin-bottom: 6px; display: block; }
    input { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #475569; background: #0b1120; color: #fff; font-size: 15px; margin-bottom: 16px; outline: none; }
    input:focus { border-color: #38bdf8; }
    button { width: 100%; padding: 14px; border-radius: 8px; border: none; background: #0284c7; color: #fff; font-size: 16px; font-weight: 800; cursor: pointer; }
    button:active { background: #0369a1; transform: scale(0.98); }
    .skip-btn { background: #334155; margin-top: 10px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>📡 CẤU HÌNH WI-FI ROBOT</h2>
    <p>Nhập tên Wi-Fi nhà bạn (băng tần 2.4GHz) để xe tự kết nối và mở giao diện điều khiển.</p>
    <form action="/savewifi" method="POST">
      <label>Tên Wi-Fi (SSID):</label>
      <input type="text" name="ssid" placeholder="Ví dụ: Ruby" required autofocus>
      <label>Mật khẩu Wi-Fi:</label>
      <input type="password" name="pass" placeholder="Nhập mật khẩu Wi-Fi">
      <button type="submit">LƯU & KẾT NỐI NGAY</button>
      <button type="button" class="skip-btn" onclick="location.href='/control'">BỎ QUA, VÀO BẢNG ĐIỀU KHIỂN</button>
    </form>
  </div>
</body>
</html>
)rawliteral";

static const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>ESP32 AGV Robot Controller</title>
  <style>
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; -webkit-touch-callout: none; user-select: none; }
    body {
      margin: 0; padding: 10px; background: #0b1120; color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh; display: flex; flex-direction: column; justify-content: space-between;
    }
    .header {
      display: flex; align-items: center; justify-content: space-between;
      padding-bottom: 8px; border-bottom: 1px solid #1e293b;
    }
    .title { font-size: 15px; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 6px; }
    .badge { font-size: 11px; padding: 3px 8px; border-radius: 999px; background: #064e3b; color: #34d399; font-weight: 700; }
    .wifi-link { font-size: 11px; color: #94a3b8; text-decoration: none; border: 1px solid #334155; padding: 3px 8px; border-radius: 6px; }

    .odom-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 8px 0; }
    .odom-card { background: #0f172a; border: 1px solid #0284c7; border-radius: 10px; padding: 6px; text-align: center; }
    .odom-title { font-size: 10px; color: #94a3b8; font-weight: 700; text-transform: uppercase; }
    .odom-val { font-size: 18px; font-weight: 900; color: #38bdf8; }

    .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px; }
    .card { background: #131d31; border: 1px solid #1e293b; border-radius: 10px; padding: 6px; text-align: center; }
    .card-title { font-size: 10px; color: #94a3b8; font-weight: 700; text-transform: uppercase; }
    .card-val { font-size: 18px; font-weight: 900; color: #38bdf8; }
    .card-sub { font-size: 10px; color: #64748b; margin-top: 2px; }

    .test-box { background: #131d31; border: 1px solid #334155; border-radius: 12px; padding: 8px; margin-bottom: 8px; }
    .test-title { font-size: 11px; font-weight: 800; color: #fbbf24; text-transform: uppercase; margin-bottom: 6px; display: flex; justify-content: space-between; }
    .test-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .test-btn {
      padding: 8px 4px; font-size: 11px; font-weight: 800; border-radius: 8px;
      border: 1px solid #d97706; background: #78350f; color: #fef3c7; cursor: pointer;
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
    }
    .test-btn:active { background: #b45309; transform: scale(0.96); }

    .dpad {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
      max-width: 310px; width: 100%; margin: 0 auto;
    }
    .btn {
      height: 60px; border-radius: 14px; border: 2px solid #334155; background: #1e293b;
      color: #f8fafc; font-size: 20px; font-weight: 900; display: flex; flex-direction: column;
      align-items: center; justify-content: center; touch-action: none;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.4);
    }
    .btn.pressed { background: #0284c7 !important; border-color: #38bdf8 !important; transform: scale(0.94); }
    .btn-stop { background: #881337; border-color: #be123c; color: #fda4af; }
    .btn-stop.pressed { background: #e11d48 !important; }
    .btn-sub { font-size: 9px; font-weight: 700; opacity: 0.85; margin-top: 1px; }

    .footer { text-align: center; font-size: 10px; color: #64748b; margin-top: 6px; }
  </style>
</head>
<body>

  <div>
    <div class="header">
      <div class="title">🤖 ROBOT AGV (L=18.75cm)</div>
      <div style="display:flex; gap:6px; align-items:center;">
        <a href="/wifi" class="wifi-link">⚙ Wi-Fi</a>
        <div class="badge" id="testBadge">SẴN SÀNG</div>
      </div>
    </div>

    <div class="odom-grid">
      <div class="odom-card"><div class="odom-title">X (Mét)</div><div class="odom-val" id="odX">0.000</div></div>
      <div class="odom-card"><div class="odom-title">Y (Mét)</div><div class="odom-val" id="odY">0.000</div></div>
      <div class="odom-card"><div class="odom-title">Góc (Độ)</div><div class="odom-val" id="odTh">0.0°</div></div>
    </div>

    <div class="stats-grid">
      <div class="card">
        <div class="card-title">Bánh Trái</div>
        <div class="card-val" id="lRpm">0.0</div>
        <div class="card-sub">PWM: <span id="lPwm">0</span> | RPM</div>
      </div>
      <div class="card">
        <div class="card-title">Bánh Phải</div>
        <div class="card-val" id="rRpm">0.0</div>
        <div class="card-sub">PWM: <span id="rPwm">0</span> | RPM</div>
      </div>
    </div>

    <div class="test-box">
      <div class="test-title">
        <span>⚡ TEST HÌNH HỌC TỰ ĐỘNG</span>
        <span style="color:#38bdf8; cursor:pointer;" onclick="sendCmd('RESET')">↺ RESET TỌA ĐỘ</span>
      </div>
      <div class="test-grid">
        <button class="test-btn" onclick="startAutoTest('STRAIGHT')">
          <span>📏 1 MÉT</span>
          <span style="font-size:9px; opacity:0.8;">Chạy thẳng 1m</span>
        </button>
        <button class="test-btn" onclick="startAutoTest('ROTATE')">
          <span>🔄 360°</span>
          <span style="font-size:9px; opacity:0.8;">Xoay 1 vòng</span>
        </button>
        <button class="test-btn" onclick="startAutoTest('SQUARE')">
          <span>⬛ HÌNH VUÔNG</span>
          <span style="font-size:9px; opacity:0.8;">10cm x 10cm về đích</span>
        </button>
      </div>
    </div>
  </div>

  <div class="dpad">
    <button class="btn" id="btnQ"><span>↺</span><span class="btn-sub">QUAY T</span></button>
    <button class="btn" id="btnW"><span>▲</span><span class="btn-sub">TIẾN</span></button>
    <button class="btn" id="btnE"><span>↻</span><span class="btn-sub">QUAY P</span></button>

    <button class="btn" id="btnA"><span>◄</span><span class="btn-sub">TRÁI</span></button>
    <button class="btn btn-stop" id="btnStop" onclick="emergencyStop()"><span>🛑</span><span class="btn-sub">DỪNG LẬP TỨC</span></button>
    <button class="btn" id="btnD"><span>►</span><span class="btn-sub">PHẢI</span></button>

    <div></div>
    <button class="btn" id="btnS"><span>▼</span><span class="btn-sub">LÙI</span></button>
    <div></div>
  </div>

  <div class="footer">Giữ phím để chạy • Buông tay xe dừng • Bấm STOP dừng mọi bài test</div>

  <script>
    const SPEED = 130;
    let isMoving = false;
    let currentCmdFunc = null;
    let heartbeatTimer = null;

    function sendCmd(cmd) {
      fetch('/cmd?val=' + encodeURIComponent(cmd)).catch(()=>{});
    }

    function emergencyStop() {
      if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
      isMoving = false;
      currentCmdFunc = null;
      fetch('/test?act=STOP').catch(()=>{});
      sendCmd('STOP');
      document.getElementById('testBadge').innerText = 'ĐÃ DỪNG';
      document.getElementById('testBadge').style.background = '#881337';
    }

    function startAutoTest(type) {
      fetch('/test?act=' + type).then(r=>r.json()).then(d=>{
        document.getElementById('testBadge').innerText = 'ĐANG CHẠY: ' + type;
        document.getElementById('testBadge').style.background = '#d97706';
      }).catch(()=>{});
    }

    function startMotion(cmdFunc) {
      isMoving = true;
      currentCmdFunc = cmdFunc;
      sendCmd(cmdFunc());

      if (heartbeatTimer) clearInterval(heartbeatTimer);
      heartbeatTimer = setInterval(() => {
        if (isMoving && currentCmdFunc) sendCmd(currentCmdFunc());
      }, 150);
    }

    function stopMotion() {
      isMoving = false;
      currentCmdFunc = null;
      if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
      document.querySelectorAll('.btn').forEach(b => b.classList.remove('pressed'));
      sendCmd('STOP');
    }

    const motions = {
      'btnW': () => `S ${SPEED} ${SPEED}`,
      'btnS': () => `S -${SPEED} -${SPEED}`,
      'btnA': () => `S 0 ${SPEED}`,
      'btnD': () => `S ${SPEED} 0`,
      'btnQ': () => `S -${SPEED} ${SPEED}`,
      'btnE': () => `S ${SPEED} -${SPEED}`
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
      const release = (e) => {
        e.preventDefault();
        try { el.releasePointerCapture(e.pointerId); } catch(err){}
        el.classList.remove('pressed');
        stopMotion();
      };
      el.addEventListener('pointerup', release);
      el.addEventListener('pointercancel', release);
    }

    Object.keys(motions).forEach(id => bindButton(id, motions[id]));

    setInterval(() => {
      fetch('/telemetry').then(r => r.json()).then(d => {
        document.getElementById('lRpm').innerText = Math.abs(d.l_rpm || 0).toFixed(1);
        document.getElementById('rRpm').innerText = Math.abs(d.r_rpm || 0).toFixed(1);
        document.getElementById('lPwm').innerText = d.l_pwm || 0;
        document.getElementById('rPwm').innerText = d.r_pwm || 0;

        document.getElementById('odX').innerText = (d.x || 0).toFixed(3);
        document.getElementById('odY').innerText = (d.y || 0).toFixed(3);
        let deg = ((d.th || 0) * 180.0 / Math.PI).toFixed(1);
        document.getElementById('odTh').innerText = deg + "°";

        if (d.test === 'IDLE' && document.getElementById('testBadge').innerText.startsWith('ĐANG CHẠY')) {
          document.getElementById('testBadge').innerText = 'HOÀN THÀNH';
          document.getElementById('testBadge').style.background = '#064e3b';
        }
      }).catch(()=>{});
    }, 100);
  </script>
</body>
</html>
)rawliteral";

static void handleRoot(void) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    if (WiFi.status() == WL_CONNECTED) {
        server.send(200, "text/html", INDEX_HTML);
    } else {
        server.send(200, "text/html", WIFI_CONFIG_HTML);
    }
}

static void handleControl(void) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "text/html", INDEX_HTML);
}

static void handleWifiPage(void) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "text/html", WIFI_CONFIG_HTML);
}

static void handleSaveWifi(void) {
    if (server.hasArg("ssid")) {
        String ssid = server.arg("ssid");
        String pass = server.arg("pass");

        prefs.begin("robot_wifi", false);
        prefs.putString("ssid", ssid);
        prefs.putString("pass", pass);
        prefs.end();

        String html = "<html><body style='background:#0f172a;color:#38bdf8;font-family:sans-serif;text-align:center;padding:50px;'>"
                      "<h2>Da luu Wi-Fi: " + ssid + "</h2>"
                      "<p style='color:#fff;'>ESP32 dang ket noi vao Wi-Fi... Dang chuyen ve trang dieu khien!</p>"
                      "<script>setTimeout(()=>{ location.href='/control'; }, 3000);</script>"
                      "</body></html>";
        server.send(200, "text/html", html);

        delay(500);
        Serial.printf("{\"info\":\"Connecting to saved WiFi: %s...\"}\r\n", ssid.c_str());
        WiFi.begin(ssid.c_str(), pass.c_str());
    } else {
        server.send(400, "text/plain", "Missing ssid");
    }
}

static void handleCmd(void) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    if (server.hasArg("val")) {
        String val = server.arg("val");
        Execute_Robot_Command(val.c_str());
        server.send(200, "application/json", "{\"status\":\"ok\"}");
    } else {
        server.send(400, "text/plain", "Missing val");
    }
}

static void handleAutoTest(void) {
    server.sendHeader("Access-Control-Allow-Origin", "*");

    /* KHÔNG cho phép khởi động AutoTest từ Wi-Fi khi chưa ARMED hoặc đang FAULT */
    extern volatile uint8_t g_safety_state; // enum RobotSafetyState_t
    if (g_safety_state != 1) { // 1 = STATE_ARMED
        server.send(403, "application/json", "{\"error\":\"DISARMED_REJECT_TEST\"}");
        return;
    }

    if (server.hasArg("act")) {
        String act = server.arg("act");

        s_start_x = g_odometry.x;
        s_start_y = g_odometry.y;
        s_start_theta = g_odometry.theta;
        s_test_stage_start_ms = millis();

        if (act == "STRAIGHT") {
            s_test_state = TEST_STRAIGHT_1M;
            Serial.printf("{\"auto_test_start\":\"STRAIGHT_1M\",\"start_x\":%.3f,\"start_y\":%.3f}\r\n", s_start_x, s_start_y);
        } else if (act == "ROTATE") {
            s_test_state = TEST_ROTATE_360;
            Serial.printf("{\"auto_test_start\":\"ROTATE_360\",\"start_th\":%.3f}\r\n", s_start_theta);
        } else if (act == "SQUARE") {
            s_test_state = TEST_SQUARE_STAGE;
            s_square_step = 0;
            Serial.printf("{\"auto_test_start\":\"SQUARE_1M\"}\r\n");
        } else {
            s_test_state = TEST_IDLE;
            Execute_Robot_Command("STOP");
        }
        server.send(200, "application/json", "{\"status\":\"started\"}");
    } else {
        server.send(400, "text/plain", "Missing act");
    }
}

static void handleTelemetry(void) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    char buf[220];
    const char* test_str = (s_test_state == TEST_IDLE) ? "IDLE" : "RUNNING";
    snprintf(buf, sizeof(buf),
        "{\"mode\":\"%s\",\"l_tgt\":%.1f,\"r_tgt\":%.1f,\"l_rpm\":%.2f,\"r_rpm\":%.2f,\"l_pwm\":%d,\"r_pwm\":%d,\"x\":%.3f,\"y\":%.3f,\"th\":%.3f,\"test\":\"%s\"}",
        (g_control_mode == MODE_PID) ? "PID" : "MAN",
        g_target_rpm_left,
        g_target_rpm_right,
        g_enc_left.rpm,
        g_enc_right.rpm,
        g_speed_left,
        g_speed_right,
        g_odometry.x,
        g_odometry.y,
        g_odometry.theta,
        test_str
    );
    server.send(200, "application/json", buf);
}

void WiFiController_CancelAutoTest(void)
{
    s_test_state = TEST_IDLE;
    s_square_step = 0;
}

void WiFiController_Init(void) {
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(AP_SSID, AP_PASS);

    dnsServer.start(53, "*", WiFi.softAPIP());

    server.on("/", handleRoot);
    server.on("/control", handleControl);
    server.on("/wifi", handleWifiPage);
    server.on("/savewifi", HTTP_POST, handleSaveWifi);
    server.on("/cmd", handleCmd);
    server.on("/test", handleAutoTest);
    server.on("/telemetry", handleTelemetry);
    server.onNotFound(handleRoot);
    server.enableCORS();
    server.begin();

    Serial.printf("{\"info\":\"WiFi AP Active: SSID '%s', Pass '%s', IP 192.168.4.1\"}\r\n", AP_SSID, AP_PASS);

    prefs.begin("robot_wifi", true);
    String saved_ssid = prefs.getString("ssid", "");
    String saved_pass = prefs.getString("pass", "");
    prefs.end();

    if (saved_ssid.length() > 0) {
        Serial.printf("{\"info\":\"Connecting to saved WiFi '%s'...\"}\r\n", saved_ssid.c_str());
        WiFi.begin(saved_ssid.c_str(), saved_pass.c_str());
    }
}

void WiFiController_Update(void) {
    dnsServer.processNextRequest();
    server.handleClient();

    static bool s_sta_reported = false;
    if (WiFi.status() == WL_CONNECTED && !s_sta_reported) {
        s_sta_reported = true;
        Serial.printf("{\"wifi_connected\":\"%s\",\"local_ip\":\"%s\"}\r\n",
                      WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
    }

    if (s_test_state == TEST_IDLE) return;

    if (millis() - s_test_stage_start_ms > 25000) {
        s_test_state = TEST_IDLE;
        Execute_Robot_Command("STOP");
        return;
    }

    float cur_x = g_odometry.x;
    float cur_y = g_odometry.y;
    float cur_th = g_odometry.theta;

    if (s_test_state == TEST_STRAIGHT_1M) {
        float dist = sqrtf((cur_x - s_start_x)*(cur_x - s_start_x) + (cur_y - s_start_y)*(cur_y - s_start_y));
        
        static uint32_t last_log_ms = 0;
        if (millis() - last_log_ms >= 200) {
            last_log_ms = millis();
            int32_t cnt_l = Encoder_GetTotalCount(&g_enc_left);
            int32_t cnt_r = Encoder_GetTotalCount(&g_enc_right);
            Serial.printf("{\"test_1m\":{\"dist_m\":%.3f,\"pulse_l\":%ld,\"pulse_r\":%ld,\"rpm_l\":%.1f,\"rpm_r\":%.1f}}\r\n",
                          dist, cnt_l, cnt_r, g_enc_left.rpm, g_enc_right.rpm);
        }

        if (dist < 1.00f) {
            Execute_Robot_Command("V 0.30 0.0");
        } else {
            Execute_Robot_Command("STOP");
            s_test_state = TEST_IDLE;
            int32_t cnt_l = Encoder_GetTotalCount(&g_enc_left);
            int32_t cnt_r = Encoder_GetTotalCount(&g_enc_right);
            Serial.printf("{\"test_1m_done\":{\"final_dist\":%.3f,\"final_pulse_l\":%ld,\"final_pulse_r\":%ld,\"status\":\"STOPPED_EXACT_1M\"}}\r\n",
                          dist, cnt_l, cnt_r);
        }
    }
    else if (s_test_state == TEST_ROTATE_360) {
        float rot_diff = fabsf(NormAngle(cur_th - s_start_theta));
        if (millis() - s_test_stage_start_ms < 1000 || rot_diff > 0.12f) {
            Execute_Robot_Command("V 0.0 1.20");
        } else {
            Execute_Robot_Command("STOP");
            s_test_state = TEST_IDLE;
        }
    }
    /* 3. BÀI TEST HÌNH VUÔNG 10CM x 10CM (0.10M x 0.10M NHỎ GỌN GẤP 10 LẦN) */
    else if (s_test_state == TEST_SQUARE_STAGE) {
        if ((s_square_step % 2) == 0) {
            /* Đi thẳng cạnh 10 cm (0.10 mét) */
            float dist = sqrtf((cur_x - s_start_x)*(cur_x - s_start_x) + (cur_y - s_start_y)*(cur_y - s_start_y));
            if (dist < 0.10f) {
                Execute_Robot_Command("V 0.12 0.0"); // Tốc độ bò chậm êm 0.12 m/s
            } else {
                Execute_Robot_Command("STOP");
                s_square_step++;
                s_start_theta = cur_th;
                s_test_stage_start_ms = millis();
                delay(300);
            }
        } else {
            /* Rẽ góc vuông 90 độ chuẩn (1.571 rad) với tốc độ xoay êm */
            float rot = fabsf(NormAngle(cur_th - s_start_theta));
            if (rot < 1.571f) {
                Execute_Robot_Command("V 0.0 0.80"); // Giảm tốc xoay 0.8 rad/s chống trớn
            } else {
                Execute_Robot_Command("STOP");
                s_square_step++;
                s_start_x = cur_x;
                s_start_y = cur_y;
                s_test_stage_start_ms = millis();
                delay(300);
                if (s_square_step >= 8) { // Đủ 4 cạnh và 4 góc rẽ 90 độ
                    s_test_state = TEST_IDLE;
                }
            }
        }
    }
}
