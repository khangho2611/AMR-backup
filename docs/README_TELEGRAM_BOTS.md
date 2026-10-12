# GIẢI TRÌNH KỸ THUẬT & KIẾN TRÚC ĐIỀU PHỐI 4 BOT TELEGRAM ("AI ENGINEERING LAB")

**Dự án:** AGV Autonomous Navigation System  
**Ngày lập:** 01/10/2026  
**Đơn vị thực hiện:** Khang AI Assistant (Broker & Hardware Owner duy nhất)  
**Kính gửi:** Codex / Lead Engineer / Sếp Khang  

---

## 1. TỔNG QUAN HIỆN TRẠNG & NGUYÊN NHÂN LỖI TRƯỚC ĐÓ

Trước đây, hệ thống 4 bot Telegram trong nhóm **"AI Engineering Lab"** (Chat ID: `-5550053050`) bao gồm:
1. `lead`: **@subagent_leader_bot** (👔 Lead Coordinator)
2. `coder`: **@suagent_coder_Bot** (💻 Coder Agent)
3. `tester`: **@subagent_tester_Bot** (🧪 QA Tester)
4. `writer`: **@subagent_writer_bot** (📝 Tech Writer)

Các con bot này đã từng hoạt động và đối thoại tự động thành công (như ảnh giao diện người dùng cung cấp). Tuy nhiên, trong quá trình vận hành gần đây, script gặp sự cố và bị đánh giá `NOT_DISPATCHED / UNVERIFIED` do 2 nguyên nhân cốt lõi:
1. **Masked Token Placeholder:** File `telegram_multi_agent_hub_v2.py` bị thay đuôi token bằng chuỗi che `***` (`8592415283:***`, `8811065117:***`, ...), khiến các yêu cầu gọi tới Telegram Bot API trả về `HTTP 404 / 401 Unauthorized`.
2. **Quy tắc Telegram Bot API (Bot-to-Bot Isolation):** Theo [Telegram Bot FAQ chính thức](https://core.telegram.org/bots/faq#why-doesn-t-my-bot-see-messages-from-other-bots), Telegram **cấm tuyệt đối các bot nhận tin nhắn từ các bot khác** trong cùng một nhóm. Do đó, nếu Khang AI Assistant hoặc bot Lead gửi tin nhắn vào nhóm, các bot khác không thể "nghe" trực tiếp được tin nhắn đó để tự kích hoạt.

---

## 2. DANH MỤC CÁC MODEL AI ĐƯỢC PHÂN BỔ CHO 4 BOT & GATEWAY NỘI BỘ

Toàn bộ các model AI phục vụ cho 4 bot được định tuyến qua **Local Project Server Gateway** (`http://localhost:8000/v1`), cấu hình trong cơ sở dữ liệu `gateway.db`.

### 2.1. Phân bổ Model cho từng vai trò của 4 con bot
1. **👔 Lead Coordinator (`lead`):**
   - **Model chỉ định:** `claude-opus-4-6-thinking` (Anthropic qua Google Code Assist pool)
   - **Đặc tính:** Khả năng lý luận sâu (Extended Thinking), bao quát kiến trúc toàn hệ thống, phân tích yêu cầu người dùng và chia nhỏ luồng việc không bị sót biên.
2. **💻 Coder Agent (`coder`):**
   - **Model chỉ định:** `claude-sonnet-4-6` (Anthropic) hoặc `gemini-3.8-flash-high`
   - **Đặc tính:** Tối ưu hóa viết mã nguồn C++ nhúng ESP32, Python ROS 2, tính toán số học chính xác, tuân thủ strict typing và PEP 8.
3. **🧪 QA Tester (`tester`):**
   - **Model chỉ định:** `claude-opus-4-6-thinking` (Anthropic)
   - **Đặc tính:** Khả năng phản biện sắc bén, phát hiện các trường hợp biên nguy hiểm (edge cases, NaN, timeout skew, deadlock, race condition).
4. **📝 Tech Writer (`writer`):**
   - **Model chỉ định:** `gemini-3.8-high` hoặc `gemini-3.1-pro`
   - **Đặc tính:** Khả năng tổng hợp báo cáo chi tiết, định dạng bảng Markdown chuẩn, kiểm tra đối chiếu mã băm SHA-256 chặt chẽ.

---

### 2.2. Danh mục chi tiết các Model kích hoạt trong Gateway (LOẠI TRỪ CÁC MODEL CHATGPT THƯỜNG)

Dưới đây là danh mục các model AI cao cấp đang mở trên Local Gateway (đã loại bỏ các model ChatGPT thông thường theo yêu cầu):

#### A. Nhóm Anthropic Claude (Định tuyến qua Google Cloud Code Assist - Free 0.00 USD)
1. **`claude-opus-4-6-thinking`**:
   - Model Opus thế hệ mới nhất kèm cơ chế tư duy mở rộng (Thinking Process).
   - Chuyên trách: Lập luận kiến trúc phức tạp, QA và đối soát logic an toàn.
2. **`claude-sonnet-4-6`**:
   - Model Sonnet tốc độ cao, khả năng code chuẩn mực hàng đầu.
   - Chuyên trách: Lập trình thuật toán, refactor module và xử lý I/O.

#### B. Nhóm Google Gemini (Định tuyến qua Google Code Assist - Free 0.00 USD)
3. **`gemini-3.8-flash-high` / `gemini-3.8-flash`**:
   - Model Flash thế hệ 3.8 với mức thinking level HIGH, độ trễ cực thấp (< 1 giây).
4. **`gemini-3.8-high` / `gemini-3.8-thinking`**:
   - Model Gemini 3.8 Pro tư duy sâu, phân tích dữ liệu đa phương thức và toán học.
5. **`gemini-3.1-pro`**:
   - Model Gemini thế hệ 3.1 bản Pro ổn định.
6. **`gemini-4-argon`**:
   - Bản thử nghiệm chuyên biệt (Closed Program).

---

### 2.3. Làm rõ đặc thù về model `gpt-5.6-sol-high` (ChatGPT Web Interface)

- **Bản chất kỹ thuật:** Model `gpt-5.6-sol-high` (hoặc alias `5.6 sol high`, `gpt-5.6-sol`) trong hệ thống **ĐƯỢC GỌI TỪ NỀN TẢNG WEB CHATGPT (ChatGPT Web Backend API qua cơ chế Reverse Proxy Session)**, **HOÀN TOÀN KHÔNG PHẢI MODEL CỦA CODEX CLI**.
- **Đặc tính:**
  - Kết nối qua pipeline backend SSE của ChatGPT Web.
  - Chi phí sử dụng: **0.00 USD** (không tính phí token API).
  - Khả năng: Phù hợp cho chat hội thoại, phân tích văn bản, suy luận ngôn ngữ tự nhiên. Không hỗ trợ native external tool calls (function calling phức tạp), do đó trong hệ thống AGV, vai trò điều phối công cụ và giám sát logic an toàn được giao cho `claude-opus-4-6-thinking` và các adapter chuyên biệt.

---

## 3. FILE TRIỂN KHAI & HƯỚNG DẪN CẤU HÌNH

### 3.1. File mã nguồn Hub chuẩn hóa
- Đường dẫn mã nguồn:
  `D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\Project server API\tools\telegram_multi_agent_hub_v2.py`
  (Bản sao lưu và tài liệu tại: `D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH\README_TELEGRAM_BOTS.md`)

### 3.2. Đường link tham chiếu kỹ thuật & tài liệu chính thức
1. **Telegram Official Bot FAQ (Giới hạn Bot-to-Bot):**  
   [https://core.telegram.org/bots/faq#why-doesn-t-my-bot-see-messages-from-other-bots](https://core.telegram.org/bots/faq#why-doesn-t-my-bot-see-messages-from-other-bots)
2. **Telegram Bot API Reference (Method sendMessage):**  
   [https://core.telegram.org/bots/api#sendmessage](https://core.telegram.org/bots/api#sendmessage)
3. **OpenAI Compatible Local API (Project Server Gateway):**  
   Endpoint: `http://localhost:8000/v1/chat/completions`

### 3.3. Hướng dẫn khởi chạy cho người vận hành (Sếp Khang)
1. Điền token thật của 4 bot do `@BotFather` cấp vào file môi trường hoặc chạy lệnh cấu hình:
   ```bash
   set TELEGRAM_LEAD_TOKEN=8592415283:AA...
   set TELEGRAM_CODER_TOKEN=8811065117:AA...
   set TELEGRAM_TESTER_TOKEN=8705434066:AA...
   set TELEGRAM_WRITER_TOKEN=8901825160:AA...
   ```
2. Khởi chạy tiến trình Hub:
   ```bash
   python "D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\Project server API\tools\telegram_multi_agent_hub_v2.py"
   ```
3. Khi Sếp chat trong nhóm `-5550053050`, Lead Bot sẽ tiếp nhận lệnh, phân rã task và kích hoạt Coder, Tester, Writer phản hồi trực tiếp.

---

## 4. CAM KẾT ĐỐI VỚI HỆ THỐNG AGV HIỆN TẠI
- Việc khôi phục hoặc điều chỉnh 4 bot Telegram **hoàn toàn chạy ở tầng ứng dụng người dùng và tài liệu**, tuyệt đối **KHÔNG can thiệp vào cổng Serial phần cứng** (`/dev/ttyUSB0`, `/dev/ttyUSB1`) của xe AGV trên sàn.
- Khang AI Assistant tiếp tục duy trì vai trò **Hardware / Serial Owner duy nhất**, đảm bảo xe đứng yên ở trạng thái tĩnh `DISARMED`, firmware `firmware_f5bf.bin` an toàn tuyệt đối.
