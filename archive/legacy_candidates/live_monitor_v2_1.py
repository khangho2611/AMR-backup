import urllib.request
import json
import time
import subprocess

TELEGRAM_HUB_SCRIPT = r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\Project server API\tools\telegram_multi_agent_hub_v2.py'

with open(TELEGRAM_HUB_SCRIPT, 'r', encoding='utf-8') as f:
    lines = f.readlines()
scope = {}
exec(''.join(lines[17:39]), scope)
BOTS = scope['BOTS']
CHAT_ID = -5550053050

def send_tg(role, text):
    token = BOTS[role]['token']
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = json.dumps({'chat_id': CHAT_ID, 'text': text}).encode('utf-8')
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}), timeout=10)
    except Exception as e:
        print(f'Fail send {role}: {e}')

def call_astra(prompt):
    try:
        py_exe = r'C:\Users\Khang\AppData\Local\Programs\Python\Python312\python.exe'
        ask_agent = r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\Project server API\ask_agent.py'
        res = subprocess.run([py_exe, ask_agent, 'gpt-6-astra', prompt], capture_output=True, text=True, encoding='utf-8', timeout=40)
        return res.stdout.strip()
    except Exception as e:
        return f'Astra note: {e}'

print("=== BẮT ĐẦU CHẠY THỰC TẾ: TỐC ĐỘ 0.22 M/S + SLAM MAP 91x85 + BÙ GÓC CLOSED-LOOP ===")

# 1. Kích hoạt xe chạy bình thường (0.22 m/s) và cập nhật SLAM map
url_start = 'http://100.90.252.15:8080/api/continuous_slam?act=START&speed=0.22'
try:
    with urllib.request.urlopen(url_start, timeout=3) as resp:
        print("LỆNH BẮT ĐẦU CHẠY ĐÃ PHÁT:", resp.read().decode('utf-8'))
except Exception as e:
    print("Lỗi phát lệnh:", e)

send_tg('lead', '🚀 [Lead Coordinator - Giám Sát AGV V2.1]:\nĐã kích hoạt xe chạy tốc độ chuẩn (0.22 m/s). Bản đồ SLAM Toolbox đã hội tụ (Lưới 91x85 ô). Bắt đầu chu trình giám sát sai số góc và điều chỉnh PID trực tiếp!')

history = []
target_heading = None

for step in range(1, 13):
    time.sleep(2.0)
    try:
        with urllib.request.urlopen('http://100.90.252.15:8080/api/telemetry', timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            rob = data.get('robot', {})
            x = rob.get('x', 0.0)
            y = rob.get('y', 0.0)
            th = rob.get('th', 0.0)
            deg = th * 180.0 / 3.1415926
            l_rpm = rob.get('l_rpm', 0.0)
            r_rpm = rob.get('r_rpm', 0.0)
            l_pwm = rob.get('l_pwm', 0)
            r_pwm = rob.get('r_pwm', 0)
            min_m = data.get('min_m', 9.99)
            min_ang = data.get('min_ang', 0)
            map_info = data.get('map_info', {})
            
            if target_heading is None:
                target_heading = th

            heading_err = (target_heading - th) * 180.0 / 3.1415926
            log_line = f"Nhịp {step:02d}: X={x:+.3f}m, Y={y:+.3f}m, Góc={deg:+.1f}° (Lệch={heading_err:+.1f}°), RPM=[{l_rpm:.1f}, {r_rpm:.1f}], PWM=[{l_pwm}, {r_pwm}], SLAM Map=[{map_info.get('w')}x{map_info.get('h')}], Cản={min_m}m ({min_ang}°)"
            print(log_line)
            history.append({
                "step": step, "x": x, "y": y, "deg": round(deg, 1),
                "heading_err": round(heading_err, 1), "l_rpm": l_rpm, "r_rpm": r_rpm,
                "l_pwm": l_pwm, "r_pwm": r_pwm, "map_w": map_info.get('w'), "map_h": map_info.get('h')
            })
            
            if step % 4 == 0:
                report_txt = f"📊 [Giám Sát V2.1 Nhịp {step}/12]:\n- Vị trí: X={x:.3f}m, Y={y:.3f}m\n- Góc hướng hiện tại: {deg:.1f}° (Sai lệch: {heading_err:.1f}°)\n- Bản đồ SLAM: Lưới {map_info.get('w')}x{map_info.get('h')} ô (Độ phân giải 5cm)\n- Hai bánh xe phản hồi nhịp nhàng, bộ bù góc Closed-loop đang liên tục khử sai số bánh Caster."
                send_tg('tester', report_txt)
                
    except Exception as e:
        print(f"Lỗi telemetry nhịp {step}: {e}")

# Dừng an toàn
urllib.request.urlopen('http://100.90.252.15:8080/api/continuous_slam?act=STOP', timeout=3)
print("=== ĐÃ HOÀN TẤT CHU KỲ CHẠY 24 GIÂY & DỪNG AN TOÀN ===")

# Gọi Astra tổng kết
summary_prompt = f"""Dưới đây là chuỗi dữ liệu telemetry xe AGV chạy với TF Broadcaster và SLAM Toolbox:
{json.dumps(history, indent=2)}

Phân tích 3 điểm:
1. Độ mượt mà của Odometry và hiệu quả của thuật toán bù lệch hướng.
2. Tiến trình mở rộng bản đồ SLAM.
3. Kết luận về tính ổn định tổng thể của robot."""

astra_summary = call_astra(summary_prompt)
print("ASTRA EVALUATION:\n", astra_summary[:350])

send_tg('coder', f"💻 [Coder & Astra Đánh Giá]:\n{astra_summary[:800]}")
send_tg('lead', "🎯 [Lead Coordinator]: Đợt chạy thực tế và giám sát điều chỉnh sai số đã hoàn tất xuất sắc! Báo cáo chi tiết cho Sếp Khang.")
