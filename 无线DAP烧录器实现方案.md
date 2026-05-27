# 无线 DAP 烧录器与无线串口实现方案

日期：2026-05-27

## 1. 目标定义

你要做的是一套“两端式无线调试/串口桥”：

| 端 | 连接位置 | 主要职责 |
|---|---|---|
| 电脑端模块 | 插到电脑 USB 口 | 在电脑上枚举成 CMSIS-DAP 调试器和 USB 虚拟串口，把 Keil/OpenOCD/串口助手的数据转成无线数据包 |
| 板端模块 | 插到 STM32 或其他目标板 | 接收无线 CMSIS-DAP 命令并在本地执行 SWD 时序；同时把目标 MCU 的 UART 和电脑虚拟串口互相桥接 |

最终用户体验应该是：

| 使用方式 | 目标板接线 | 电脑端表现 | 板端实际动作 |
|---|---|---|---|
| 无线烧录 / 调试 | `CLK, DIO, GND, 3.3V`，建议额外接 `RST` | Keil 选择 `CMSIS-DAP Debugger` 后点击 Download | 板端模块本地生成 `SWCLK/SWDIO` 波形，完成 SWD 烧录 |
| 无线串口 | `TX, RX, GND, 3.3V` | 电脑出现一个 COM 口，串口助手可收发 | 板端模块把无线数据和目标 UART 互转 |

关键结论：这个项目不能把 `CLK/DIO` 当作普通无线透明线缆。SWD 有严格的半双工方向切换、ACK、WAIT/FAULT 响应和时钟关系，必须让“板端模块”在目标 MCU 旁边本地执行 SWD 波形；无线链路只传 CMSIS-DAP 命令包和响应包。

## 2. 联网资料结论

| 资料 | 用途 | 关键结论 |
|---|---|---|
| [Arm CMSIS-DAP 官方文档](https://arm-software.github.io/CMSIS_6/latest/DAP/index.html) | 确认 DAP 本质 | CMSIS-DAP 是标准化访问 CoreSight DAP 的协议，调试器通过 USB 连接 Debug Unit，Debug Unit 再通过 SWD/JTAG 连接目标芯片 |
| [CMSIS-DAP DAP_Transfer 命令](https://arm-software.github.io/CMSIS-DAP/latest/group__DAP__Transfer.html) | 确认烧录核心命令 | `DAP_Transfer` 读写 DP/AP 寄存器，失败条件包括协议错误、目标 FAULT、WAIT 超限、Value Match 失败 |
| [CMSIS-DAP Firmware 配置说明](https://arm-software.github.io/CMSIS-DAP/latest/dap_firmware.html) | 确认固件结构 | 官方固件通过 `DAP_config.h` 适配 SWD/JTAG GPIO、USB、UART、SWO 等硬件 |
| [DAPLink GitHub](https://github.com/ARMmbed/DAPLink) | 确认 DAPLink 功能范围 | DAPLink 是开源接口固件，常见功能包括 MSC 拖拽烧录、CDC 虚拟串口、CMSIS-DAPv1 HID、CMSIS-DAPv2 WinUSB |
| [Keil CMSIS-DAP Debugger User's Guide](https://www.keil.com/support/man/docs/dapdebug/default.htm) | 确认 Keil 兼容性 | Keil MDK 的 CMSIS-DAP Debugger 可用于 Cortex-M 芯片 Flash 下载和调试 |
| [TinyUSB 官方文档](https://docs.tinyusb.org/) | USB 栈选择 | TinyUSB 支持 CDC、HID、MSC、Vendor 等 USB Device Class，适合做复合 USB 设备 |
| [ESP-NOW 官方文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/network/esp_now.html) | 无线链路选择 | ESP-NOW 是无连接 Wi-Fi 私有帧协议，默认速率 1 Mbps；v1 最大 250 字节，v2 最大 1470 字节，但应按版本兼容设计 |
| [TI SN74AXC4T245](https://www.ti.com/product/SN74AXC4T245) | SWD 电平转换 | 方向控制型双电源收发器，适合 JTAG/SPI/UART 这类推挽高速信号；最大数据率 380 Mbps，电压范围 0.65V 到 3.6V |
| [TI TXS0102](https://www.ti.com/product/TXS0102) | UART/I2C 类双向电平转换参考 | 自动方向双向电平转换器，适合开漏和低速推挽场景；高速 SWD 不建议依赖自动方向转换 |

## 3. 总体架构

推荐先做两个完全相同的硬件模块，通过拨码开关或按键选择角色：

```text
电脑 / Keil / 串口助手
        │ USB-C
        ▼
┌──────────────────────────────┐
│ 电脑端模块                    │
│ - USB CMSIS-DAP HID/WinUSB    │
│ - USB CDC 虚拟串口             │
│ - 无线收发与重传              │
└──────────────┬───────────────┘
               │ 2.4GHz 无线数据包
┌──────────────▼───────────────┐
│ 板端模块                      │
│ - CMSIS-DAP 命令执行器         │
│ - SWD GPIO/电平转换            │
│ - UART 桥接                   │
└──────┬───────────────┬───────┘
       │ SWCLK/SWDIO   │ TX/RX
       ▼               ▼
  目标 STM32 SWD     目标 MCU UART
```

不要设计成下面这种形式：

```text
电脑端 GPIO 产生 SWCLK/SWDIO -> 无线透明传输 -> 板端 GPIO 输出 SWCLK/SWDIO
```

原因如下：

| 问题 | 影响 |
|---|---|
| SWDIO 是半双工双向线 | 无线透明传输很难准确处理方向切换和 turnaround 周期 |
| SWCLK 与 SWDIO 需要稳定相对时序 | 无线链路存在不可控延迟、抖动和丢包 |
| 每个 SWD 事务都有 ACK/WAIT/FAULT | 必须在目标旁边实时采样并决定后续动作 |
| Keil 只认 USB 调试器 | 电脑端必须表现成标准 CMSIS-DAP 设备，不能只做串口透传 |

## 4. 主控和无线方案选择

### 4.1 推荐方案：ESP32-S3 + ESP-NOW

| 项目 | 说明 |
|---|---|
| 主控 | 两端都用 ESP32-S3-WROOM-1 或 ESP32-S3-MINI-1 |
| USB | ESP32-S3 原生 USB Device，电脑端使用 TinyUSB 枚举 HID + CDC |
| 无线 | ESP-NOW，先按 250 字节以内的数据包做兼容设计 |
| 优点 | 成本低、开发资料多、一颗芯片同时解决 USB + 无线 + GPIO |
| 缺点 | Wi-Fi 任务会带来延迟抖动；无线烧录速度不要期待接近有线 DAP |

这是最适合第一版打样的方案。第一版目标应是“Keil 能下载、串口能稳定收发”，不要一开始追求高速在线调试体验。

### 4.2 更稳但开发更难：nRF52840 + 私有 2.4GHz

| 项目 | 说明 |
|---|---|
| 主控 | 两端用 nRF52840 |
| USB | nRF52840 原生 USB Full-Speed |
| 无线 | Enhanced ShockBurst / 私有 2.4GHz / BLE 自定义通道 |
| 优点 | 低功耗、2.4GHz 实时性通常更可控，适合产品化 |
| 缺点 | USB CMSIS-DAP + 无线协议 + SWD 引擎的开发门槛更高 |

如果你后面要做小批量稳定产品，可以把 ESP32-S3 版本作为原型，再评估 nRF52840 或“USB MCU + 无线 MCU”的双芯片版本。

### 4.3 双芯片方案：RP2040/STM32 + 无线芯片

| 组合 | 特点 |
|---|---|
| RP2040 + ESP32-C3 | RP2040 负责 USB 和 SWD PIO，ESP32-C3 负责无线 |
| STM32F103/STM32G0 + nRF24L01 | 传统、便宜，但 USB 和无线协议开发量较大 |
| STM32U5/L4 + nRF52 | 稳定但成本和复杂度较高 |

双芯片方案的好处是 SWD 时序可以由更确定的 MCU 外设或 PIO 处理，无线只负责通信；坏处是 PCB、固件和升级流程更复杂。

## 5. 接口定义建议

你提出的两排接口可以保留，但建议明确每个引脚的电气意义。

### 5.1 SWD 排针

| 引脚名 | 建议丝印 | 方向 | 说明 |
|---|---|---|---|
| `CLK` | `SWCLK` | 板端模块 -> 目标 MCU | SWD 时钟 |
| `DIO` | `SWDIO` | 双向 | SWD 数据线，必须支持方向切换 |
| `GND` | `GND` | 公共地 | 板端模块和目标板必须共地 |
| `3.3V` | `VTREF/3V3` | 目标板 -> 模块，或模块 -> 目标板 | 强烈建议默认作为目标电压参考 `VTREF`；是否给目标供电用跳帽选择 |
| `5V` | `VIN/5V` | 可选 | 给板端模块供电，或通过限流开关给目标供电；不要当 5V SWD 逻辑参考 |

强烈建议额外增加测试焊盘或 6Pin 版本：

| 额外信号 | 原因 |
|---|---|
| `NRST` | 支持 Keil “connect under reset”、下载后复位、救砖和批量烧录更稳定 |
| `SWO` | 可选，支持 SWO Trace；第一版可以不做 |

如果 PCB 空间允许，建议最终接口从 5Pin 升级为：

```text
GND / VTREF / SWDIO / SWCLK / NRST / 5V
```

### 5.2 UART 排针

| 引脚名 | 建议丝印 | 方向 | 说明 |
|---|---|---|---|
| `TX` | `TXD` | 板端模块 -> 目标 MCU RX | 模块发给目标 |
| `RX` | `RXD` | 目标 MCU TX -> 板端模块 | 目标发给模块 |
| `GND` | `GND` | 公共地 | 必须连接 |
| `3.3V` | `VTREF/3V3` | 参考或供电 | 用于 UART 电平参考，或通过跳帽供电 |
| `5V` | `VIN/5V` | 可选供电 | 只做电源，不代表 UART 信号可以直接进 ESP32 |

注意：ESP32-S3 的 GPIO 不是 5V 容忍。即使排针上有 `5V`，UART 的 `RX` 也不能直接接 5V TTL，必须经过电平转换或限流保护。

## 6. 硬件设计

### 6.1 模块硬件框图

```text
                         ┌──────────────────┐
USB-C ─ ESD ─ CC电阻 ───►│ ESP32-S3          │◄── 天线 / 模块天线
VBUS ─ 保险丝 ─ 5V_SYS ─►│ USB + Wi-Fi + GPIO│
              │          └──────┬─────┬─────┘
              ▼                 │     │
        3.3V 稳压器              │     │
              │                 │     │
              ▼                 │     │
        3V3_MCU              SWD接口  UART接口
                                │     │
                         ┌──────▼─────▼──────┐
                         │ 电平转换 / ESD / 保护 │
                         └──────┬─────┬──────┘
                                │     │
                             目标板 SWD/UART
```

### 6.2 电源设计

| 电源节点 | 建议设计 |
|---|---|
| `USB_VBUS` | 来自电脑 USB-C，串联自恢复保险丝或限流开关 |
| `5V_SYS` | USB 5V 或目标板 5V 输入经过防反接/理想二极管后形成 |
| `3V3_MCU` | 给 ESP32-S3 和板上逻辑供电，建议稳压器峰值能力 >= 600mA |
| `VTREF` | 从目标板 `3.3V` 引脚采样，给电平转换器目标侧供电或作为目标电压检测 |
| `3V3_OUT` | 如果要给目标板供电，必须经过跳帽和限流开关；默认不建议直接输出 |

ESP32-S3 无线发射时瞬时电流较大，不建议长期从目标 STM32 板的小 LDO 上偷 3.3V 给模块供电。更稳的方式是：板端模块用目标板 5V、单独 USB 口或电池供电，目标板 3.3V 只作为 `VTREF`。

### 6.3 USB-C 设计要点

| 项目 | 建议 |
|---|---|
| CC1/CC2 | 各接 5.1k 下拉到 GND，声明 UFP 设备 |
| D+/D- | 等长、短走线、靠近 USB 口放 ESD 保护 |
| VBUS | 加保险丝、TVS、输入电容 |
| 屏蔽壳 | 通过电容/电阻或机壳地策略处理，第一版可按常规 USB 参考设计 |

### 6.4 SWD 电平转换

SWD 推荐使用方向控制型电平转换，不推荐使用自动方向电平转换器来处理高速 SWDIO。

| 信号 | 推荐做法 |
|---|---|
| `SWCLK` | ESP32-S3 GPIO -> 方向控制电平转换 -> 目标 `SWCLK` |
| `SWDIO` | 使用带 `DIR/OE` 的双电源收发器，固件在读写阶段主动切换方向 |
| `NRST` | 开漏或 NMOS 下拉方式，只拉低不强推高，目标侧上拉 |
| `SWO` | 可选，目标 -> 模块 UART/RMT 输入，第一版可不做 |

推荐器件：

| 器件 | 适合范围 | 说明 |
|---|---|---|
| `SN74AXC4T245` | 1.2V/1.8V/3.3V 目标，最高 3.6V | 方向控制，适合 SWD/JTAG/SPI/UART 推挽信号 |
| `SN74LVC1T45` 系列 | 单路方向控制 | 可以拆成单信号使用，便于 SWDIO/CLK 独立控制 |
| `TXS0102/TXB010x` | 低速 UART 或普通 GPIO | 不建议作为 SWDIO 的第一选择 |

设计细节：

| 细节 | 说明 |
|---|---|
| 串联电阻 | `SWCLK/SWDIO` 靠近驱动端串 22Ω 到 47Ω，减小过冲 |
| ESD | 排针外接信号靠近接口放低电容 ESD |
| 上拉/下拉 | `SWDIO` 可加 47k 到 100k 弱上拉到 `VTREF`，不要用太强上拉影响速度 |
| 目标电压 | 第一版建议只保证 3.3V 目标稳定；1.8V 和 5V 目标作为后续扩展 |

### 6.5 UART 电平转换

| 场景 | 推荐 |
|---|---|
| 目标 UART 是 3.3V | 可直接通过 100Ω 串联电阻连接，外加 ESD |
| 目标 UART 是 5V TTL | 必须电平转换，目标 TX 到模块 RX 可用分压/缓冲器，模块 TX 到目标 RX 用 5V 侧转换器 |
| 目标 UART 是 1.8V | 使用双电源方向控制电平转换器，`VTREF=1.8V` |

第一版若主要服务 STM32，建议声明 UART 支持 3.3V TTL。5V UART 通过硬件版本 2 再完整支持，避免 ESP32 GPIO 被 5V 损坏。

### 6.6 PCB 布局建议

| 区域 | 布局要求 |
|---|---|
| RF 天线 | 使用模组天线时按模组手册做禁布区，天线下方和前方不要铺铜、不要走线 |
| USB | D+/D- 短、等长、远离天线和开关电源；ESD 靠近接口 |
| 电源 | ESP32-S3 供电脚附近放 0.1uF + 1uF，稳压器输入输出按手册放电容 |
| SWD 接口 | 排针、ESD、串阻、电平转换器尽量靠近，走线短且远离 RF 天线 |
| GND | 大面积地平面，RF 区按模组参考设计打地过孔 |
| 调试焊盘 | 预留 ESP32-S3 下载/日志串口、BOOT、EN、SWD/JTAG 或 USB 下载相关测试点 |

第一版推荐 4 层板：`Top 信号 + GND + 3V3/5V + Bottom 信号`。如果做 2 层板，RF 和 USB 的布局容错会变差，但低速原型也能验证功能。

## 7. 固件总体设计

### 7.1 电脑端固件

电脑端模块必须让 Keil 和串口助手看到标准设备：

| USB 接口 | 推荐第一版 | 用途 |
|---|---|---|
| CMSIS-DAP | HID，64 字节包 | Keil 下载和调试，Windows 免驱概率高 |
| CDC ACM | 1 个虚拟 COM 口 | 无线串口 |
| Vendor/WinUSB | 第二版再做 | CMSIS-DAP v2 bulk 速度更好，但 USB 描述符和 Windows 兼容更复杂 |

电脑端任务划分：

| 任务 | 作用 |
|---|---|
| `usb_dap_task` | 接收 USB HID 的 CMSIS-DAP 请求包，转成无线 DAP 请求 |
| `usb_cdc_task` | 接收/发送 USB CDC 串口数据 |
| `radio_tx_task` | 负责无线发送、排队、重传、超时 |
| `radio_rx_task` | 接收板端响应，按 `seq` 分发给 DAP 或 UART |
| `pairing_task` | 按键配对、保存对端 MAC 和密钥 |

电脑端 CMSIS-DAP 处理策略：

| 命令类别 | 处理位置 |
|---|---|
| `DAP_Info` 中的厂商名、产品名、包大小 | 电脑端可以本地回答，但要与无线协议能力一致 |
| `DAP_Connect / DAP_Disconnect / DAP_SWJ_Clock / DAP_SWJ_Sequence` | 转发给板端执行 |
| `DAP_Transfer / DAP_TransferBlock` | 必须转发给板端执行 |
| `DAP_ResetTarget` | 转发给板端，板端控制 `NRST` |
| `DAP_UART` 或 USB CDC 数据 | 第一版建议走自定义 UART 数据帧，不必实现 CMSIS-DAP UART 命令集 |

### 7.2 板端固件

板端模块是真正接触目标 MCU 的一端。

| 任务 | 作用 |
|---|---|
| `radio_rx_task` | 接收电脑端的 DAP/UART/控制数据 |
| `dap_exec_task` | 调用 CMSIS-DAP 命令执行器，生成 SWD 时序 |
| `swd_gpio_layer` | 直接控制 `SWCLK/SWDIO/DIR/OE/NRST` |
| `uart_bridge_task` | 目标 UART 与无线 UART 帧互转 |
| `radio_tx_task` | 发送 DAP 响应和 UART 数据 |

板端 SWD 执行要点：

| 要点 | 说明 |
|---|---|
| SWD 时钟 | 第一版建议 100kHz 到 1MHz 起步，确认稳定后再提高 |
| 临界区 | 单个 SWD 事务中尽量减少任务切换；关键 GPIO 翻转函数放 IRAM |
| 方向切换 | 写阶段 `SWDIO` 输出，读 ACK/数据阶段切到输入，并控制电平转换器 `DIR/OE` |
| WAIT 重试 | 遵循 CMSIS-DAP 的 WAIT 重试计数，超限后返回错误 |
| Reset | 有 `NRST` 时实现 `DAP_ResetTarget`；无 `NRST` 时返回不支持或只做软复位相关操作 |

### 7.3 为什么不建议第一版完整移植 DAPLink

DAPLink 是完整接口固件，除了 CMSIS-DAP，还有 MSD 拖拽烧录、板卡识别、目标芯片 flash algorithm 管理等内容。你的无线烧录目标是 Keil 点击 Download，这条路径主要需要 CMSIS-DAP，不一定需要 DAPLink 的 MSC 拖拽烧录。

建议路线：

| 阶段 | 选择 |
|---|---|
| 第一版 | 实现 `Wireless CMSIS-DAP + CDC`，兼容 Keil 的 CMSIS-DAP 下载 |
| 第二版 | 增加 CMSIS-DAP v2 WinUSB bulk，提高速度 |
| 第三版 | 如果确实需要 U 盘拖拽烧录，再研究 DAPLink 的 MSD 和目标 flash algorithm |

## 8. 无线协议设计

### 8.1 帧格式

建议自定义一个很小的二进制帧：

```c
/*
 * 无线链路统一帧头。
 * 该帧头用于区分 DAP、UART、控制、ACK 等不同业务，并通过 seq 支持重传和乱序检测。
 */
typedef struct {
    uint16_t magic;      // 固定魔数，例如 0x5744，表示 Wireless DAP
    uint8_t  version;    // 协议版本，便于后续升级兼容
    uint8_t  type;       // 帧类型：DAP_REQ、DAP_RSP、UART_DATA、CTRL、ACK
    uint16_t seq;        // 序号，请求和响应使用同一个序号匹配
    uint8_t  flags;      // 标志位，例如是否需要 ACK、是否为最后分片
    uint8_t  frag_idx;   // 当前分片编号
    uint8_t  frag_cnt;   // 总分片数量
    uint16_t len;        // payload 长度
    uint16_t crc16;      // 帧头和 payload 的 CRC，避免误包
} wireless_frame_header_t;
```

帧类型建议：

| 类型 | 方向 | 说明 |
|---|---|---|
| `DAP_REQ` | 电脑端 -> 板端 | 一个 CMSIS-DAP USB 请求包 |
| `DAP_RSP` | 板端 -> 电脑端 | 对应请求的 CMSIS-DAP 响应包 |
| `UART_DATA` | 双向 | 串口数据 |
| `CTRL` | 双向 | 配对、心跳、版本、设置串口波特率 |
| `ACK` | 双向 | 应用层确认 |
| `NACK` | 双向 | CRC 错误、分片丢失、忙 |

### 8.2 DAP 数据传输策略

| 规则 | 说明 |
|---|---|
| 严格请求-响应 | 一个 `DAP_REQ` 必须等到对应 `DAP_RSP` 或超时 |
| 高优先级 | DAP 帧优先级高于 UART，避免 Keil 超时 |
| 分片 | HID 64 字节可直接塞进 ESP-NOW v1；WinUSB 512 字节时要分片 |
| 超时 | 电脑端对 DAP 响应设置短超时和有限重试，超时后给 Keil 返回错误 |
| 顺序 | DAP 请求不乱序执行，保证调试状态一致 |

### 8.3 UART 数据传输策略

| 规则 | 说明 |
|---|---|
| 缓冲 | 电脑端 USB CDC 和板端 UART 都使用环形缓冲区 |
| 合包 | 多个 UART 字节可以合并成一个无线帧，降低空口开销 |
| 延迟上限 | 例如 2ms 到 5ms flush 一次，兼顾实时性和吞吐 |
| 流控 | 第一版可不接 RTS/CTS，但必须实现软件水位线，缓冲快满时通知对端暂停 |
| 丢包策略 | 串口数据建议也做 ACK/重传，否则串口日志在干扰环境下会丢字节 |

### 8.4 配对和安全

| 项目 | 建议 |
|---|---|
| 配对方式 | 两端同时长按按键进入配对，交换 MAC/随机数 |
| 保存位置 | ESP32-S3 使用 NVS 保存对端 MAC、信道、密钥 |
| 加密 | ESP-NOW 可使用 PMK/LMK；应用层也可再加 AES-CTR/CMAC |
| 防串扰 | 帧内包含设备 ID 和协议 magic，避免附近多个模块互相误收 |
| 信道 | 配对后固定 Wi-Fi 信道，减少扫描时间和不确定性 |

## 9. Keil 下载流程

用户操作流程：

| 步骤 | 操作 |
|---|---|
| 1 | 电脑端模块插入电脑 USB |
| 2 | Windows 设备管理器中出现 `Wireless CMSIS-DAP` 和一个 COM 口 |
| 3 | 板端模块连接目标板 `SWCLK/SWDIO/GND/VTREF`，最好再接 `NRST` |
| 4 | 两端完成配对，指示灯显示无线链路在线 |
| 5 | Keil `Options for Target -> Debug` 选择 `CMSIS-DAP Debugger` |
| 6 | `Settings` 中选择 `SWD`，SWD Clock 先设低，例如 100kHz 或 500kHz |
| 7 | `Flash Download` 保持目标芯片对应的 Flash Algorithm |
| 8 | 点击 `Download` |

内部数据流程：

```text
Keil
  │ CMSIS-DAP USB HID Request
  ▼
电脑端 ESP32-S3
  │ DAP_REQ 无线帧
  ▼
板端 ESP32-S3
  │ 本地执行 SWD 事务
  ▼
目标 STM32
  │ ACK / DATA
  ▼
板端 ESP32-S3
  │ DAP_RSP 无线帧
  ▼
电脑端 ESP32-S3
  │ CMSIS-DAP USB HID Response
  ▼
Keil
```

预期表现：

| 项目 | 第一版合理目标 |
|---|---|
| Keil 识别 | 能识别 CMSIS-DAP 设备 |
| 连接目标 | 能读到 Cortex-M IDCODE |
| 下载速度 | 先追求稳定，不追求高速；可能明显慢于有线 DAP |
| 在线调试 | 单步、断点可能可用，但体验取决于无线延迟 |
| 大容量固件 | 需要应用层重传和稳定电源，否则容易中途失败 |

## 10. 软件开发步骤

### 10.1 第一阶段：USB 设备跑通

| 任务 | 验收标准 |
|---|---|
| 建 ESP-IDF 工程 | 两块 ESP32-S3 都能编译、下载、打印日志 |
| TinyUSB HID | 电脑能看到自定义 HID 设备 |
| CMSIS-DAP HID 描述符 | Keil 或 pyOCD 能看到 CMSIS-DAP 名称 |
| TinyUSB CDC | 电脑出现 COM 口，能本地回环收发 |

### 10.2 第二阶段：无线链路跑通

| 任务 | 验收标准 |
|---|---|
| ESP-NOW 初始化 | 两端固定信道互发心跳 |
| 配对 | 按键配对后保存对端 MAC |
| ACK/重传 | 人为干扰或丢包时能重传 |
| 分片重组 | 64/128/512 字节 payload 都能正确传输 |

### 10.3 第三阶段：无线串口

| 任务 | 验收标准 |
|---|---|
| USB CDC -> 无线 -> UART | 串口助手发送，目标 MCU 收到 |
| UART -> 无线 -> USB CDC | 目标 MCU 打印日志，串口助手显示 |
| 波特率设置 | 串口助手改波特率后板端 UART 同步设置 |
| 压力测试 | 115200 连续传输 10 分钟不丢包或可统计重传 |

### 10.4 第四阶段：CMSIS-DAP 命令代理

| 任务 | 验收标准 |
|---|---|
| `DAP_Info` | Keil/pyOCD 能读取设备信息 |
| `DAP_Connect` | 能切到 SWD 模式 |
| `DAP_SWJ_Clock` | 能设置板端 SWD 时钟 |
| `DAP_SWJ_Sequence` | 能输出 SWD/JTAG 切换序列 |
| `DAP_Transfer` | 能读 DP IDCODE |
| `DAP_TransferBlock` | 能批量读写内存 |

### 10.5 第五阶段：Keil 下载验证

| 任务 | 验收标准 |
|---|---|
| STM32F103 最小板 | 读 IDCODE、擦除、下载 blink |
| STM32F4/GD32/AT32 | 至少验证 1 到 2 种 Cortex-M 目标 |
| 无 `NRST` 测试 | 正常目标可下载，但记录限制 |
| 有 `NRST` 测试 | 支持 connect under reset，救砖能力更好 |
| 断点单步 | 能设置断点、单步、读写变量，但记录速度 |

## 11. 固件实现关键点

### 11.1 CMSIS-DAP 包大小

第一版推荐 CMSIS-DAP v1 HID：

| 参数 | 建议 |
|---|---|
| USB HID Report | 64 字节 |
| 无线 DAP payload | 64 字节或稍大 |
| `DAP_PACKET_COUNT` | 先设 1 或 2，稳定后增加 |
| `DAP_PACKET_SIZE` | 与 HID 报告长度一致 |

如果后续做 CMSIS-DAP v2 bulk：

| 参数 | 说明 |
|---|---|
| USB bulk 包 | Full-Speed 常见 64 字节，High-Speed 可更大；ESP32-S3 是 Full-Speed USB |
| 无线分片 | 必须做可靠分片 |
| 优势 | WinUSB bulk 相比 HID 更适合高吞吐 |
| 风险 | Windows 描述符、驱动绑定和 Keil 识别需要仔细验证 |

### 11.2 SWD GPIO 层

板端需要实现类似下面的抽象层：

```c
/*
 * 初始化 SWD 相关 GPIO 和电平转换器控制脚。
 * 主要流程：
 * 1. 配置 SWCLK 为输出并默认拉低。
 * 2. 配置 SWDIO 初始为输出高电平，用于 line reset。
 * 3. 配置 DIR/OE 控制脚，确保上电时不会误驱动目标板。
 * 4. 若硬件提供 NRST，则配置为开漏输出或通过 NMOS 控制。
 * 返回值：0 表示初始化成功，负值表示 GPIO 或硬件状态异常。
 */
int swd_io_init(void);

/*
 * 设置 SWDIO 方向。
 * 参数 output 为 true 时，模块驱动 SWDIO；为 false 时，释放 SWDIO 并采样目标输出。
 * 关键点：切换方向时必须同步切换电平转换器 DIR/OE，并留出很短的 turnaround 时间。
 */
void swd_set_swdio_output(bool output);

/*
 * 发送并可选采样一个 SWD bit。
 * 参数 bit_out 是需要输出到目标的位。
 * 返回值是从 SWDIO 采样到的位；当 SWDIO 处于输出阶段时，返回值通常仅用于调试。
 */
uint8_t swd_transfer_bit(uint8_t bit_out);
```

ESP32-S3 上建议把高频 GPIO 翻转函数放到 IRAM，并在短事务中使用临界区，避免 Flash cache 或 Wi-Fi 任务造成极端抖动。SWD 不是连续高速同步总线，低频下能容忍一定周期抖动，但方向切换和采样点必须正确。

### 11.3 USB CDC 波特率同步

串口助手改波特率时，电脑端 TinyUSB CDC 会收到 line coding 变化。电脑端应发送控制帧给板端：

| 字段 | 说明 |
|---|---|
| baudrate | 例如 9600、115200、921600 |
| data_bits | 通常 8 |
| parity | none/even/odd |
| stop_bits | 1/2 |

板端收到后重新配置 UART。第一版建议支持 `8N1`，波特率先覆盖 `9600/115200/230400/460800/921600`。

## 12. 兼容范围与限制

| 类型 | 支持情况 |
|---|---|
| STM32 Cortex-M | 主要支持对象，使用 SWD + CMSIS-DAP |
| GD32/AT32/APM32 等 Cortex-M | 理论支持，取决于 Keil/OpenOCD 目标算法和芯片兼容性 |
| NXP/Nordic/Microchip Cortex-M | 理论支持，前提是工具链支持 CMSIS-DAP |
| CH32V/RISC-V | 不属于标准 Arm CMSIS-DAP/SWD 路线，需单独研究协议和工具链 |
| AVR/8051/PIC | 不能通过 SWD CMSIS-DAP 烧录，只能做无线串口或另做对应烧录协议 |
| UART 串口 | 只要电平匹配，基本都支持 |

必须提前接受的限制：

| 限制 | 解释 |
|---|---|
| 下载速度慢于有线 DAP | 无线请求-响应延迟无法消除 |
| 在线调试体验有限 | 单步、查看变量会产生大量 DAP 事务 |
| 需要稳定电源 | 板端模块掉电或目标板供电不足会导致下载中断 |
| 建议加 `NRST` | 没有复位线时，部分低功耗、锁死、改错时钟的目标板可能连不上 |
| 第一版不要承诺 5V SWD | 5V 供电脚不等于 5V 调试逻辑支持 |

## 13. 建议 BOM

| 模块 | 推荐器件 | 数量 | 说明 |
|---|---|---:|---|
| 主控无线 | ESP32-S3-WROOM-1 / ESP32-S3-MINI-1 | 1 | 每块模块一颗 |
| USB | USB-C 16Pin 母座 | 1 | 只做 USB2.0 Device |
| USB CC | 5.1k 1% | 2 | CC1/CC2 下拉 |
| USB ESD | USBLC6-2 或同类低电容 ESD | 1 | 保护 D+/D- |
| 电源 | 3.3V 600mA 以上 LDO 或 DCDC | 1 | ESP32 峰值电流要留余量 |
| 保护 | 自恢复保险丝/限流开关 | 1 | USB/目标供电保护 |
| SWD 电平转换 | SN74AXC4T245 或多个 SN74LVC1T45 | 1 组 | 方向控制型 |
| UART 电平转换 | SN74LVC1T45/TXS0102/电阻分压组合 | 1 组 | 按支持电压选择 |
| 排针 | 2.54mm 或 1.27mm 5Pin x2 | 2 | SWD 排和 UART 排 |
| 按键 | Pair / Boot / Reset | 2 到 3 | 配对、下载、复位 |
| 指示灯 | Power / Link / DAP / UART | 3 到 4 | 调试很有用 |

## 14. 推荐原型路线

| 阶段 | 硬件 | 目标 |
|---|---|---|
| 原型 0 | 两块 ESP32-S3 开发板 + 杜邦线 | 验证 USB CDC、ESP-NOW、无线串口 |
| 原型 1 | ESP32-S3 开发板 + 外接电平转换小板 | 验证 SWD IDCODE 读取 |
| 原型 2 | 第一版 PCB，3.3V SWD + 3.3V UART | 验证 Keil 下载 STM32 |
| 原型 3 | 加 `NRST`、外壳、保护、更多电平范围 | 提升可靠性和易用性 |
| 原型 4 | CMSIS-DAP v2、速度优化、批量测试 | 接近可用产品 |

不要一开始就直接画最终产品 PCB。先用开发板把“Keil 能不能通过无线 CMSIS-DAP 下载”验证出来，这是整个项目最大风险。

## 15. 调试和验证清单

| 测试项 | 方法 | 通过标准 |
|---|---|---|
| USB 枚举 | Windows 设备管理器 / USBView | 同时看到 CMSIS-DAP HID 和 CDC COM |
| 无线稳定性 | 心跳包 + 丢包统计 | 近距离丢包率低，断开可自动重连 |
| UART 回环 | 板端 TX/RX 短接 | 串口助手收发一致 |
| SWD 波形 | 逻辑分析仪看 SWCLK/SWDIO | line reset、request、ACK、turnaround 正确 |
| IDCODE | pyOCD/OpenOCD/自测命令 | 能读到 Cortex-M DP ID |
| Keil 下载 | STM32 blink 工程 | 多次 Download 成功 |
| 断点调试 | Keil debug session | 能 halt、run、step、breakpoint |
| 异常恢复 | 拔掉板端、目标断电、无线断开 | Keil 不死锁，模块能重新连接 |

## 16. 第一版最小可行规格

| 项目 | 第一版规格 |
|---|---|
| 芯片 | ESP32-S3-WROOM-1 x 2 |
| USB | CMSIS-DAP v1 HID + CDC ACM |
| 无线 | ESP-NOW，固定信道，应用层 ACK/重传 |
| SWD | 3.3V 目标，100kHz 到 1MHz |
| UART | 3.3V TTL，115200 优先，最高再测试 921600 |
| 目标 | STM32F103C8T6 最小系统板优先验证 |
| 供电 | 电脑端 USB 供电；板端优先 5V/VIN 供电，3.3V 作为 VTREF |
| 额外线 | 强烈建议加 NRST 焊盘或 6Pin 版本 |

## 17. 需要提前决定的问题

| 问题 | 推荐答案 |
|---|---|
| 两块板是否使用同一 PCB？ | 是，同一 PCB 用角色开关选择电脑端/板端，方便生产和备件 |
| 是否必须支持 5V UART？ | 第一版不强制，先保证 3.3V；硬件上预留转换器位置 |
| 是否必须支持 5V SWD？ | 不建议。绝大多数 Cortex-M SWD 是 1.8V/3.3V；5V 作为电源即可 |
| 是否需要 NRST？ | 强烈建议需要，即使主排针不放，也要放焊盘 |
| 是否做 DAPLink 拖拽烧录？ | 第一版不做，先做 CMSIS-DAP 下载和 CDC 串口 |
| 是否做加密？ | 配对和设备 ID 第一版就做；正式产品再增强加密和认证 |

## 18. 推荐结论

最务实的实现路线是：

1. 两端都用 ESP32-S3。
2. 电脑端通过 TinyUSB 枚举成 `CMSIS-DAP HID + CDC COM`。
3. 板端移植 CMSIS-DAP 命令执行核心，本地用 GPIO 和方向控制电平转换器执行 SWD。
4. 两端之间用 ESP-NOW 传输可靠的 `DAP_REQ/DAP_RSP/UART_DATA` 数据帧。
5. 接口保留你提出的两排 5Pin，但把 `3.3V` 定义为 `VTREF/可选供电`，把 `5V` 定义为 `VIN/可选供电`，不要把 5V 当作 SWD/UART 逻辑默认支持。
6. 第一版目标只承诺 3.3V STM32 无线下载和 3.3V TTL 无线串口；`NRST`、5V UART、CMSIS-DAP v2、拖拽烧录作为后续增强。

如果按这个路线做，Keil 端会认为你插了一个普通 CMSIS-DAP 调试器；目标板端会认为旁边接了一个普通 SWD 下载器。无线链路被隐藏在两个模块之间，这才是最容易兼容现有工具链的架构。
