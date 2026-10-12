#include "usbd_cdc_if.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

extern USBD_HandleTypeDef hUsbDeviceFS;

uint8_t UserRxBufferFS[APP_RX_DATA_SIZE];
uint8_t UserTxBufferFS[APP_TX_DATA_SIZE];

static int8_t CDC_Init_FS(void);
static int8_t CDC_DeInit_FS(void);
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t* pbuf, uint16_t length);
static int8_t CDC_Receive_FS(uint8_t* pbuf, uint32_t *Len);

USBD_CDC_ItfTypeDef USBD_Interface_fops_FS =
{
  CDC_Init_FS,
  CDC_DeInit_FS,
  CDC_Control_FS,
  CDC_Receive_FS
};

USBD_CDC_LineCodingTypeDef LineCoding =
{
  115200, /* baud rate*/
  0x00,   /* stop bits-1*/
  0x00,   /* parity - none*/
  0x08    /* nb. of bits 8*/
};

static int8_t CDC_Init_FS(void)
{
  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0);
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS);
  return (USBD_OK);
}

static int8_t CDC_DeInit_FS(void)
{
  return (USBD_OK);
}

static int8_t CDC_Control_FS(uint8_t cmd, uint8_t* pbuf, uint16_t length)
{
  switch(cmd)
  {
    case CDC_SEND_ENCAPSULATED_COMMAND:
      break;

    case CDC_GET_ENCAPSULATED_RESPONSE:
      break;

    case CDC_SET_COMM_FEATURE:
      break;

    case CDC_GET_COMM_FEATURE:
      break;

    case CDC_CLEAR_COMM_FEATURE:
      break;

    case CDC_SET_LINE_CODING:
      LineCoding.bitrate = (uint32_t)(pbuf[0] | (pbuf[1] << 8) |\
                            (pbuf[2] << 16) | (pbuf[3] << 24));
      LineCoding.format = pbuf[4];
      LineCoding.paritytype = pbuf[5];
      LineCoding.datatype = pbuf[6];
      break;

    case CDC_GET_LINE_CODING:
      pbuf[0] = (uint8_t)(LineCoding.bitrate);
      pbuf[1] = (uint8_t)(LineCoding.bitrate >> 8);
      pbuf[2] = (uint8_t)(LineCoding.bitrate >> 16);
      pbuf[3] = (uint8_t)(LineCoding.bitrate >> 24);
      pbuf[4] = LineCoding.format;
      pbuf[5] = LineCoding.paritytype;
      pbuf[6] = LineCoding.datatype;
      break;

    case CDC_SET_CONTROL_LINE_STATE:
      break;

    case CDC_SEND_BREAK:
      break;

    default:
      break;
  }

  return (USBD_OK);
}

#define USB_CMD_BUFFER_SIZE  512

static volatile char s_cmd_ring_buffer[USB_CMD_BUFFER_SIZE];
static volatile uint16_t s_cmd_head = 0;
static volatile uint16_t s_cmd_tail = 0;

static int8_t CDC_Receive_FS(uint8_t* Buf, uint32_t *Len)
{
  uint32_t length = *Len;
  for (uint32_t i = 0; i < length; i++)
  {
    uint16_t next_head = (s_cmd_head + 1) % USB_CMD_BUFFER_SIZE;
    if (next_head != s_cmd_tail)
    {
      s_cmd_ring_buffer[s_cmd_head] = (char)Buf[i];
      s_cmd_head = next_head;
    }
  }

  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, &Buf[0]);
  USBD_CDC_ReceivePacket(&hUsbDeviceFS);
  return (USBD_OK);
}

uint16_t CDC_ReadLine(char *dest, uint16_t max_len)
{
  if (dest == NULL || max_len < 2) return 0;

  /* Kiểm tra xem trong ring buffer có ký tự kết thúc dòng '\n' hay chưa */
  uint16_t temp_tail = s_cmd_tail;
  uint8_t has_line = 0;
  while (temp_tail != s_cmd_head)
  {
    char c = s_cmd_ring_buffer[temp_tail];
    if (c == '\n' || c == '\r')
    {
      has_line = 1;
      break;
    }
    temp_tail = (temp_tail + 1) % USB_CMD_BUFFER_SIZE;
  }

  if (!has_line) return 0;

  /* Đọc các ký tự cho đến khi gặp '\n' hoặc '\r' */
  uint16_t idx = 0;
  while (s_cmd_tail != s_cmd_head)
  {
    char c = s_cmd_ring_buffer[s_cmd_tail];
    s_cmd_tail = (s_cmd_tail + 1) % USB_CMD_BUFFER_SIZE;

    if (c == '\r' || c == '\n')
    {
      if (idx > 0)
      {
        break;
      }
      continue;
    }

    if (idx < (max_len - 1))
    {
      dest[idx++] = c;
    }
  }

  dest[idx] = '\0';
  return idx;
}

uint8_t CDC_Transmit_FS(uint8_t* Buf, uint16_t Len)
{
  uint8_t result = USBD_OK;
  
  /* Nếu thiết bị chưa được cấu hình bởi Host PC thì thoát ngay */
  if (hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED)
  {
    return USBD_FAIL;
  }

  USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef*)hUsbDeviceFS.pClassData;
  if (hcdc == NULL)
  {
    return USBD_FAIL;
  }

  /* Đợi tối đa 5ms nếu bộ đệm trước đó đang bận, tránh blocking vô hạn */
  uint32_t start_tick = HAL_GetTick();
  while (hcdc->TxState != 0)
  {
    if ((HAL_GetTick() - start_tick) >= 5)
    {
      return USBD_BUSY;
    }
  }

  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, Buf, Len);
  result = USBD_CDC_TransmitPacket(&hUsbDeviceFS);
  return result;
}

uint8_t USB_IsConnected(void)
{
  return (hUsbDeviceFS.dev_state == USBD_STATE_CONFIGURED);
}

void USB_Print(const char *format, ...)
{
  char tx_buffer[256];
  va_list args;
  va_start(args, format);
  int len = vsnprintf(tx_buffer, sizeof(tx_buffer), format, args);
  va_end(args);

  if (len > 0)
  {
    CDC_Transmit_FS((uint8_t *)tx_buffer, (uint16_t)len);
  }
}
