# Báo cáo quan sát AGV chạm tường và không tự thoát

- Ngày: 08/10/2026; mốc giờ bên dưới theo UTC+7.
- Nguồn: giao diện AGV Mission Control tại http://100.90.252.15:8080/ và phản hồi trực tiếp của người vận hành.
- Phạm vi: quan sát trong phiên chạy, với các mẫu có ghi giờ từ 14:19:13 đến 14:20:28 và một số mẫu trước đó. Không bấm nút điều khiển, không gửi lệnh, không đổi tham số, không sửa chương trình robot.
- Phương pháp: đọc từng mẫu giao diện và xem radar. Không có video liên tục, camera hiện trường, log điều khiển hoặc kiểm tra mã nguồn trong phiên đánh giá này.

## 1. Kết luận

**Chưa đạt yêu cầu tránh va chạm và tự thoát kẹt trong phiên thử này.** Người vận hành xác nhận xe chạm tường, không tự né và cần xoay xe bằng tay; sau đó tiếp tục báo hiện tượng tương tự tái diễn.

Giao diện đã hiển thị vật cản gần khoảng 14–18 cm, có điểm vùng đỏ trên radar và từng xuất hiện cảnh báo “QUÁ GẦN!”. Vì vậy, bằng chứng hiện có cho thấy **có dữ liệu vật cản gần trên giao diện nhưng hành vi né/thoát kẹt thực tế chưa hiệu quả**. Chưa thể kết luận bộ điều khiển tự hành nhận và sử dụng đúng chính dữ liệu đó.

Đáng chú ý, thông báo `STOP_UNCONFIRMED` xuất hiện nhiều lần đồng thời với RPM khác 0. Đây là điểm cần đối chiếu giữa trạng thái giao diện, lệnh điều khiển và phản hồi động cơ; riêng thông báo này chưa chứng minh được nguyên nhân va chạm.

## 2. Diễn biến và bằng chứng

Các giá trị là số hiển thị tại thời điểm lấy mẫu, không phải bản ghi liên tục. T/P là bánh trái/phải theo nhãn giao diện; góc vật cản giữ nguyên quy ước của giao diện, chưa xác minh trục góc.

| Mốc giờ | Vật cản gần nhất | RPM T / P | Ghi nhận |
|---|---|---|---|
| Trước 14:19:13 | Lần lượt thấy 73 cm, 22 cm rồi 16 cm | Thay đổi qua các mẫu | Khoảng cách hiển thị giảm; xuất hiện `STOP_UNCONFIRMED`. |
| 14:19:13 | 16 cm, 5° | 32,0 / 0,0 | Một bánh hiển thị quay, bánh còn lại bằng 0; chưa thấy khoảng cách tăng khỏi vùng sát vật cản. |
| 14:19:22 | 16 cm, 4° | 39,7 / 1,3 | Người vận hành xác nhận: “xe bị chạm tường mà nó không biết tự né”. Radar có cụm điểm đỏ gần biểu tượng xe. |
| Sau xác nhận chạm tường | — | — | Người vận hành thông báo sẽ xoay xe ra chỗ khác. Đánh dấu là can thiệp bằng tay; chưa biết chính xác thời điểm bắt đầu/kết thúc thao tác. |
| 14:19:43 | 52 cm, 275° | 30,7 / 33,3 | Sau thông báo can thiệp, khoảng cách tăng và RPM hai bánh gần nhau hơn. Không tính đoạn này là xe tự thoát thành công. |
| 14:19:59 | 18 cm, 30° | 26,9 / 10,2 | Giao diện báo “CẢNH BÁO: QUÁ GẦN!”, trạng thái nút arm hiển thị “ĐÃ SẴN SÀNG”. |
| 14:20:16 | 18 cm, 2° | 30,7 / 14,1 | `STOP_UNCONFIRMED` xuất hiện lại, RPM vẫn khác 0. Ảnh chụp ngay sau đó ghi bánh phải 19,2 RPM, thể hiện số liệu tiếp tục thay đổi giữa hai lần đọc. |
| Trước mẫu cuối | — | — | Người vận hành báo: “lại nữa nó biết là vùng đỏ rồi mà nó không tự né”. Đây là xác nhận hiện tượng tái diễn, chưa có xác nhận vị trí tiếp xúc lần hai. |
| 14:20:28 | 14 cm, 328° | 0,0 / 0,0 | Mẫu cuối cho thấy cả hai RPM bằng 0, vẫn có `STOP_UNCONFIRMED`. Chưa xác định xe tự dừng, người vận hành dừng hay nguyên nhân khác. |

## 3. Đánh giá theo từng vấn đề

### 3.1. Hiển thị vật cản và hiệu quả né tránh

Radar và nhãn khoảng cách có phản ánh vật cản gần. Tuy nhiên, xác nhận chạm tường của người vận hành cho thấy việc hiển thị/cảnh báo chưa chuyển thành khả năng tránh va chạm hiệu quả trong tình huống này.

**Không đồng nhất “vùng đỏ” với “thuật toán đã quyết định né”.** Màu hiển thị chỉ là bằng chứng ở giao diện; cần log để biết nhánh điều khiển nào thực sự đang chạy. Nút tự động vẫn hiện “BẬT TỰ ĐỘNG QUÉT MAP” trong các mẫu đã xem, nên giao diện này cũng chưa đủ để xác nhận trạng thái AUTO thực tế ở bộ điều khiển.

### 3.2. Chênh lệch RPM khi sát tường

Ở đoạn được xác nhận chạm tường, RPM trái/phải lệch mạnh: 32,0/0,0 rồi 39,7/1,3. Mẫu này phù hợp với khả năng xe đang cố đổi hướng hoặc một bên chuyển động bị hạn chế, nhưng **không đủ để phân biệt lệnh né chủ động, bánh bị cản, trượt bánh hay lỗi phản hồi**.

Trong các mẫu đã đọc, chưa ghi nhận được bằng chứng rõ ràng của một chuỗi tự thoát thành công. Không khẳng định chương trình hoàn toàn không có chức năng lùi hoặc thoát kẹt, vì các khoảng giữa hai mẫu không được ghi liên tục.

### 3.3. Can thiệp bằng tay

Khoảng cách tăng lên 52 cm sau khi người vận hành thông báo xoay xe. Do có can thiệp, kết quả này không được dùng để chấm khả năng tự phục hồi. Việc người vận hành tiếp tục báo lỗi sau đó cho thấy vấn đề chưa được giải quyết chỉ bằng việc đổi hướng xe một lần.

### 3.4. Trạng thái lỗi và chuyển động cần được đối chiếu

`STOP_UNCONFIRMED` cùng RPM khác 0 là dấu hiệu cần ưu tiên kiểm tra. Chưa biết trạng thái lỗi có đồng bộ với dữ liệu RPM hay không, RPM là giá trị đo hay giá trị khác do ứng dụng đưa lên, và lệnh nào đang nắm quyền điều khiển. Không quy lỗi ngay cho MCU, đường truyền hoặc nút dừng chỉ từ màn hình.

## 4. Các giả thuyết cần kiểm chứng

Đây là các hướng kiểm tra, **chưa phải nguyên nhân đã xác nhận**:

1. **Khoảng hở thân xe chưa được xét đúng:** khoảng cách trên radar có thể chưa quy đổi thành khoảng hở từ mép xe đến tường. Cần đo vị trí lắp LiDAR, kích thước thân xe và khoảng quét của thân khi quay. Không thể lấy số 16 cm trên màn hình làm khoảng hở thực tế của đầu xe.
2. **Phản ứng khi vật cản quá gần chưa đủ hiệu quả:** cần xem xe đang tiếp tục tiến, quay theo cung, quay tại chỗ hay chuyển sang thoát kẹt; đối chiếu lệnh và chuyển động thực tế.
3. **Chưa phát hiện được tình trạng có chuyển động bánh nhưng không thoát:** cần đối chiếu RPM với mức thay đổi khoảng cách và chuyển động thực tế. Tọa độ X/Y thay đổi trên giao diện chưa tự chứng minh thân xe đã thoát nếu nguồn vị trí chưa được xác minh.
4. **Trạng thái điều khiển hoặc xác nhận dừng không nhất quán:** cần xác minh nguồn phát lệnh đang hoạt động, trạng thái AUTO/MANUAL/FAULT, thời điểm lệnh dừng và phản hồi tương ứng.
5. **Dữ liệu dùng cho né tránh khác dữ liệu hiển thị:** kiểm tra tuổi dữ liệu, hệ tọa độ, vùng góc xét vật cản và cách bộ điều khiển nhận dữ liệu radar.

## 5. Đề xuất kiểm tra ở bước tiếp theo

Chưa thực hiện thay đổi nào theo các đề xuất này.

- Đồng bộ video hiện trường với log: thời gian, khoảng cách theo hướng, trạng thái điều khiển, lệnh tốc độ từng bánh, RPM phản hồi, lệnh dừng/xác nhận dừng và thời điểm can thiệp tay.
- Kiểm tra sự kiện `STOP_UNCONFIRMED` cùng thời điểm RPM khác 0 để xác định dữ liệu có cùng thời điểm và cùng nguồn điều khiển hay không.
- Đo hình học thân xe–LiDAR rồi xác định ngưỡng giảm tốc, dừng và khoảng hở khi quay dựa trên số đo; chưa đề xuất một ngưỡng cm cố định từ phiên quan sát này.
- Kiểm tra riêng các tình huống tiếp cận tường thẳng, tường chéo, góc tường và cột. Phiên này chưa có xác nhận xe kẹt cột nên chưa đánh giá riêng tình huống đó.
- Đánh giá chức năng thoát kẹt bằng mức tăng khoảng hở và chuyển động thực tế; ghi riêng mọi lần người vận hành chạm/xoay xe.

## 6. Tiêu chí đánh giá lại

- Xe phát hiện vùng có nguy cơ va chạm và phản ứng trước khi thân xe tiếp xúc vật cản.
- Khi không đi tiếp được, xe thoát theo hướng còn khoảng trống hoặc dừng có kiểm soát, không duy trì hành vi tì vào tường.
- Không tính bất kỳ lần can thiệp tay nào là xe tự né/tự thoát thành công.
- Lệnh, trạng thái lỗi, phản hồi RPM và hình ảnh thực tế đối chiếu được theo thời gian.
- Ghi số lần thử, va chạm, tự thoát và can thiệp tay; dữ liệu hiện tại chưa đủ để tính tỷ lệ thành công hoặc thời gian phản ứng.

**Kết luận cuối phiên:** đã có một lần chạm tường được người vận hành xác nhận, một thông báo can thiệp xoay xe bằng tay và một phản ánh lỗi né tránh tái diễn. Giao diện có tín hiệu vật cản gần, nhưng chưa có bằng chứng xe tự né hoặc tự thoát thành công trong những đoạn được báo lỗi. Cần kiểm tra chuỗi nhận vật cản → quyết định điều khiển → phản hồi động cơ để xác định nguyên nhân.

## 7. Bổ sung sau khi đọc mã nguồn trên máy — các điểm cụ thể

Phần này được bổ sung theo yêu cầu làm rõ của người vận hành. Chỉ đọc mã nguồn trong workspace, không sửa chương trình, không chạy robot hoặc yêu cầu người vận hành tái hiện lần nữa. Các phần 1–6 ghi lại bằng chứng quan sát ban đầu; phần này bổ sung bằng chứng từ code. Chưa xác minh bản đang chạy trên robot trùng với bản trong workspace.

### A. Báo đỏ và kích hoạt thoát kẹt dùng hai điều kiện khác nhau

- `agv_unified_brain.py:467`: khoảng cách nhỏ nhất <= 0,35 m gán nhãn `DANGER_STOP`. Đoạn gán nhãn này không trực tiếp phát lệnh STOP hoặc gọi thoát kẹt.
- `agv_unified_brain.py:483`: dữ liệu phía trước đồng thời cập nhật `scan_clear`, dùng để chặn lệnh tiến tự hành thông thường tại tầng gửi lệnh. Vì vậy không được kết luận radar chỉ dùng để trang trí.
- `agv_unified_brain.py:995`: nhánh gọi `_try_escape()` lại phụ thuộc ô hiện tại trên bản đồ không đi được hoặc vùng thân xe trên bản đồ không đủ trống, sau nhánh kiểm tra không tiến triển và nhánh chuyển sang đi chậm.

**Điểm cụ thể:** màn hình báo đỏ do khoảng cách LiDAR không đồng nghĩa nhánh thoát kẹt được gọi. Có khả năng lệnh tiến bị chặn trong khi điều kiện chuyển sang thoát kẹt theo bản đồ chưa thỏa. Đây là sự khác biệt đã thấy trong code; chưa khẳng định đó là đường thực thi của lần va chạm vừa rồi.

### B. Chế độ operator bỏ chặn lỗi tại tầng gửi lệnh và tự ghép ARM

- `agv_command_session.py:436`: khi `strict_preflight=False`, hàm gửi lệnh đặt `armed=True`, `latched=False`.
- `agv_command_session.py:446`: điều kiện chặn vì `FAULT` chỉ có hiệu lực khi `strict_preflight=True`.
- `agv_command_session.py:441`: với lệnh không tự hành trong chế độ này, danh sách chặn bị đặt rỗng.
- `agv_command_session.py:460`: lệnh được ghép thêm `ARM`; nếu telemetry MCU báo `FAULT`, còn ghép `CLEAR_FAULT` trước `ARM`.
- `agv_unified_brain.py:211` và các script `start_live_agv.sh:48`, `start_agv_system.sh:65`: tùy chọn `--operator-control` dẫn đến `strict_preflight=False`; hai script này có sử dụng tùy chọn đó.

**Điểm cụ thể:** trong chế độ này, có lỗi `STOP_UNCONFIRMED` không tự bảo đảm lệnh chạy tiếp theo bị chặn. Đây là cơ chế trong code có thể phù hợp với hiện tượng lỗi vẫn hiển thị trong khi RPM khác 0. Chưa xác nhận robot đang được khởi động bằng script nào.

### C. Nhận diện kẹt bánh có điều kiện hẹp và chờ hơn 4 giây

- `agv_unified_brain.py:973`: lấy trị tuyệt đối RPM thực tế và RPM mục tiêu từng bánh.
- `agv_unified_brain.py:977`: chỉ tích lũy thời gian khi ít nhất một bánh có mục tiêu >= 5 RPM nhưng RPM thực tế < 1,5.
- `agv_unified_brain.py:980`: phải kéo dài hơn 4 giây mới đánh dấu kẹt bánh.
- `agv_unified_brain.py:987`: khi phát hiện, đổi chỉ số hướng thoát, gọi `_hold()` rồi kết thúc lượt xử lý; không gọi `_try_escape()` ngay trong nhánh này.

**Điểm cụ thể:** bánh vẫn quay/trượt hoặc RPM vượt ngưỡng sẽ không được nhánh này coi là kẹt bánh. Những mẫu 32,0/0,0 và 39,7/1,3 chưa đủ khẳng định bộ phát hiện đã kích hoạt vì màn hình không cho RPM mục tiêu và thời gian duy trì liên tục. Nhánh kiểm tra tiến triển khác còn dựa vào biến đổi cả vị trí lẫn góc (`agv_unified_brain.py:996`).

### D. RPM trên màn hình đã bị bỏ dấu

`index_cyberpunk.html:628` và dòng kế tiếp dùng `Math.abs()` trước khi hiển thị RPM. Vì vậy **không thể suy ra xe đang tiến hay lùi chỉ từ các số RPM đã quan sát**. Nhận xét trước đó về chưa thấy chuỗi lùi phải hiểu là chưa có bằng chứng, không phải khẳng định xe không từng phát lệnh lùi.

### Kết luận bổ sung

Không cần thêm một lần chạy để chứng minh lỗi né tránh tái diễn. Các điểm cần truy nguyên đã được thu hẹp vào **điều kiện chuyển từ báo đỏ sang thoát kẹt, cơ chế cho phép chạy khi đang lỗi ở chế độ operator, và điều kiện nhận diện kẹt**. Đây là phần điều tra phần mềm, không phải yêu cầu người vận hành tiếp tục thử xe. Chưa thay đổi bất kỳ logic hoặc tham số nào.
