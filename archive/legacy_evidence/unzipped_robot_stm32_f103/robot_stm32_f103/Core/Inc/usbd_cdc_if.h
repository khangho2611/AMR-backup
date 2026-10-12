#ifndef __USBD_CDC_IF_H
#define __USBD_CDC_IF_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "usbd_cdc.h"

#define APP_RX_DATA_SIZE  256
#define APP_TX_DATA_SIZE  256

extern USBD_CDC_ItfTypeDef USBD_Interface_fops_FS;

/* API truyền dữ liệu qua USB CDC */
uint8_t CDC_Transmit_FS(uint8_t* Buf, uint16_t Len);

/* Đọc một dòng lệnh hoàn chỉnh từ USB CDC (trả về độ dài chuỗi, hoặc 0 nếu chưa có dòng mới) */
uint16_t CDC_ReadLine(char *dest, uint16_t max_len);

/* Helper in chuỗi định dạng qua USB CDC (tương tự printf) */
void USB_Print(const char *format, ...);

/* Kiểm tra trạng thái USB đã kết nối với PC hay chưa */
uint8_t USB_IsConnected(void);

#ifdef __cplusplus
}
#endif

#endif /* __USBD_CDC_IF_H */
