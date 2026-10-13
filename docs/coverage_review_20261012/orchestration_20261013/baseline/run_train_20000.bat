@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Huấn Luyện AI Coverage V2 - AGV Autonomous Navigation
color 0b

echo ==============================================================================
echo        CHƯƠNG TRÌNH HUẤN LUYỆN DRL COVERAGE V2 (CHUẨN HỢP ĐỒNG 2026)
echo ==============================================================================
echo.
echo [*] Bắt đầu huấn luyện mô hình Double DQN trên môi trường ma trận giả lập...
echo [*] Bạn có thể bấm Ctrl+C bất cứ lúc nào để dừng và lưu checkpoint an toàn.
echo.

python "train_coverage_20000.py" %*
set TRAIN_EXIT_CODE=%errorlevel%

echo.
if %TRAIN_EXIT_CODE% equ 0 (
    echo ==============================================================================
    echo        HUẤN LUYỆN HOÀN TẤT VÀ ĐÃ XUẤT FILE MODEL THÀNH CÔNG!
    echo ==============================================================================
) else (
    echo [!] Tiến trình kết thúc với mã lỗi: %TRAIN_EXIT_CODE%
)

pause
exit /b %TRAIN_EXIT_CODE%
