# -*- coding: utf-8 -*-
"""
Tự động biên soạn tài liệu tính toán thiết kế xe tự hành AGV (3kg, bánh chu vi 23cm, động cơ 280 RPM)
vào thư mục: D:\\HoMinhKhang\\PROJECT\\GITHUB_PROJECT\\CODE XE TU HANH
Chuẩn 100% Microsoft Word Equation native (OMML).
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

# Canh lề chuẩn: Trên 2cm, Dưới 2cm, Trái 2.5cm, Phải 2cm
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
    format_p(p, 1.15, 4, 4, WD_ALIGN_PARAGRAPH.CENTER)
    p._p.append(parse_xml(f'<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">{ostr}</m:oMathPara>'))

# TIÊU ĐỀ TÀI LIỆU
add_title("BẢN TÍNH TOÁN THIẾT KẾ ĐỘNG LỰC HỌC VÀ CHỌN ĐỘNG CƠ XE TỰ HÀNH (AGV)")
add_subtitle("CẤU HÌNH XE 3 BÁNH (1 CASTER TRƯỚC + 2 DẪN ĐỘNG SAU), KHỐI LƯỢNG 3.0 KG")

# PHẦN 1
add_h1("1. THÔNG SỐ CẤU HÌNH VÀ TỔNG TẢI TRỌNG THIẾT KẾ")
add_body("Hệ thống xe tự hành di chuyển trong nhà xưởng/phòng thí nghiệm trên mặt phẳng nằm ngang, không chở thêm tải trọng ngoài. Cấu hình cơ khí gồm 1 bánh tự lựa (caster) dẫn hướng phía trước và 2 bánh chủ động dẫn động độc lập phía sau.")

add_h2("1.1. Công thức tính tổng khối lượng có hệ số an toàn")
add_body("Tổng khối lượng thiết kế là khối lượng toàn bộ xe dùng để tính toán động lực học, bao gồm khối lượng ước lượng thực tế nhân với hệ số dự phòng an toàn kỹ thuật nhằm bù trừ sai số dây dẫn, ốc vít, ke góc cơ khí và thiết bị phát sinh:")
add_eq(r"M = m_{thuc} \cdot k_s")
add_body("Trong đó:")
add_body("M: Tổng khối lượng tính toán của xe (đơn vị: kg).", bold_prefix="• ")
add_body("m_thuc: Khối lượng thực tế của xe ước tính ban đầu (m_thuc = 3.0 kg).", bold_prefix="• ")
add_body("k_s: Hệ số an toàn thiết kế (chọn k_s = 1.2, tương ứng dư tải 20%).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"M = 3.0 \cdot 1.2 = 3.6\text{ kg}")

add_h2("1.2. Công thức tính trọng lực toàn xe")
add_body("Trọng lực là lực hút của Trái Đất tác dụng lên toàn bộ khối lượng của xe theo phương thẳng đứng hướng xuống mặt sàn:")
add_eq(r"P = M \cdot g")
add_body("Trong đó:")
add_body("P: Trọng lực toàn phần của xe (đơn vị: N).", bold_prefix="• ")
add_body("M: Tổng khối lượng tính toán (M = 3.6 kg).", bold_prefix="• ")
add_body("g: Gia tốc trọng trường (lấy chuẩn g = 9.81 m/s²).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"P = 3.6 \cdot 9.81 = 35.316\text{ N}")

add_h2("1.3. Phân bổ tải trọng lên các cụm bánh xe")
add_body("Để đảm bảo 2 bánh dẫn động phía sau có đủ lực bám ma sát với mặt sàn, không bị trượt quay tại chỗ khi tăng tốc hoặc hãm phanh, đồng thời bánh caster phía trước đủ nhẹ để chuyển hướng linh hoạt, tải trọng được phân bổ theo tỷ lệ 70% dồn vào 2 bánh sau và 30% dồn vào bánh trước:")

add_body("1. Trọng lực đè lên 2 bánh dẫn động phía sau:")
add_eq(r"P_{sau} = 0.70 \cdot P = 0.70 \cdot 35.316 = 24.72\text{ N}")
add_body("Mỗi bánh dẫn động sau chịu một nửa tải:")
add_eq(r"P_{banh\_sau} = \dfrac{P_{sau}}{2} = \dfrac{24.72}{2} = 12.36\text{ N}")

add_body("2. Trọng lực đè lên 1 bánh caster dẫn hướng phía trước:")
add_eq(r"P_{caster} = 0.30 \cdot P = 0.30 \cdot 35.316 = 10.60\text{ N}")

# PHẦN 2
add_h1("2. TÍNH TOÁN KÍCH THƯỚC HÌNH HỌC BÁNH XE")
add_body("Bánh xe dẫn động thực tế được đo chu vi vòng tròn ngoài cùng bằng thước dây đạt C = 23 cm (0.23 m).")

add_h2("2.1. Công thức tính đường kính bánh xe")
add_body("Đường kính bánh xe là chiều dài đoạn thẳng đi qua tâm và nối hai điểm đối diện trên đường tròn viền bánh xe:")
add_eq(r"D = \dfrac{C}{\pi}")
add_body("Trong đó:")
add_body("D: Đường kính bánh xe (đơn vị: m).", bold_prefix="• ")
add_body("C: Chu vi vòng tròn bánh xe đo được (C = 0.23 m).", bold_prefix="• ")
add_body("pi: Hằng số Pi (lấy xấp xỉ 3.1416).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"D = \dfrac{0.23}{3.1416} \approx 0.0732\text{ m} = 73.2\text{ mm}")

add_h2("2.2. Công thức tính bán kính bánh xe")
add_body("Bán kính bánh xe là khoảng cách từ trục quay tâm bánh xe đến mép ngoài tiếp xúc với mặt sàn:")
add_eq(r"R = \dfrac{D}{2}")
add_body("Trong đó:")
add_body("R: Bán kính bánh xe (đơn vị: m).", bold_prefix="• ")
add_body("D: Đường kính bánh xe (D = 0.0732 m).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"R = \dfrac{0.0732}{2} = 0.0366\text{ m} = 36.6\text{ mm}")

# PHẦN 3
add_h1("3. TÍNH TOÁN CÁC THÀNH PHẦN LỰC CẢN CHUYỂN ĐỘNG")
add_body("Khi xe tự hành di chuyển trên mặt sàn phẳng ngang trong nhà xưởng, động cơ phải sản sinh lực đẩy để thắng hai thành phần lực cản cơ bản: lực cản lăn và lực cản quán tính khi tăng tốc.")

add_h2("3.1. Công thức tính lực cản lăn")
add_body("Lực cản lăn là lực ma sát xuất hiện do sự biến dạng tiếp xúc giữa lốp cao su của bánh xe và bề mặt sàn cứng khi bánh xe lăn đều:")
add_eq(r"F_{lan} = \mu \cdot P = \mu \cdot M \cdot g")
add_body("Trong đó:")
add_body("F_lan: Lực cản lăn của toàn xe (đơn vị: N).", bold_prefix="• ")
add_body("mu: Hệ số cản lăn giữa bánh cao su và mặt sàn phẳng cứng (chọn chuẩn mu = 0.02).", bold_prefix="• ")
add_body("M: Tổng khối lượng tính toán của xe (M = 3.6 kg).", bold_prefix="• ")
add_body("g: Gia tốc trọng trường (g = 9.81 m/s²).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"F_{lan} = 0.02 \cdot 3.6 \cdot 9.81 = 0.706\text{ N}")

add_h2("3.2. Công thức tính lực cản quán tính khi tăng tốc")
add_body("Lực cản quán tính là lực cản trở sự biến đổi trạng thái chuyển động của xe khi xe tăng tốc từ vị trí đứng yên lên tốc độ làm việc theo Định luật II Newton:")
add_eq(r"F_{qt} = M \cdot a")
add_body("Trong đó:")
add_body("F_qt: Lực quán tính khi tăng tốc (đơn vị: N).", bold_prefix="• ")
add_body("M: Tổng khối lượng tính toán (M = 3.6 kg).", bold_prefix="• ")
add_body("a: Gia tốc tăng tốc mong muốn của xe (chọn a = 0.3 m/s² để xe khởi động êm mượt, không giật trượt).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"F_{qt} = 3.6 \cdot 0.3 = 1.080\text{ N}")

add_h2("3.3. Công thức tính tổng lực kéo yêu cầu")
add_body("Tổng lực kéo yêu cầu là tổng hợp lực nhỏ nhất mà hệ thống động cơ cần tạo ra tại thời điểm xe bắt đầu tăng tốc chuyển động:")
add_eq(r"F_{keo} = F_{lan} + F_{qt}")
add_body("Trong đó:")
add_body("F_keo: Tổng lực kéo toàn xe (đơn vị: N).", bold_prefix="• ")
add_body("F_lan: Lực cản lăn (F_lan = 0.706 N).", bold_prefix="• ")
add_body("F_qt: Lực quán tính khi tăng tốc (F_qt = 1.080 N).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"F_{keo} = 0.706 + 1.080 = 1.786\text{ N}")

add_body("Do xe sử dụng 2 động cơ dẫn động độc lập chia tải đều nhau, lực đẩy yêu cầu trên mỗi bánh xe sau:")
add_eq(r"F_{banh} = \dfrac{F_{keo}}{2} = \dfrac{1.786}{2} = 0.893\text{ N} \approx 0.90\text{ N}")

# PHẦN 4
add_h1("4. TÍNH TOÁN MÔ-MEN XOẮN VÀ KIỂM TRA ĐỘNG CƠ 280 RPM")

add_h2("4.1. Công thức tính mô-men xoắn cần thiết trên trục bánh xe")
add_body("Mô-men xoắn là đại lượng đặc trưng cho tác dụng làm quay của lực quanh trục bánh xe, được tính bằng tích số giữa lực đẩy tiếp tuyến tại mép bánh với bán kính bánh xe và chia cho hiệu suất truyền động:")
add_eq(r"T_{banh} = \dfrac{F_{banh} \cdot R}{\eta}")
add_body("Trong đó:")
add_body("T_banh: Mô-men xoắn cần thiết trên trục bánh xe (đơn vị: N.m).", bold_prefix="• ")
add_body("F_banh: Lực đẩy yêu cầu cho một bánh xe (F_banh = 0.893 N).", bold_prefix="• ")
add_body("R: Bán kính bánh xe (R = 0.0366 m).", bold_prefix="• ")
add_body("eta: Hiệu suất truyền động cơ khí và hộp số giảm tốc (chọn eta = 0.85).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"T_{banh} = \dfrac{0.893 \cdot 0.0366}{0.85} = 0.0384\text{ N}\cdot\text{m}")

add_body("Quy đổi sang đơn vị mô-men thông dụng trên thị trường (kg.cm):")
add_eq(r"T_{banh} = 0.0384 \cdot 10.197 \approx 0.392\text{ kg}\cdot\text{cm}")

add_body("Để động cơ hoạt động bền bỉ, không bị quá nhiệt khi chạy liên tục, áp dụng hệ số dự trữ công suất k_m = 1.5:")
add_eq(r"T_{chon} \ge T_{banh} \cdot 1.5 = 0.392 \cdot 1.5 = 0.588\text{ kg}\cdot\text{cm} \approx 0.60\text{ kg}\cdot\text{cm}")

add_h2("4.2. Đánh giá và kiểm tra thông số động cơ 280 RPM đã mua")
add_body("Thực tế đã mua 2 động cơ DC giảm tốc có tốc độ danh định sau hộp số là n = 280 vòng/phút (RPM).")

add_body("1. Công thức tính vận tốc di chuyển cực đại của xe (khi mở hết ga 100% PWM):")
add_body("Vận tốc cực đại là quãng đường xe đi được trong 1 giây ứng với số vòng quay tối đa của bánh xe:")
add_eq(r"v_{\max} = \dfrac{n \cdot C}{60}")
add_body("Trong đó:")
add_body("v_max: Vận tốc di chuyển cực đại của xe (đơn vị: m/s).", bold_prefix="• ")
add_body("n: Tốc độ vòng quay của trục bánh xe (n = 280 vòng/phút).", bold_prefix="• ")
add_body("C: Chu vi bánh xe (C = 0.23 m).", bold_prefix="• ")
add_body("Thay số vào công thức:")
add_eq(r"v_{\max} = \dfrac{280 \cdot 0.23}{60} \approx 1.073\text{ m/s} = 3.86\text{ km/h}")

add_body("2. Đánh giá khả năng đáp ứng mô-men xoắn:")
add_body("Các dòng động cơ DC giảm tốc phổ thông loại 280 RPM (như GA25-370 hoặc JGB37-520) có mô-men xoắn định mức đạt từ 1.2 kg.cm đến 2.5 kg.cm. Giá trị này lớn hơn rất nhiều so với mô-men xoắn yêu cầu tính toán (T_chon >= 0.60 kg.cm). Do đó động cơ thừa lực kéo, khởi động khỏe và đảm bảo xe tăng tốc nhanh mượt.")

# PHẦN 5
add_h1("5. KHUYẾN NGHỊ ĐIỀU KHIỂN VẬN HÀNH TRÊN MÃ NGUỒN")
add_body("1. Khống chế dải vận tốc qua PWM: Trong không gian phòng thí nghiệm hoặc nhà xưởng, tốc độ làm việc tối ưu của xe là v = 0.40 - 0.55 m/s (tương ứng 105 - 145 RPM). Khi lập trình vi điều khiển (Arduino/STM32/ESP32), khống chế độ rộng xung PWM tối đa ở mức 40% - 55% chu kỳ (tương ứng giá trị PWM = 100 - 140 trên thang 8-bit 255).")
add_body("2. Dự trữ công suất vượt chướng ngại: Dải công suất còn lại (45% - 100% PWM) được giữ làm dự phòng để xe vượt gờ sàn, leo thảm hoặc bù lực khi bánh xe caster bị kẹt góc xoay.")

doc.save(out_docx)
print("File generated successfully at:", out_docx)
