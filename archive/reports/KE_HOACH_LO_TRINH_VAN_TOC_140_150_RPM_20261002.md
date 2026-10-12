# DINH CHINH & HIEU CHINH TOAN DIEN TAI LIEU LO TRINH VAN TOC AGV
**Tai lieu:** KE_HOACH_LO_TRINH_VAN_TOC_140_150_RPM_20261002.md
**Phien ban:** 2.0 (Hieu chinh theo Codex Review 10:55) | **Trang thai:** DRAFT / HYPOTHESIS SPECIFICATION ONLY
**Hardware Owner:** Khang AI Assistant
**Cam ket phan cung:** Xe AGV dat tinh tren san, trang thai DISARMED, CHUA DUOC PHEP CHAY (NOT APPROVED).

---

## 1. DINH CHINH CAC GIA THUYET & PHAM VI DO LUONG (ANTI-OVERCLAIM)

1. Chuyen dong vat ly 0-2mm va am thanh dong co: UNVERIFIED / UNMEASURED. Dang cho du lieu quan sat khach quan tu Khang.
2. Nguyen nhan RPM = 0.00 va Odometry = 0.00 khong phai sole-cause deadband ma la 4 gia thuyet can kiem chung:
   - H1 (Mechanical Deadband): Ma sat tinh giua banh xe, san va hop giam toc 21.3:1 lon hon mo-men o PWM <= 23.
   - H2 (Luong tu hoa xung Encoder): Do phan giai 937.2 xung/vong tren chu ky 50ms yeu cau >= 1 xung (> 0.384 do) moi nhay khoi 0.00 RPM.
   - H3 (Ti so truyen thuc te chua kiem chung): Ti so truyen 21.3 va 11 PPR la thong so source, chua do tren truc va banh.
   - H4 (Nguon cap / Driver H-Bridge): Duoi tai 1.75 kg, sut ap hoac deadband mach cong suat lam dong khoi dong chua du.
3. Cu ly dung <= 15mm la tinh toan ly thuyet tren mo hinh quan tinh ly tuong, UNMEASURED tren thuc te.

---

## 2. CHOT DUY NHAT MOT PROFILE THUC NGHIEM CHO BAI CHAY TIEP THEO

- Muc tieu: Khao sat nguong thoat Deadband va kiem chung phan hoi xung Encoder.
- Van toc danh dinh: v = 0.080 m/s (Target RPM = 20.9 RPM).
- Thoi gian danh dinh: t_nominal = 1.0s, gia toc a = 0.15 m/s^2, hard time cap = 1.5s.
- Quang duong ly thuyet co ramp: s_nominal ~ 58.7 mm (5.87 cm).

---

## 3. LO TRINH TIEM CAN MUC TIEU 140-150 RPM CUA KHANG

1. Buoc 1 (Candidate v = 0.08 m/s / 20.9 RPM): Do cu ly dung va phan hoi xung encoder dau tien.
2. Buoc 2 (Tiem can tran an toan firmware v = 0.15 m/s / 39.1 RPM): Do sai lech banh va heading drift.
3. Buoc 3 (Thu nghiem v = 0.25 m/s / 65.0 RPM): Tran RPM clamp cua firmware. Danh gia phanh o toc do cao.
4. Buoc 4 (Muc tieu 140 - 150 RPM / 0.537 - 0.575 m/s): Trien khai sau khi hoan tat cac buoc truoc va duoc Codex phe duyet.

---

## 4. KE HOACH DO DAC PHAN TICH NGUYEN NHAN THUC TE

1. Do ti so truyen & CPR thuc te: Ke banh xe quay tay 1 vong 360 do, doc total_count doi chieu voi 937.2.
2. Do quang duong & huong: Dung thuoc la tren san phong Lab lam Ground Truth doi chieu Odometry.
