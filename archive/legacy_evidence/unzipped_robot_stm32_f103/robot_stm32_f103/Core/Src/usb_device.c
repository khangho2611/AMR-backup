#include "usb_device.h"
#include "usbd_core.h"
#include "usbd_desc.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"

USBD_HandleTypeDef hUsbDeviceFS;

void MX_USB_DEVICE_Init(void)
{
  /*
   * KỸ THUẬT BLUE PILL USB RE-ENUMERATION:
   * Trên board Blue Pill, trở kéo 1.5k trên chân USB D+ (PA12) được hàn cố định lên 3.3V.
   * Khi MCU reset hoặc nạp code mới qua ST-Link, máy tính sẽ không nhận biết MCU đã reset.
   * Kéo PA12 xuống LOW trong 15ms rồi thả ra để ép Windows phát hiện ngắt kết nối
   * và nhận diện lại cổng COM ngay lập tức!
   */
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitStruct.Pin = GPIO_PIN_12;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_12, GPIO_PIN_RESET);
  HAL_Delay(15);

  /* Trả chân PA12 về trạng thái mặc định để ngoại vi USB tiếp quản */
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* Khởi tạo USB Device Stack với lớp CDC */
  USBD_Init(&hUsbDeviceFS, &FS_Desc, 0);
  USBD_RegisterClass(&hUsbDeviceFS, &USBD_CDC);
  USBD_CDC_RegisterInterface(&hUsbDeviceFS, &USBD_Interface_fops_FS);
  USBD_Start(&hUsbDeviceFS);
}
