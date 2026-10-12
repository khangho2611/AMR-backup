# -*- coding: utf-8 -*-
"""
Cập nhật toàn diện và duy nhất vào:
D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH\TINH_TOAN_THIET_KE_XE_TU_HANH.docx

Bổ sung:
1. Động học thuận (Forward Kinematics): Từ tốc độ bánh (omega_R, omega_L) -> Vận tốc xe (v, omega) & Ma trận Jacobi 3x2.
2. Động học nghịch (Inverse Kinematics): Từ lệnh điều khiển (v, omega) -> Tốc độ đặt cho từng bánh (omega_R, omega_L).
3. Tích hợp thông số thực tế: L = 18.75 cm (0.1875 m), R = 3.66 cm (0.0366 m), Động cơ GA25 280 RPM, Driver I2C MKE-M18 BD62130, Pin Waveshare UPS 3S, Buck XL4015 5A.
4. Mọi công thức đều có định nghĩa ý nghĩa vật lý và chú giải biến số rõ ràng, chuẩn Word Equation Native (OMML).
"""
import os
import lxml.etree as ET
import latex2mathml.converter
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml

target_dir = r"D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH"
os.makedirs(target_dir, exist_ok=True)
out_docx = os.path.join(target_dir, "TINH_TOAN_THIET_KE_XE_TU_HANH.docx")

xslt_path = r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"
xslt = ET.parse(xslt_path)
xslt_transform = ET.XSLT(xslt)

doc = Document()

for section in doc.sections:
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(0.8)

BLACK = RGBColor(0, 0, 0)
PRIMARY = RGBColor(0, 51, 102)

def format_p(p, ls=1.3, sa=4, sb=0, al=WD_ALIGN_PARAGRAPH.LEFT, indent=0):
    p.paragraph_format.line_spacing = ls
    p.paragraph_format.space_after = Pt(sa)
    p.paragraph_format.space_before = Pt(sb)
    p.alignment = al
    if indent > 0:
        p.paragraph_format.left_indent = Inches(indent)
    return p

def add_title(text):
    p = doc.add_paragraph()
    format_p(p, 1.2, 4, 10, WD_ALIGN_PARAGRAPH.CENTER)
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(16)
    r.font.bold = True
    r.font.color.rgb = BLACK

def add_subtitle(text):
    p = doc.add_paragraph()
    format_p(p, 1.2, 14, 2, WD_ALIGN_PARAGRAPH.CENTER)
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)
    r.font.bold = True
    r.font.color.rgb = PRIMARY

def add_h1(text):
    p = doc.add_paragraph()
    format_p(p, 1.2, 4, 12, WD_ALIGN_PARAGRAPH.LEFT)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(13)
    r.font.bold = True
    r.font.color.rgb = PRIMARY

def add_h2(text):
    p = doc.add_paragraph()
    format_p(p, 1.2, 3, 8, WD_ALIGN_PARAGRAPH.LEFT)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)
    r.font.bold = True
    r.font.color.rgb = BLACK

def add_body(text, bold_prefix="", indent=0):
    p = doc.add_paragraph()
    format_p(p, 1.3, 3, 0, WD_ALIGN_PARAGRAPH.LEFT, indent)
    if bold_prefix:
        rb = p.add_run(bold_prefix)
        rb.font.name = "Times New Roman"
        rb.font.size = Pt(12)
        rb.font.bold = True
        rb.font.color.rgb = BLACK
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)
    r.font.color.rgb = BLACK

def add_eq(latex_code):
    mathml = latex2mathml.converter.convert(latex_code)
    tree = ET.fromstring(mathml)
    omml = xslt_transform(tree)
    ostr = ET.tostring(omml, encoding="utf-8").decode("utf-8")
    p = doc.add_paragraph()
    format_p(p, 1.25, 8, 8, WD_ALIGN_PARAGRAPH.CENTER)
    p._p.append(parse_xml(f'<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">{ostr}</m:oMathPara>'))

# TIÊU ĐỀ TÀI LIỆU
add_title("BẢN TÍNH TOÁN THIẾT KẾ ĐỘNG LỰC HỌC, ĐỘNG HỌC VÀ ĐIỀU KHIỂN XE TỰ HÀNH (AGV)")
add_subtitle("HỆ THỐNG THỰC TẾ: XE 1.75 KG, ĐỘNG CƠ GA25 280RPM, DRIVER I2C MKE-M18 VÀ NGUỒN PIN 3S WAVESHARE")

# =========================================================================
# MỤC 1: TỔNG TẢI TRỌNG
# =========================================================================
add_h1("1. TỔNG TẢI TRỌNG VÀ PHÂN BỔ KHỐI LƯỢNG THỰC TẾ")
add_body("Khối lượng thực tế cân được của xe sau khi lắp đặt hoàn chỉnh gồm khung gầm, khối pin 3S, bo mạch vi điều khiển, driver và 2 động cơ là m_thuc = 1.75 kg. Cấu hình cơ khí gồm 1 bánh tự lựa (caster) dẫn hướng phía trước và 2 bánh chủ động dẫn động độc lập phía sau.")

add_h2("1.1. Công thức tính tổng khối lượng thiết kế có hệ số an toàn")
add_body("Tổng khối lượng thiết kế là khối lượng dùng để tính toán động cơ, bằng khối lượng thực tế nhân với hệ số an toàn dự phòng (chọn k_s = 1.2, tương ứng tính dư thêm 20% tải để dự phòng phụ kiện và cáp nối phát sinh):")
add_eq(r"M = m_{thuc} \cdot k_s")
add_body("Trong đó:")
add_body("M: Tổng khối lượng tính toán của xe (đơn vị: kg).", bold_prefix="• ")
add_body("m_thuc: Khối lượng thực tế cân được của xe (m_thuc = 1.75 kg).", bold_prefix="• ")
add_body("k_s: Hệ số an toàn thiết kế (k_s = 1.2).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"M = 1.75 \cdot 1.2 = 2.10\text{ kg}")

add_h2("1.2. Công thức tính trọng lực toàn xe")
add_body("Trọng lực là lực hút của Trái Đất tác dụng lên toàn bộ khối lượng xe theo phương thẳng đứng vuông góc với mặt sàn:")
add_eq(r"P = M \cdot g")
add_body("Trong đó:")
add_body("P: Trọng lực toàn phần của xe (đơn vị: N).", bold_prefix="• ")
add_body("M: Tổng khối lượng tính toán (M = 2.10 kg).", bold_prefix="• ")
add_body("g: Gia tốc trọng trường (lấy chuẩn g = 9.81 m/s²).", bold_prefix="• ")
add_body("Thay số:")
add_eq(r"P = 2.10 \cdot 9.81 = 20.601\text{ N}")

add_h2("1.3. Phân bổ tải trọng lên các cụm bánh xe")
add_body("Để 2 bánh dẫn động phía sau có đủ ma sát bám sàn, tránh hiện tượng trượt quay khi khởi động hoặc phanh, đồng thời bánh caster trước đủ nhẹ để chuyển hướng mượt, tải trọng phân bổ theo tỷ lệ 70% đè lên 2 bánh sau và 30% đè lên bánh trước:")
add_body("1. Trọng lực dồn lên 2 bánh dẫn động sau:")
add_eq(r"P_{sau} = 0.70 \cdot P = 0.70 \cdot 20.601 = 14.42\text{ N}")
add_body("Mỗi bánh sau chịu tải trọng:")
add_eq(r"P_{banh\_sau} = \dfrac{P_{sau}}{2} = \dfrac{14.42}{2} = 7.21\text{ N} \approx 0.735\text{ kg/bánh}")
add_body("2. Trọng lực dồn lên bánh caster trước:")
add_eq(r"P_{caster} = 0.30 \cdot P = 0.30 \cdot 20.601 = 6.18\text{ N} \approx 0.630\text{ kg}")

# =========================================================================
# MỤC 2: THÔNG SỐ HÌNH HỌC BÁNH XE
# =========================================================================
add_h1("2. THÔNG SỐ HÌNH HỌC BÁNH XE THỰC TẾ")
add_body("Bánh xe đi kèm bộ động cơ GA25 có chu vi vòng tròn ngoài đo được trực tiếp bằng thước dây là C = 23 cm (0.23 m). Khoảng cách giữa hai tâm bánh xe dẫn động sau đo được là L = 18.75 cm (0.1875 m).")

add_h2("2.1. Công thức tính đường kính và bán kính bánh xe")
add_body("Đường kính bánh xe được tính từ chu vi theo công thức hình học:")
add_eq(r"D = \dfrac{C}{\pi}")
add_body("Trong đó:")
add_body("D: Đường kính bánh xe (đơn vị: m).", bold_prefix="• ")
add_body("C: Chu vi bánh xe (C = 0.23 m).", bold_prefix="• ")
add_body("pi: Hằng số Pi (lấy 3.1416).", bold_prefix="• ")
add_body("Thay số:")
add_eq(r"D = \dfrac{0.23}{3.1416} \approx 0.0732\text{ m} = 73.2\text{ mm}")

add_body("Bán kính bánh xe bằng một nửa đường kính:")
add_eq(r"R = \dfrac{D}{2} = \dfrac{0.0732}{2} = 0.0366\text{ m} = 36.6\text{ mm}")

# =========================================================================
# MỤC 3: LỰC CẢN VÀ MÔ-MEN XOẮN
# =========================================================================
add_h1("3. TÍNH TOÁN LỰC CẢN VÀ MÔ-MEN XOẮN YÊU CẦU")
add_h2("3.1. Công thức tính lực cản lăn")
add_body("Lực cản lăn xuất hiện do ma sát tiếp xúc và biến dạng giữa lốp cao su của bánh xe với mặt sàn phẳng khi xe di chuyển đều:")
add_eq(r"F_{lan} = \mu \cdot P = \mu \cdot M \cdot g")
add_body("Trong đó:")
add_body("F_lan: Lực cản lăn của xe (đơn vị: N).", bold_prefix="• ")
add_body("mu: Hệ số cản lăn sàn gạch/gỗ phẳng (lấy chuẩn mu = 0.02).", bold_prefix="• ")
add_body("P: Trọng lực toàn xe (P = 20.601 N).", bold_prefix="• ")
add_body("Thay số:")
add_eq(r"F_{lan} = 0.02 \cdot 20.601 = 0.412\text{ N}")

add_h2("3.2. Công thức tính lực quán tính khi tăng tốc")
add_body("Lực quán tính là lực cản trở gia tốc khi xe bắt đầu tăng tốc từ vị trí đứng yên lên tốc độ định mức theo Định luật II Newton:")
add_eq(r"F_{qt} = M \cdot a")
add_body("Trong đó:")
add_body("F_qt: Lực quán tính khi tăng tốc (đơn vị: N).", bold_prefix="• ")
add_body("M: Tổng khối lượng tính toán (M = 2.10 kg).", bold_prefix="• ")
add_body("a: Gia tốc tăng tốc mong muốn (chọn a = 0.3 m/s² để xe khởi động êm mượt, không giật trượt bánh).", bold_prefix="• ")
add_body("Thay số:")
add_eq(r"F_{qt} = 2.10 \cdot 0.3 = 0.630\text{ N}")

add_h2("3.3. Tổng lực kéo yêu cầu toàn xe và lực đẩy mỗi bánh")
add_body("Tổng lực kéo là hợp lực động cơ cần tạo ra tại thời điểm khởi động tăng tốc:")
add_eq(r"F_{keo} = F_{lan} + F_{qt} = 0.412 + 0.630 = 1.042\text{ N}")
add_body("Mỗi bánh dẫn động sau cần tạo ra một lực đẩy tiếp tuyến:")
add_eq(r"F_{banh} = \dfrac{F_{keo}}{2} = \dfrac{1.042}{2} = 0.521\text{ N}")

add_h2("3.4. Mô-men xoắn cần thiết trên trục bánh xe")
add_body("Mô-men xoắn yêu cầu là tích số giữa lực đẩy tiếp tuyến với bán kính bánh xe, chia cho hiệu suất truyền động:")
add_eq(r"T_{banh} = \dfrac{F_{banh} \cdot R}{\eta}")
add_body("Trong đó:")
add_body("T_banh: Mô-men xoắn yêu cầu trên trục bánh (đơn vị: N.m).", bold_prefix="• ")
add_body("F_banh: Lực đẩy mỗi bánh (F_banh = 0.521 N).", bold_prefix="• ")
add_body("R: Bán kính bánh xe (R = 0.0366 m).", bold_prefix="• ")
add_body("eta: Hiệu suất truyền động cơ khí hộp số (chọn eta = 0.85).", bold_prefix="• ")
add_body("Thay số:")
add_eq(r"T_{banh} = \dfrac{0.521 \cdot 0.0366}{0.85} = 0.0224\text{ N}\cdot\text{m} = 0.228\text{ kg}\cdot\text{cm}")
add_body("Áp dụng hệ số an toàn dự trữ công suất k_m = 1.5:")
add_eq(r"T_{chon} \ge T_{banh} \cdot 1.5 = 0.228 \cdot 1.5 = 0.342\text{ kg}\cdot\text{cm}")

# =========================================================================
# MỤC 4: ĐỐI CHIẾU THỰC TẾ ĐỘNG CƠ 280 RPM
# =========================================================================
add_h1("4. ĐỐI CHIẾU THỰC TẾ: TỐC ĐỘ YÊU CẦU VÀ ĐỘNG CƠ 280 RPM ĐÃ MUA")
add_h2("4.1. Tốc độ vòng quay lý thuyết cần thiết (n_yeucau)")
add_body("Trong không gian phòng thí nghiệm hoặc nhà xưởng, tốc độ di chuyển an toàn và tối ưu của xe là v = 0.50 m/s (tương đương 1.8 km/h).")
add_body("Công thức tính tốc độ vòng quay yêu cầu của bánh xe:")
add_eq(r"n_{yeucau} = \dfrac{60 \cdot v}{C} = \dfrac{60 \cdot 0.50}{0.23} \approx 130.4\text{ RPM} \approx 130 - 140\text{ RPM}")
add_body("Như vậy về mặt lý thuyết, xe chỉ cần động cơ có tốc độ sau giảm tốc khoảng 130 đến 140 RPM.")

add_h2("4.2. Thực tế sử dụng động cơ GA25-370 280 RPM và giải pháp điều khiển PWM")
add_body("Thực tế đã mua bộ động cơ GA25-370 12V 280 RPM (n_thucte = 280 RPM). Khi mở hết 100% công suất, xe chạy đạt v_max = 1.07 m/s (gần 3.9 km/h, quá nhanh trong nhà).")
add_body("Giải pháp lập trình điều khiển:")
add_eq(r"\text{Tỷ lệ PWM} = \dfrac{n_{yeucau}}{n_{thucte}} = \dfrac{130}{280} \approx 46.4\% \implies \text{Cài đặt PWM từ 45\% đến 50\%}")
add_body("Trên thang điều khiển 8-bit (0 đến 255): PWM = 120 đến 130.")
add_body("Lợi ích thực tế: Động cơ chạy cực mát, tăng tuổi thọ chổi than. 50% dải công suất còn lại đóng vai trò dự trữ mô-men xoắn giúp xe tự động tăng ga vượt dốc, leo gờ cửa hoặc khi bánh caster bị kẹt góc xoay mà không bị sụt áp.")

# =========================================================================
# MỤC 5: ĐỘNG HỌC THUẬN VÀ ĐỘNG HỌC NGHỊCH (KINEMATICS)
# =========================================================================
add_h1("5. MÔ HÌNH HÓA ĐỘNG HỌC XE DI ĐỘNG VI SAI (DIFFERENTIAL DRIVE KINEMATICS)")
add_body("Xe sử dụng cơ cấu vi sai 2 bánh chủ động phía sau với bán kính bánh xe R = 0.0366 m và khoảng cách giữa hai bánh xe L = 0.1875 m. Xe di chuyển trên mặt phẳng tọa độ toàn cục Oxy với góc hướng thân xe là theta.")

add_h2("5.1. Mô hình Động học thuận (Forward Kinematics)")
add_body("Động học thuận là bài toán xác định vận tốc dài tịnh tiến v(t) và vận tốc góc xoay omega(t) của toàn xe dựa trên vận tốc góc quay tức thời của bánh phải (omega_R) và bánh trái (omega_L) đo được từ Encoder:")
add_eq(r"v = \dfrac{R \left(\omega_R + \omega_L\right)}{2}")
add_eq(r"\omega = \dfrac{R \left(\omega_R - \omega_L\right)}{L}")

add_body("Trong đó:")
add_body("v: Vận tốc dài tịnh tiến của tâm trục bánh sau (đơn vị: m/s).", bold_prefix="• ")
add_body("omega: Vận tốc góc tự xoay của thân xe quanh trục thẳng đứng (đơn vị: rad/s).", bold_prefix="• ")
add_body("omega_R: Vận tốc góc quay của bánh xe sau bên phải (đơn vị: rad/s).", bold_prefix="• ")
add_body("omega_L: Vận tốc góc quay của bánh xe sau bên trái (đơn vị: rad/s).", bold_prefix="• ")
add_body("R: Bán kính bánh xe (R = 0.0366 m).", bold_prefix="• ")
add_body("L: Khoảng cách giữa hai bánh xe sau (L = 0.1875 m).", bold_prefix="• ")

add_body("Biểu diễn đạo hàm vị trí của xe trong hệ tọa độ thế giới Oxy thông qua ma trận Jacobi chuyển đổi trạng thái:")
add_body("1. Quan hệ giữa vận tốc tọa độ toàn cục Oxy và vận tốc thân xe [v, omega]^T:")
add_eq(r"""\begin{bmatrix} \dot{x} \ \dot{y} \ \dot{\theta} \end{bmatrix} = \begin{bmatrix} \cos\theta & 0 \ \sin\theta & 0 \ 0 & 1 \end{bmatrix} \begin{bmatrix} v \ \omega \end{bmatrix}""")

add_body("2. Ma trận Jacobi chuyển đổi trực tiếp từ vận tốc góc hai bánh xe [omega_R, omega_L]^T sang vận tốc toàn cục:")
add_eq(r"""\begin{bmatrix} \dot{x} \ \dot{y} \ \dot{\theta} \end{bmatrix} = \begin{bmatrix} \dfrac{R}{2}\cos\theta & \dfrac{R}{2}\cos\theta \ \dfrac{R}{2}\sin\theta & \dfrac{R}{2}\sin\theta \ \dfrac{R}{L} & -\dfrac{R}{L} \end{bmatrix} \begin{bmatrix} \omega_R \ \omega_L \end{bmatrix}""")
add_h2("5.2. Mô hình Động học nghịch (Inverse Kinematics)")
add_body("Động học nghịch là bài toán quy đổi từ vận tốc dài mong muốn v(t) và vận tốc góc mong muốn omega(t) (do thuật toán dẫn đường hoặc bộ điều khiển phát ra) thành vận tốc góc cần đặt cho từng động cơ bánh phải (omega_R) và bánh trái (omega_L):")
add_eq(r"\begin{cases} v_R = v + \dfrac{\omega \cdot L}{2} \implies \omega_R = \dfrac{1}{R} \left( v + \dfrac{\omega \cdot L}{2} \right) \\[10pt] v_L = v - \dfrac{\omega \cdot L}{2} \implies \omega_L = \dfrac{1}{R} \left( v - \dfrac{\omega \cdot L}{2} \right) \end{cases}")

add_body("Trong đó:")
add_body("v_R, v_L: Vận tốc dài tiếp tuyến tương ứng của bánh phải và bánh trái (đơn vị: m/s).", bold_prefix="• ")
add_body("omega_R, omega_L: Vận tốc góc đặt cho động cơ bánh phải và bánh trái (đơn vị: rad/s).", bold_prefix="• ")
add_body("v: Vận tốc dài yêu cầu của xe (đơn vị: m/s).", bold_prefix="• ")
add_body("omega: Vận tốc góc yêu cầu của xe (đơn vị: rad/s).", bold_prefix="• ")

add_body("Chuyển đổi từ vận tốc góc omega (rad/s) sang tốc độ vòng quay n (vòng/phút - RPM) để nạp vào hàm điều khiển PWM:")
add_eq(r"n_R = \dfrac{60 \cdot \omega_R}{2\pi}, \quad n_L = \dfrac{60 \cdot \omega_L}{2\pi}")

# =========================================================================
# MỤC 6: TÍNH TOÁN ODOMETRY VÀ ENCODER
# =========================================================================
add_h1("6. TÍNH TOÁN THÔNG SỐ ENCODER VÀ GIẢI THUẬT ĐỊNH VỊ ODOMETRY")
add_body("Động cơ GA25 tích hợp Encoder Hall 2 kênh AB có 11 xung/vòng/kênh trên đĩa từ. Hộp số giảm tốc có tỷ số truyền K_gear = 21.3 : 1.")

add_h2("6.1. Tổng số xung trên 1 vòng quay bánh xe")
add_body("Số xung thực tế sau khi qua hộp số giảm tốc và giải mã 4 cạnh xung (chế độ x4 Quadrature Decoding):")
add_eq(r"N_{rev} = N_{dia} \cdot K_{gear} \cdot 4 = 11 \cdot 21.3 \cdot 4 = 937.2\text{ xung/vòng}")

add_h2("6.2. Độ phân giải quãng đường di chuyển của mỗi xung")
add_body("Cự ly xe lăn bánh tương ứng với 1 xung Encoder đọc được:")
add_eq(r"\Delta s_{pulse} = \dfrac{C}{N_{rev}} = \dfrac{0.23}{937.2} \approx 0.000245\text{ m} = 0.245\text{ mm/xung}")

add_h2("6.3. Giải thuật cập nhật tọa độ Odometry trong chu kỳ lấy mẫu dt")
add_body("Trong mỗi chu kỳ trích mẫu dt (chọn dt = 0.02s tương ứng 50 Hz), gọi delta_N_R và delta_N_L là số xung vi điều khiển đếm được từ bánh phải và bánh trái. Quãng đường dịch chuyển của từng bánh:")
add_eq(r"\Delta s_R = \Delta N_R \cdot \Delta s_{pulse}, \quad \Delta s_L = \Delta N_L \cdot \Delta s_{pulse}")

add_body("Quãng đường tịnh tiến của tâm xe và góc quay thân xe:")
add_eq(r"\Delta s = \dfrac{\Delta s_R + \Delta s_L}{2}, \quad \Delta\theta = \dfrac{\Delta s_R - \Delta s_L}{L} = \dfrac{\Delta s_R - \Delta s_L}{0.1875}")

add_body("Cập nhật tọa độ và góc hướng của xe theo phương pháp tích phân hình thang Runge-Kutta bậc 2:")
add_eq(r"\begin{cases} x_{k+1} = x_k + \Delta s \cdot \cos\left(\theta_k + \dfrac{\Delta\theta}{2}\right) \\[8pt] y_{k+1} = y_k + \Delta s \cdot \sin\left(\theta_k + \dfrac{\Delta\theta}{2}\right) \\[8pt] \theta_{k+1} = \theta_k + \Delta\theta \end{cases}")

# =========================================================================
# MỤC 7: NGUỒN PIN VÀ DRIVER
# =========================================================================
add_h1("7. TÍNH TOÁN NGUỒN ĐIỆN VÀ DRIVER ĐIỀU KHIỂN")
add_h2("7.1. Đánh giá Driver MKE-M18 BD62130 I2C")
add_body("Module MKE-M18 chịu điện áp 8.0V - 13.0VDC, dòng liên tục 3.0A/kênh (dòng đỉnh 4.0A). Động cơ GA25 chạy có tải chỉ ăn dòng 0.2A - 0.4A và dòng kẹt tải là 1.8A. Driver hoàn toàn dư tải an toàn.")
add_body("Lợi thế I2C: Module chỉ dùng 2 chân SDA/SCL (địa chỉ 0x40), tích hợp vi điều khiển ARM Cortex-M0+ tự băm xung PWM độc lập, giải phóng 100% chân GPIO ngắt ngoài trên vi điều khiển chính để đọc tín hiệu Encoder.")

add_h2("7.2. Tính toán thời gian hoạt động của khối Pin Waveshare UPS 3S")
add_body("Khối pin gồm 3 cell pin 18650 mắc nối tiếp (điện áp 11.1V - 12.6V, dung lượng 2600 mAh = 2.6 Ah).")
add_body("Tổng dòng tiêu thụ trung bình toàn xe:")
add_eq(r"I_{tb} = I_{2\_motor} + I_{mcu} + I_{sensor} = 0.35 + 0.15 + 0.30 = 0.80\text{ A}")
add_body("Thời gian hoạt động liên tục với độ xả sâu an toàn 80% (DoD = 0.8):")
add_eq(r"t_{hoat\_dong} = \dfrac{C_{pin} \cdot \text{DoD}}{I_{tb}} = \dfrac{2.6 \cdot 0.8}{0.80} = 2.6\text{ giờ (khoảng 2 tiếng 35 phút)}")

add_h2("7.3. Mạch giảm áp Buck XL4015 5A")
add_body("Module Buck XL4015 hạ áp từ nguồn 12V xuống 5.0VDC độc lập cung cấp dòng tải lên đến 5A cho cụm cảm biến và phụ kiện, tránh sụt áp gây reset vi điều khiển khi động cơ khởi động.")


# =========================================================================
# MỤC 8: TÍNH TOÁN CHU KỲ ĐIỀU KHIỂN, GIA TỐC VÀ CỰ LY PHANH AN TOÀN
# =========================================================================
add_h1("8. TÍNH TOÁN CHU KỲ ĐIỀU KHIỂN, GIA TỐC VÀ CỰ LY PHANH AN TOÀN")

add_h2("8.1. Tính toán chu kỳ lấy mẫu điều khiển (Sample Time dt)")
add_body("Khi xe chạy ở vận tốc danh định v = 0.50 m/s với độ phân giải xung delta_s = 0.245 mm/xung, tần số phát xung của mỗi bánh xe:")
add_eq(r"f_{pulse} = \dfrac{v}{\Delta s_{pulse}} = \dfrac{0.50}{0.000245} \approx 2040	ext{ xung/giây (khoảng 2.04 kHz)}")
add_body("Để bộ điều khiển vi điều khiển (Arduino/ESP32/STM32) đọc kịp số xung và tính toán PID mượt mà mà không bị quá tải CPU, chu kỳ lấy mẫu ngắt Timer được chọn:")
add_eq(r"\Delta t = 0.02	ext{ s (20 ms, tương ứng tần số lấy mẫu } f = 50	ext{ Hz)}")
add_body("Trong mỗi chu kỳ 20 ms, mỗi bánh xe quay được số xung là:")
add_eq(r"N_{sample} = f_{pulse} \cdot \Delta t = 2040 \cdot 0.02 \approx 40.8	ext{ xung/chu kỳ}")
add_body("Nhận xét: Mỗi chu kỳ có khoảng 40 xung, đủ dày để thuật toán tính toán vận tốc tức thời cực kỳ mịn và không bị nhiễu số liệu.")

add_h2("8.2. Tính toán gia tốc tăng tốc và quãng đường khởi động")
add_body("Để bánh xe cao su không bị trượt trên bề mặt sàn gạch hoặc gỗ khi bắt đầu lăn bánh, gia tốc tăng tốc cực đại được giới hạn:")
add_eq(r"a_{\max} = 0.30	ext{ m/s}^2")
add_body("Thời gian xe cần để tăng tốc từ vị trí đứng yên lên tốc độ định mức v = 0.50 m/s:")
add_eq(r"t_{tangtoc} = \dfrac{v}{a_{\max}} = \dfrac{0.50}{0.30} \approx 1.67	ext{ giây}")
add_body("Quãng đường xe di chuyển trong giai đoạn tăng tốc:")
add_eq(r"s_{tangtoc} = \dfrac{v^2}{2 \cdot a_{\max}} = \dfrac{0.50^2}{2 \cdot 0.30} \approx 0.417	ext{ m} = 41.7	ext{ cm}")

add_h2("8.3. Tính toán cự ly dừng phanh an toàn khi gặp vật cản")
add_body("Khi cảm biến (LiDAR 2D hoặc cảm biến siêu âm) phát hiện vật cản phía trước, khoảng cách an toàn tối thiểu cần thiết để xe dừng hẳn không va chạm gồm 3 thành phần:")
add_body("1. Quãng đường xe trôi do độ trễ xử lý cảm biến và vi điều khiển (t_tre = 0.05 s = 50 ms):", bold_prefix="• ")
add_eq(r"s_{troi} = v \cdot t_{tre} = 0.50 \cdot 0.05 = 0.025	ext{ m} = 2.5	ext{ cm}")
add_body("2. Quãng đường hãm phanh với gia tốc hãm an toàn a_phanh = 0.50 m/s²:", bold_prefix="• ")
add_eq(r"s_{phanh} = \dfrac{v^2}{2 \cdot a_{phanh}} = \dfrac{0.50^2}{2 \cdot 0.50} = 0.250	ext{ m} = 25.0	ext{ cm}")
add_body("3. Khoảng đệm an toàn vật lý giữ khoảng cách với vật cản khi đã dừng hẳn: s_dem = 0.10 m (10 cm).", bold_prefix="• ")
add_body("Tổng cự ly an toàn bắt buộc phải cài đặt trong code cảm biến:")
add_eq(r"S_{dung} = s_{troi} + s_{phanh} + s_{dem} = 0.025 + 0.250 + 0.100 = 0.375	ext{ m} = 37.5	ext{ cm}")
add_body("Khuyến nghị lập trình: Cài đặt ngưỡng cảnh báo và kích hoạt phanh dừng khi vật cản xuất hiện ở cự ly nhỏ hơn hoặc bằng 38 - 40 cm.")

# =========================================================================
# MỤC 9: BỘ ĐIỀU KHIỂN PID VẬN TỐC VÀ QUY TRÌNH HIỆU CHUẨN THỰC TẾ
# =========================================================================
add_h1("9. BỘ ĐIỀU KHIỂN PID VẬN TỐC VÀ QUY TRÌNH HIỆU CHUẨN THỰC TẾ")

add_h2("9.1. Cấu trúc bộ điều khiển PID vận tốc vòng kín")
add_body("Bộ điều khiển PID vận tốc nhận giá trị sai lệch giữa vận tốc yêu cầu (v_setpoint) và vận tốc thực tế phản hồi từ Encoder (v_feedback) để tính toán giá trị PWM xuất ra module I2C MKE-M18:")
add_eq(r"e(t) = v_{setpoint}(t) - v_{feedback}(t)")
add_eq(r"u_{PWM}(t) = K_p \cdot e(t) + K_i \int_0^t e(	au) d	au + K_d \dfrac{de(t)}{dt}")
add_body("Trong đó:")
add_body("K_p: Hệ số tỉ lệ (Proportional Gain), tạo lực kéo nhanh chóng theo độ lệch tức thời.", bold_prefix="• ")
add_body("K_i: Hệ số tích phân (Integral Gain), triệt tiêu hoàn toàn sai số xác lập khi xe chạy đường dài hoặc leo dốc nhẹ.", bold_prefix="• ")
add_body("K_d: Hệ số vi phân (Derivative Gain), giảm thiểu hiện tượng vọt lố và dập tắt dao động rung lắc khi đổi tốc độ đột ngột.", bold_prefix="• ")
add_body("Dải thông số PID khởi điểm khuyến nghị cho xe 1.75 kg có quán tính nhỏ: K_p = 12.0 - 18.0; K_i = 1.5 - 2.5; K_d = 0.2 - 0.5; tần số lấy mẫu chu kỳ dt = 0.02 s.")

add_h2("9.2. Quy trình hiệu chuẩn thực tế bắt buộc (Calibration Procedure)")
add_body("Do lốp cao su có độ đàn hồi lún nhẹ dưới trọng lượng xe và khoảng cách trục L có thể lệch một vài milimet khi gia công gá bắt động cơ, cần thực hiện 2 bước hiệu chuẩn thực tế trên sàn:")

add_body("Bước 1: Hiệu chuẩn cự ly chạy thẳng (Hiệu chỉnh bán kính bánh xe R)")
add_body("1. Đặt xe tại vạch mốc số 0 trên mặt sàn, ra lệnh cho xe chạy thẳng đúng 1.0 m (1000 mm) theo số xung lý thuyết (4075 xung).", bold_prefix="• ")
add_body("2. Dùng thước cuộn đo quãng đường thực tế xe lăn bánh (gọi là S_thuc, ví dụ đạt 9187.5 mm).", bold_prefix="• ")
add_body("3. Tính hệ số bù cự ly và cập nhật lại bán kính thực tế trong code:", bold_prefix="• ")
add_eq(r"R_{hieu\_chinh} = R_{ly\_thuyet} \cdot \dfrac{S_{thuc}}{S_{ly\_thuyet}} = 0.0366 \cdot \dfrac{985}{1000} \approx 0.0360	ext{ m}")

add_body("Bước 2: Hiệu chuẩn góc quay tại chỗ 360 độ (Hiệu chỉnh khoảng cách trục L)")
add_body("1. Đặt xe trên sàn, đánh dấu hướng ban đầu của đầu xe bằng tia laser hoặc vạch phấn.", bold_prefix="• ")
add_body("2. Ra lệnh cho xe tự xoay tròn tại chỗ đúng 10 vòng (3600 độ hay 20*pi rad) theo công thức góc d_theta = (s_R - s_L)/L.", bold_prefix="• ")
add_body("3. Quan sát vị trí dừng của đầu xe sau khi đủ 10 vòng:", bold_prefix="• ")
add_body("Nếu xe quay chưa đủ 10 vòng (bị thiếu góc): Thông số L trong code đang nhỏ hơn thực tế, cần tăng giá trị L (ví dụ từ 187.5 mm lên 86 mm).", indent=0.25)
add_body("Nếu xe quay lố qua 10 vòng (bị dư góc): Thông số L trong code đang lớn hơn thực tế, cần giảm giá trị L (ví dụ từ 187.5 mm xuống 84 mm).", indent=0.25)
add_body("4. Lặp lại 2-3 lần cho đến khi đầu xe dừng chuẩn xác 100% tại hướng xuất phát ban đầu. Khi đó sai số tích lũy góc của thuật toán Odometry được triệt tiêu hoàn toàn.")

doc.save(out_docx)
print("Updated successfully to single file with full Kinematics:", out_docx)
