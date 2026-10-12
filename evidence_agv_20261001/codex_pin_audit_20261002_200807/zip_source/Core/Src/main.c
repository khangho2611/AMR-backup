/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Open-loop Motor & Encoder Test with USB CDC Virtual COM Port
  *                   STM32F103C8T6 Blue Pill + MKE-M18 (I2C) + GA25-370 Encoders
  *                   (Native USB-C CDC - Pure STM32 HAL - NO Arduino - NO USART)
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <string.h>
#include "encoder.h"
#include "mke_m18.h"
#include "pid.h"
#include "robot_motor.h"
#include "usb_device.h"
#include "usbd_cdc_if.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef struct
{
    int16_t speed;          /* Mức PWM (-255..+255) cấp đồng thời cho 2 motor */
    uint32_t duration_ms;   /* Thời gian duy trì mức tốc độ (ms) */
    const char *banner;     /* Thông báo in ra USB khi chuyển bước */
} MotorTestStep_t;
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define USB_PRINT_INTERVAL_MS   100     /* Xuất log qua USB CDC mỗi 100ms (10Hz) */
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */
/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c1;

TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;

/* USER CODE BEGIN PV */
Encoder_t g_enc_left;
Encoder_t g_enc_right;

PID_t g_pid_left;
PID_t g_pid_right;

#define MODE_OPEN_LOOP  0
#define MODE_PID        1

uint8_t g_control_mode = MODE_PID;

float g_target_rpm_left  = 0.0f;
float g_target_rpm_right = 0.0f;

/* Hệ số điều khiển PID tối ưu cho GA25-370 (chu kỳ 50ms) */
float g_kp = 0.50f;
float g_ki = 1.50f;
float g_kd = 0.010f;
float g_kf = 0.45f;

int16_t g_speed_left  = 0;
int16_t g_speed_right = 0;

static uint8_t s_i2c_scanned = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM3_Init(void);
/* USER CODE BEGIN PFP */
static void Print_USB_Debug_Log(void);
static void Process_USB_Commands(void);
static void Scan_I2C_Bus(void);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
static void Scan_I2C_Bus(void)
{
    USB_Print("{\"info\":\"Scanning I2C bus...\"}\r\n");
    uint8_t found_count = 0;

    for (uint8_t addr = 1; addr < 128; addr++)
    {
        if (HAL_I2C_IsDeviceReady(&hi2c1, (uint16_t)(addr << 1), 2, 5) == HAL_OK)
        {
            found_count++;
            MKE_M18_SetAddress(addr);
            USB_Print("{\"i2c_found\":\"0x%02X\"}\r\n", addr);
        }
    }

    if (found_count == 0)
    {
        USB_Print("{\"error\":\"No I2C device found\"}\r\n");
    }
    else
    {
        uint32_t vin_mv = 0;
        if (MKE_M18_ReadVIN(&vin_mv) == HAL_OK && vin_mv > 0)
        {
            USB_Print("{\"vin_mv\":%lu}\r\n", (unsigned long)vin_mv);
        }
    }
}

static void Process_USB_Commands(void)
{
    char cmd[64];
    if (CDC_ReadLine(cmd, sizeof(cmd)) > 0)
    {
        char *p = cmd;
        while (*p == ' ' || *p == '\t') p++;

        /* Lệnh STOP (Dừng khẩn cấp, reset tích phân PID) - Kiểm tra đầu tiên */
        if (strncmp(p, "STOP", 4) == 0 || strncmp(p, "stop", 4) == 0)
        {
            g_target_rpm_left  = 0.0f;
            g_target_rpm_right = 0.0f;
            PID_Reset(&g_pid_left);
            PID_Reset(&g_pid_right);

            g_speed_left  = 0;
            g_speed_right = 0;
            Robot_Stop();
            USB_Print("{\"ack\":\"STOP\"}\r\n");
        }
        /* Lệnh SCAN (Quét lại bus I2C) */
        else if (strncmp(p, "SCAN", 4) == 0 || strncmp(p, "scan", 4) == 0)
        {
            Scan_I2C_Bus();
        }
        /* Lệnh RESET (Reset bộ đếm encoder về 0) */
        else if (strncmp(p, "RESET", 5) == 0 || strncmp(p, "reset", 5) == 0)
        {
            Encoder_ResetCount(&g_enc_left);
            Encoder_ResetCount(&g_enc_right);
            USB_Print("{\"ack\":\"RESET\"}\r\n");
        }
        /* Lệnh PING kiểm tra kết nối */
        else if (strncmp(p, "PING", 4) == 0 || strncmp(p, "ping", 4) == 0)
        {
            USB_Print("{\"ack\":\"PONG\"}\r\n");
        }
        /* Lệnh TUNING <kp> <ki> <kd> [kf] (Hiệu chỉnh hệ số PID trực tiếp từ Web UI) */
        else if (strncmp(p, "TUNING", 6) == 0 || strncmp(p, "tuning", 6) == 0)
        {
            float kp = 0.0f, ki = 0.0f, kd = 0.0f, kf = g_kf;
            int n = sscanf(p + 6, "%f %f %f %f", &kp, &ki, &kd, &kf);
            if (n >= 3)
            {
                g_kp = kp;
                g_ki = ki;
                g_kd = kd;
                if (n >= 4) g_kf = kf;

                PID_SetGains(&g_pid_left, g_kp, g_ki, g_kd, g_kf);
                PID_SetGains(&g_pid_right, g_kp, g_ki, g_kd, g_kf);

                USB_Print("{\"ack\":\"TUNING %.3f %.3f %.4f %.3f\"}\r\n", g_kp, g_ki, g_kd, g_kf);
            }
        }
        /* Lệnh S <left_rpm> <right_rpm> (Điều khiển vận tốc vòng kín PID) */
        else if ((*p == 'S' || *p == 's') && (*(p + 1) == ' ' || *(p + 1) == '\t'))
        {
            float l_rpm = 0.0f, r_rpm = 0.0f;
            if (sscanf(p + 1, "%f %f", &l_rpm, &r_rpm) == 2)
            {
                if (l_rpm > 280.0f) l_rpm = 280.0f;
                if (l_rpm < -280.0f) l_rpm = -280.0f;
                if (r_rpm > 280.0f) r_rpm = 280.0f;
                if (r_rpm < -280.0f) r_rpm = -280.0f;

                g_target_rpm_left  = l_rpm;
                g_target_rpm_right = r_rpm;
                g_control_mode     = MODE_PID;

                USB_Print("{\"ack\":\"S %.1f %.1f\"}\r\n", g_target_rpm_left, g_target_rpm_right);
            }
        }
        /* Lệnh M <left_pwm> <right_pwm> (Chế độ thủ công PWM vòng hở) */
        else if ((*p == 'M' || *p == 'm') && (*(p + 1) == ' ' || *(p + 1) == '\t'))
        {
            int l_pwm = 0, r_pwm = 0;
            if (sscanf(p + 1, "%d %d", &l_pwm, &r_pwm) == 2)
            {
                if (l_pwm > 255) l_pwm = 255;
                if (l_pwm < -255) l_pwm = -255;
                if (r_pwm > 255) r_pwm = 255;
                if (r_pwm < -255) r_pwm = -255;

                g_control_mode = MODE_OPEN_LOOP;
                g_speed_left   = (int16_t)l_pwm;
                g_speed_right  = (int16_t)r_pwm;

                Robot_SetLeftMotor(g_speed_left);
                for (volatile int d = 0; d < 500; d++) {}
                Robot_SetRightMotor(g_speed_right);

                USB_Print("{\"ack\":\"M %d %d\"}\r\n", g_speed_left, g_speed_right);
            }
        }
    }
}

static void Print_USB_Debug_Log(void)
{
    /* Định dạng JSON 1 dòng tiêu chuẩn cho Web Dashboard parse mượt mà */
    USB_Print("{\"mode\":\"%s\",\"l_tgt\":%.1f,\"r_tgt\":%.1f,\"l_rpm\":%.2f,\"r_rpm\":%.2f,\"l_pwm\":%d,\"r_pwm\":%d,\"l_cnt\":%ld,\"r_cnt\":%ld}\r\n",
        (g_control_mode == MODE_PID) ? "PID" : "MAN",
        g_target_rpm_left,
        g_target_rpm_right,
        g_enc_left.rpm,
        g_enc_right.rpm,
        g_speed_left,
        g_speed_right,
        (long)Encoder_GetTotalCount(&g_enc_left),
        (long)Encoder_GetTotalCount(&g_enc_right)
    );
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/
  HAL_Init();

  /* Configure the system clock: SYSCLK = 72MHz, USB Clock = 48MHz (HSE 8MHz) */
  SystemClock_Config();

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_I2C1_Init();
  MX_TIM2_Init();
  MX_TIM3_Init();

  /* Khởi tạo USB Device CDC (kèm kỹ thuật ép Windows re-enumerate) */
  MX_USB_DEVICE_Init();

  /* USER CODE BEGIN 2 */
  /* 1. An toàn: Dừng động cơ ngay khi MCU khởi động */
  Robot_Motor_Init(&hi2c1);
  Robot_Stop();

  /* 2. Khởi tạo và kích hoạt Hardware Timer Encoder */
  Encoder_Init(&g_enc_left, &htim2, LEFT_ENCODER_DIRECTION);
  Encoder_Init(&g_enc_right, &htim3, RIGHT_ENCODER_DIRECTION);

  Encoder_Start(&g_enc_left);
  Encoder_Start(&g_enc_right);

  /* 3. Khởi tạo 2 bộ điều khiển PID tốc độ vòng kín */
  PID_Init(&g_pid_left, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);
  PID_Init(&g_pid_right, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);

  /* 4. Khởi tạo mốc thời gian lấy mẫu */
  uint32_t last_sample_tick = HAL_GetTick();
  uint32_t last_usb_tick    = HAL_GetTick();
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
      uint32_t current_tick = HAL_GetTick();

      /* Tác vụ 0: Xử lý lệnh điều khiển nhận từ Web Serial UI ngay khi có */
      Process_USB_Commands();

      /* Quét I2C một lần sau khi khởi động 1.5s */
      if (!s_i2c_scanned && current_tick >= 1500)
      {
          s_i2c_scanned = 1;
          Scan_I2C_Bus();
      }

      /* ----------------------------------------------------------------------
       * Tác vụ 1: Lấy mẫu encoder & tính toán PID mỗi 50ms (20Hz)
       * ---------------------------------------------------------------------- */
      if ((current_tick - last_sample_tick) >= ENCODER_SAMPLE_MS)
      {
          last_sample_tick += ENCODER_SAMPLE_MS;

          /* Đọc delta xung và tính RPM cho cả 2 bánh xe */
          Encoder_Update(&g_enc_left);
          Encoder_Update(&g_enc_right);

          Encoder_CalculateRPM(&g_enc_left, ENCODER_SAMPLE_DT_SEC, COUNTS_PER_OUTPUT_REV);
          Encoder_CalculateRPM(&g_enc_right, ENCODER_SAMPLE_DT_SEC, COUNTS_PER_OUTPUT_REV);

          /* Điều khiển vận tốc vòng kín PID nếu đang ở MODE_PID */
          if (g_control_mode == MODE_PID)
          {
              float out_l = PID_Compute(&g_pid_left, g_target_rpm_left, g_enc_left.rpm, ENCODER_SAMPLE_DT_SEC);
              float out_r = PID_Compute(&g_pid_right, g_target_rpm_right, g_enc_right.rpm, ENCODER_SAMPLE_DT_SEC);

              g_speed_left  = (int16_t)out_l;
              g_speed_right = (int16_t)out_r;

              Robot_SetLeftMotor(g_speed_left);
              for (volatile int d = 0; d < 500; d++) {}
              Robot_SetRightMotor(g_speed_right);
          }
      }

      /* ----------------------------------------------------------------------
       * Tác vụ 2: Xuất Telemetry JSON qua cổng USB CDC mỗi 100ms (10Hz)
       * ---------------------------------------------------------------------- */
      if ((current_tick - last_usb_tick) >= USB_PRINT_INTERVAL_MS)
      {
          last_usb_tick += USB_PRINT_INTERVAL_MS;
          Print_USB_Debug_Log();
      }

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  *        HSE = 8MHz
  *        PLL: 8MHz x 9 = 72MHz (SYSCLK)
  *        USB: 72MHz / 1.5 = 48MHz (Chuẩn Full Speed USB)
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9; /* 8MHz * 9 = 72MHz */
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }

  /** Cấu hình xung nhịp cho USB: 72MHz / 1.5 = 48MHz bắt buộc cho USB Full Speed
  */
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_USB;
  PeriphClkInit.UsbClockSelection = RCC_USBCLKSOURCE_PLL_DIV1_5;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief I2C1 Initialization Function (PB6=SCL, PB7=SDA, 100kHz)
  * @param None
  * @retval None
  */
static void MX_I2C1_Init(void)
{
  hi2c1.Instance = I2C1;
  hi2c1.Init.ClockSpeed = 100000;
  hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM2 Initialization Function (Encoder Left: PA0, PA1)
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 65535;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  sConfig.EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter = 6;
  sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter = 6;
  if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM3 Initialization Function (Encoder Right: PA6, PA7)
  * @param None
  * @retval None
  */
static void MX_TIM3_Init(void)
{
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 0;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 65535;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  sConfig.EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter = 6;
  sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter = 6;
  if (HAL_TIM_Encoder_Init(&htim3, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}

#ifdef  USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif /* USE_FULL_ASSERT */
