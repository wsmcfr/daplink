# 无线 DAP 中配版 PCB 布局、器件选型与网络标签说明

日期：2026-05-28

## 1. 文档目标

本文面向嘉立创EDA原理图和 PCB 绘制阶段，目标是把中配版无线 DAP 硬件从“方案描述”推进到“可以开始摆器件和连网络标签”的程度。

本文默认采用中配增强版：

| 模块 | 推荐选型 | 作用 |
|---|---|---|
| 主控 MCU | `CH32V307RCT6` | 负责 USB High-Speed、CMSIS-DAP、目标 SWD、本地 UART、与 ESP 通信 |
| 无线协处理器 | `ESP32-C6-WROOM-1U-N8` | 负责 Wi-Fi 无线链路、配对、OTA、无线数据收发 |
| 目标接口 | 3.3V SWD + 3.3V UART | 第一版主打 STM32/GD32/AT32 等 3.3V Cortex-M 目标 |
| 扩展接口 | SPI 必连，SDIO 预留，UART 调试保留 | SPI 用于第一版打通，SDIO 给后续提速 |
| PCB 形态 | 长条形 4 层板 | USB、电源、主控、无线、目标接口分区清楚，便于布线 |

重要边界：

| 边界 | 说明 |
|---|---|
| 5V 引脚 | 只作为电源输入或可控输出，不代表 SWD/UART 支持 5V 逻辑 |
| 无线 SWD | 不透传 SWCLK/SWDIO 波形，板端 CH32 在目标旁边本地执行 SWD |
| CH32 调试口 | `PA13/PA14` 只给 CH32 自身下载调试，不能拿去接目标板 SWD |
| 第一版目标 | 稳定识别、稳定下载、稳定无线串口，速度优化放到后续固件阶段 |

## 2. 推荐整板布局

### 2.1 板形与器件分区

推荐使用长条形布局，USB-C 在左，目标接口在右下或下边，ESP32-C6 天线在右上板边。这样 USB、电源、RF、SWD 四个最容易互相干扰的区域可以自然分开。

```text
┌──────────────────────────────────────────────────────────────┐
│ 左侧 USB/电源区          中部主控区              右侧无线区   │
│                                                              │
│ USB-C  ESD  Fuse/DCDC   CH32V307RCT6       ESP32-C6-WROOM-1U │
│  │      │       │       8MHz晶振/去耦        U.FL/外接天线朝外 │
│  │      │       │            │                    │           │
│  └──USBHS PB6/PB7───────┘     └──SPI/SDIO/UART────┘           │
│                                                              │
│ WCH-Link调试口       按键/LED/测试点       SWD/UART/10Pin接口 │
└──────────────────────────────────────────────────────────────┘
```

| 区域 | 推荐位置 | 核心器件 | 布局目的 |
|---|---|---|---|
| USB 输入区 | 板左边缘 | USB-C、USB ESD、CC 电阻、VBUS 保护 | 缩短 USB 差分线，降低 ESD 回流路径 |
| 电源区 | USB-C 后方偏左 | 5V 保护、3.3V DCDC/LDO、电源电感、电容 | 让电源先稳定，再分配给 CH32 和 ESP |
| CH32 主控区 | 板中部 | CH32V307RCT6、8MHz 晶振、去耦电容 | 让 USB、ESP、目标接口到主控距离都较短 |
| ESP 无线区 | 右上板边 | ESP32-C6-WROOM-1U、U.FL 天线座或外置天线引出 | 让天线远离 USB 口、目标排针和电源电感 |
| 目标接口区 | 右下或下边 | SWD 排针、UART 排针、10Pin Cortex、ESD、串阻 | 让目标信号先保护再进主控，接线直观 |
| 调试操作区 | 板边易按位置 | Reset、Boot、Pair、LED、测试点 | 方便调试、烧录、配对和故障定位 |

### 2.2 4 层板叠层建议

| 层 | 用途 | 规则 |
|---|---|---|
| L1 Top | 主器件、USB/SPI/SDIO/SWD 关键线 | 高速线优先同层直连，少打过孔 |
| L2 GND | 完整地平面 | 不切割，不走信号，给 USB/RF/SPI/SDIO 提供连续回流 |
| L3 Power/Slow | 3.3V、5V、慢速控制线 | 电源面尽量成片，避免穿过 RF 天线净空 |
| L4 Bottom | 低速信号、测试点、少量跨区连接 | 不建议走 USB HS、SDIO CLK、RF 附近信号 |

## 3. 嘉立创EDA器件搜索与选型

下面的“嘉立创EDA搜索关键词”用于放置原理图库和 PCB 封装时搜索。实际下单前要在立创商城确认库存、封装、温度等级和价格。

### 3.1 核心 IC

| 功能 | 推荐器件 | 嘉立创EDA搜索关键词 | 封装/备注 |
|---|---|---|---|
| 主控 MCU | `CH32V307RCT6` | `CH32V307RCT6` | LQFP64M，10mm x 10mm，0.5mm pitch |
| 无线模组 | `ESP32-C6-WROOM-1U-N8` | `ESP32-C6-WROOM-1U` | 外接天线版本，优先用于第一版 |
| 无线模组备选 | `ESP32-C6-WROOM-1-N8` | `ESP32-C6-WROOM-1` | 板载天线版本，必须严格做天线净空 |
| 可选电平转换 | `SN74LVC1T45` / `SN74AXC4T245` | `SN74LVC1T45`、`SN74AXC4T245` | 增强版支持低压目标时再焊 |
| USB ESD | `USBLC6-2SC6` 或同类低电容 TVS | `USBLC6-2`、`USB ESD` | 靠近 USB-C |
| 普通信号 ESD | 低电容 ESD 阵列或单路 ESD | `ESD5V`、`SRV05`、`PESD5V` | 靠近目标接口 |

### 3.2 电源与保护

| 功能 | 推荐规格 | 嘉立创EDA搜索关键词 | 备注 |
|---|---|---|---|
| USB-C 座 | USB2.0 Type-C 16Pin 母座 | `TYPE-C 16P`、`USB-C 16Pin`、`Type-C 母座` | 只做 USB2.0 Device |
| CC 电阻 | 5.1k 1% | `5.1K 0603` | CC1/CC2 各一颗下拉 |
| 5V 输入保护 | 自恢复保险丝或限流开关 | `PTC 500mA`、`TPS2553`、`限流开关` | USB VBUS 后级保护 |
| 主 3.3V | 1A 级 DCDC 或低噪声 LDO | `3.3V DCDC`、`SY8089`、`AP2112K-3.3` | ESP 峰值电流较大，优先 1A 级 |
| ESP 支路测流 | 0R 电阻或电流采样跳线 | `0R 0603`、`Current Sense` | 第一版建议保留 |
| 目标供电开关 | 5V/3.3V 负载开关 | `TPS22918`、`TPS2553`、`Load Switch` | 默认可不焊或默认关闭 |

### 3.3 接口、按键与显示

| 功能 | 推荐器件 | 嘉立创EDA搜索关键词 | 备注 |
|---|---|---|---|
| CH32 调试口 | 4Pin/5Pin 排针或 1.27mm 调试座 | `排针 1x4`、`SWD 1.27` | 接 WCH-Link |
| 目标 SWD | 2.54mm 1x6 排针 | `排针 1x6 2.54` | 推荐线序：GND、VTREF、SWDIO、SWCLK、NRST、5V |
| 目标 UART | 2.54mm 1x5 排针 | `排针 1x5 2.54` | TXD、RXD、GND、VTREF、5V |
| Cortex 10Pin | 1.27mm 2x5 SWD 座 | `Cortex 10Pin`、`SWD 10P 1.27` | 标准调试线兼容 |
| U.FL 座 | IPEX/U.FL 射频座 | `U.FL`、`IPEX` | 配合 WROOM-1U |
| 按键 | 轻触按键 | `轻触按键 3x4`、`KEY SMD` | Reset、Boot、Pair |
| LED | 0603 LED | `LED 0603` | Power、Link、DAP、UART |

## 4. 电源网络与标签

### 4.1 电源树

```text
USB_VBUS
   │
   ├── TVS / Fuse / Load Switch
   │
   ├── 5V_SYS
   │       ├── 目标 5V 可控输出：TARGET_5V_SW
   │       └── 3.3V 稳压器输入
   │
   └── 3V3_SYS
           ├── 3V3_CH32
           ├── 3V3_ESP
           ├── 3V3_IO
           └── 可选目标 3.3V 输出：TARGET_3V3_SW
```

| 网络标签 | 含义 | 连接对象 |
|---|---|---|
| `USB_VBUS` | USB-C 输入 5V 原始电源 | USB-C VBUS、输入 TVS、保险丝前端 |
| `5V_SYS` | 受保护后的板上 5V | 3.3V 稳压器输入、目标 5V 负载开关 |
| `3V3_SYS` | 主 3.3V 电源 | CH32、ESP、逻辑电路 |
| `3V3_CH32` | CH32 支路 3.3V | CH32 VDD/VIO/VDDA 去耦 |
| `3V3_ESP` | ESP 支路 3.3V | ESP 模组 3V3，建议经 0R/磁珠分支 |
| `VTREF` | 目标板电压参考输入 | 目标 SWD/UART 排针、ADC 分压、电平转换目标侧 |
| `VTREF_ADC` | VTREF 分压后的 ADC 信号 | CH32 ADC 输入 |
| `TARGET_5V_SW` | 可控目标 5V 输出 | 目标接口 5V 引脚，默认关闭 |
| `TARGET_3V3_SW` | 可控目标 3.3V 输出 | 目标接口 VTREF/3.3V，默认谨慎使用 |
| `GND` | 系统地 | USB、CH32、ESP、目标接口公共地 |

### 4.2 电源布局规则

| 对象 | 规则 |
|---|---|
| CH32 去耦 | 每个 VDD/VIO 旁放 0.1uF，芯片附近再放 4.7uF 或 10uF |
| ESP 去耦 | 3V3 入口放 10uF，近端放 1uF + 0.1uF，地端就近打孔 |
| DCDC 电感 | 远离 ESP 天线、U.FL、CH32 晶振、USB 差分线 |
| VDDA | 建议用 0R 或磁珠从 3V3_CH32 分出，旁边放 1uF + 0.1uF |
| VTREF | 先进入保护/分压，再接 ADC，不要直接强驱动目标电源 |

## 5. CH32V307RCT6 引脚分配

### 5.1 必须固定的系统引脚

| CH32 引脚/管脚 | 网络标签 | 用途 | 说明 |
|---|---|---|---|
| `PB6 / USBHS_DM` | `USB_DM_HS` | USB High-Speed D- | 接 USB-C D-，按差分线布线 |
| `PB7 / USBHS_DP` | `USB_DP_HS` | USB High-Speed D+ | 接 USB-C D+，按差分线布线 |
| `PA13 / SWDIO` | `CH32_SWDIO` | CH32 自身调试数据 | 只接 WCH-Link 调试口 |
| `PA14 / SWCLK` | `CH32_SWCLK` | CH32 自身调试时钟 | 只接 WCH-Link 调试口 |
| `NRST` | `CH32_NRST` | CH32 复位 | 接复位按键、调试口、RC 复位 |
| `BOOT0` | `CH32_BOOT0` | CH32 启动模式选择 | 默认下拉，预留 Boot 按键或焊盘 |
| `PB2 / BOOT1` | `CH32_BOOT1` | 启动配置 | 默认下拉，不要悬空 |
| `PD0 / OSC_IN` | `CH32_HSE_IN` | 8MHz 晶振输入 | 晶振靠近 CH32 |
| `PD1 / OSC_OUT` | `CH32_HSE_OUT` | 8MHz 晶振输出 | 晶振线短且对称 |

### 5.2 CH32 到 ESP 的 SPI 主通道

SPI 是第一版最容易打通的主控到无线协处理器链路。建议所有 SPI 线都预留串联电阻焊盘，初始焊 0R，后续可改 22R/33R。

| CH32 引脚 | 网络标签 | 方向 | 连接到 ESP | 用途 |
|---|---|---|---|---|
| `PB12 / SPI2_NSS` | `ESP_SPI_CS` | CH32 -> ESP | ESP SPI CS | SPI 片选 |
| `PB13 / SPI2_SCK` | `ESP_SPI_SCK` | CH32 -> ESP | ESP SPI CLK | SPI 时钟，必须最短且参考地连续 |
| `PB14 / SPI2_MISO` | `ESP_SPI_MISO` | ESP -> CH32 | ESP SPI MISO | ESP 返回数据 |
| `PB15 / SPI2_MOSI` | `ESP_SPI_MOSI` | CH32 -> ESP | ESP SPI MOSI | CH32 发送数据 |
| `PC2` | `ESP_IRQ` | ESP -> CH32 | ESP GPIO IRQ | ESP 通知有新包 |
| `PC0` | `ESP_EN_CTRL` | CH32 -> ESP | ESP EN 控制 | 主控复位 ESP，建议经 0R 隔离 |
| `PC1` | `ESP_BOOT_CTRL` | CH32 -> ESP | ESP IO9/BOOT 控制 | 主控控制 ESP 进入下载模式 |

### 5.3 CH32 到 ESP 的 UART 调试/下载口

| CH32 引脚 | 网络标签 | 方向 | 连接到 ESP | 用途 |
|---|---|---|---|---|
| `PA2 / USART2_TX` | `ESP_UART_RXD` | CH32 -> ESP | ESP UART0 RXD | CH32 向 ESP 发送下载/控制数据 |
| `PA3 / USART2_RX` | `ESP_UART_TXD` | ESP -> CH32 | ESP UART0 TXD | ESP 日志或下载返回 |

说明：网络标签按“对端功能”命名会更直观，`ESP_UART_RXD` 表示接到 ESP 的 RXD。

### 5.4 预留 SDIO 4-bit 高速通道

SDIO 第一版可以只放串阻和测试焊盘，不一定贴齐全部器件。布线时仍要按高速线处理，避免后续想启用时发现走线不可用。

| CH32 候选引脚 | 网络标签 | 连接到 ESP 候选脚 | 用途 |
|---|---|---|---|
| `PD2 / SDIO_CMD` | `ESP_SDIO_CMD` | ESP SDIO CMD | 命令线，上拉焊盘预留 |
| `PC12 / SDIO_CK` | `ESP_SDIO_CLK` | ESP SDIO CLK | SDIO 时钟，最关键 |
| `PC8 / SDIO_D0` | `ESP_SDIO_D0` | ESP SDIO D0 | 数据 0 |
| `PC9 / SDIO_D1` | `ESP_SDIO_D1` | ESP SDIO D1 | 数据 1 |
| `PC10 / SDIO_D2` | `ESP_SDIO_D2` | ESP SDIO D2 | 数据 2 |
| `PC11 / SDIO_D3` | `ESP_SDIO_D3` | ESP SDIO D3 | 数据 3 |

注意：如果使用 `PB14/PB15` 同时做 SPI 和 SDIO 复用，原理图必须放 0R 选择电阻，避免两个接口硬短。第一版推荐 SPI 走 `PB12~PB15`，SDIO 独立预留 `PC8~PC12/PD2`。

### 5.5 目标 SWD 与 UART

| CH32 引脚 | 网络标签 | 方向 | 目标接口标签 | 用途 |
|---|---|---|---|---|
| `PA8` | `TARGET_SWCLK` | CH32 -> 目标 | `SWCLK` | SWD 时钟，串 22R~47R |
| `PA9` | `TARGET_SWDIO` | 双向 | `SWDIO` | SWD 数据，需支持输入输出切换 |
| `PA10` | `TARGET_NRST_CTRL` | CH32 -> NMOS | `NRST` | 开漏方式拉低目标复位 |
| `PB10 / USART3_TX` | `TARGET_UART_TXD` | CH32 -> 目标 | `TXD` | 模块 TXD，接目标 RX |
| `PB11 / USART3_RX` | `TARGET_UART_RXD` | 目标 -> CH32 | `RXD` | 模块 RXD，接目标 TX |
| `PA0 / ADC` | `VTREF_ADC` | 目标 -> CH32 | `VTREF` | 采样目标电压 |
| `PA1 / ADC` | `VBUS_DET` | USB -> CH32 | USB VBUS 检测 | 可选，用于判断 USB 接入 |

目标 SWD 默认 3.3V 直连保护版：

```text
CH32 GPIO ─ 22R/47R ─ ESD ─ 目标接口
```

增强版低压目标：

```text
CH32 GPIO ─ 电平转换 A 侧
VTREF ───── 电平转换 B 侧
电平转换 B 侧 ─ 22R/47R ─ ESD ─ 目标接口
```

## 6. ESP32-C6-WROOM-1U 引脚与外部电路

### 6.1 ESP 必接基础电路

| ESP 信号 | 网络标签 | 连接 | 用途 |
|---|---|---|---|
| `3V3` | `3V3_ESP` | 3.3V 电源 | ESP 模组供电 |
| `GND` | `GND` | 系统地 | 地参考 |
| `EN` | `ESP_EN` | 10k 上拉到 3V3，1uF 到 GND，按键/CH32 可拉低 | ESP 复位/使能 |
| `IO9` | `ESP_BOOT` | 默认上拉，按键/CH32 可拉低 | ESP 下载启动模式 |
| `TXD0` | `ESP_UART_TXD` | CH32 `PA3`，可串 499R/0R | ESP 日志/下载 TX |
| `RXD0` | `ESP_UART_RXD` | CH32 `PA2`，可串 499R/0R | ESP 日志/下载 RX |

### 6.2 ESP USB 调试预留

ESP32-C6 自带 USB Serial/JTAG，建议第一版至少预留测试点；如果空间允许，也可以放一个不焊 USB-C 或焊盘口。

| ESP 信号 | 网络标签 | 用途 | 备注 |
|---|---|---|---|
| `IO12 / USB_D-` | `ESP_USB_DM` | ESP USB D- | 预留测试点或调试 USB 口 |
| `IO13 / USB_D+` | `ESP_USB_DP` | ESP USB D+ | 预留测试点或调试 USB 口 |

注意：不要把 CH32 的 USB HS D+/D- 和 ESP 的 USB D+/D- 直接并到同一个 USB-C。若要同时支持，必须用 USB MUX 或单独调试口；第一版建议 CH32 占用主 USB-C，ESP USB 只留测试点。

### 6.3 ESP 到 CH32 的 SPI/SDIO 连接建议

ESP32-C6 模组的可用 GPIO 需要按最终模组手册和 ESP-IDF 驱动确认。本文给出网络级连接要求，原理图阶段应优先选择不影响启动绑带和 USB 调试的普通 GPIO。

| 网络标签 | 连接关系 | 建议 |
|---|---|---|
| `ESP_SPI_CS` | CH32 SPI2_NSS -> ESP GPIO | 选普通 GPIO，避免启动绑带脚 |
| `ESP_SPI_SCK` | CH32 SPI2_SCK -> ESP GPIO | 短线，预留串阻 |
| `ESP_SPI_MOSI` | CH32 SPI2_MOSI -> ESP GPIO | 预留串阻 |
| `ESP_SPI_MISO` | ESP GPIO -> CH32 SPI2_MISO | 预留串阻 |
| `ESP_IRQ` | ESP GPIO -> CH32 EXTI | 建议上拉或下拉明确默认状态 |
| `ESP_SDIO_CMD` | CH32 SDIO_CMD <-> ESP SDIO CMD | 预留 10k~47k 上拉 |
| `ESP_SDIO_CLK` | CH32 SDIO_CK -> ESP SDIO CLK | 最短、少过孔 |
| `ESP_SDIO_D0~D3` | CH32 SDIO_D0~D3 <-> ESP SDIO DATA | 每线预留串阻和上拉焊盘 |

## 7. 目标接口线序与网络标签

### 7.1 推荐 6Pin SWD 排针

建议不要继续只放 `CLK/DIO/GND/3.3V/5V` 五根线，至少升级成 6Pin，把 `NRST` 加进去。

| 排针脚位 | 丝印 | 网络标签 | 含义 |
|---|---|---|---|
| 1 | `GND` | `GND` | 公共地 |
| 2 | `VTREF` | `VTREF` | 目标电压参考，默认由目标板提供 |
| 3 | `DIO` | `TARGET_SWDIO` | SWD 双向数据 |
| 4 | `CLK` | `TARGET_SWCLK` | SWD 时钟 |
| 5 | `RST` | `TARGET_NRST` | 目标复位，开漏拉低 |
| 6 | `5V` | `TARGET_5V_SW` | 可控 5V 电源，默认关闭或不焊 |

### 7.2 推荐 5Pin UART 排针

| 排针脚位 | 丝印 | 网络标签 | 含义 |
|---|---|---|---|
| 1 | `TXD` | `TARGET_UART_TXD` | 模块发给目标 RX |
| 2 | `RXD` | `TARGET_UART_RXD` | 目标 TX 发给模块 |
| 3 | `GND` | `GND` | 公共地 |
| 4 | `VTREF` | `VTREF` | 目标电压参考 |
| 5 | `5V` | `TARGET_5V_SW` | 可控 5V 电源，默认关闭或不焊 |

### 7.3 Cortex 10Pin 标准接口

如果 PCB 空间允许，建议放 1.27mm 2x5 Cortex Debug 焊盘或座子，即使第一版不焊也保留封装。

| Cortex 信号 | 网络标签 | 说明 |
|---|---|---|
| `VTREF` | `VTREF` | 目标电压参考 |
| `SWDIO/TMS` | `TARGET_SWDIO` | SWD 数据 |
| `GND` | `GND` | 地 |
| `SWCLK/TCK` | `TARGET_SWCLK` | SWD 时钟 |
| `SWO/TDO` | `TARGET_SWO` | 第一版可只留焊盘 |
| `RESET` | `TARGET_NRST` | 目标复位 |

## 8. 布线规则

### 8.1 USB High-Speed

| 项目 | 规则 |
|---|---|
| 网络 | `USB_DP_HS`、`USB_DM_HS` |
| 阻抗 | 90Ω 差分，按嘉立创板厂 4 层叠层计算线宽线距 |
| 走线 | USB-C 到 CH32 `PB6/PB7` 尽量短、平行、等长 |
| 过孔 | 尽量不换层；必须换层时旁边放地回流孔 |
| ESD | USB ESD 靠近 USB-C，先过 ESD 再进板内 |
| 禁忌 | 不要分叉，不要跨电源分割，不要靠近 DCDC 电感 |

### 8.2 ESP SPI

| 项目 | 规则 |
|---|---|
| 网络 | `ESP_SPI_SCK`、`ESP_SPI_MOSI`、`ESP_SPI_MISO`、`ESP_SPI_CS` |
| 串阻 | 每线预留 0R/22R/33R，`SCK` 必须预留 |
| 走线 | CH32 到 ESP 直连，尽量短，避免穿过 USB 和电源开关区 |
| 参考地 | L2 保持完整 GND，SCK 旁边优先有地回流 |
| 测试点 | `SCK`、`MISO`、`MOSI`、`CS` 建议放小测试点 |

### 8.3 预留 SDIO

| 项目 | 规则 |
|---|---|
| 网络 | `ESP_SDIO_CLK`、`ESP_SDIO_CMD`、`ESP_SDIO_D0~D3` |
| 串阻 | 6 根线都预留串阻，初始可不焊 |
| 上拉 | `CMD`、`D0~D3` 预留 10k~47k 上拉到 3V3 |
| 等长 | 数据/CMD 相对 CLK 尽量接近，第一版按短线优先 |
| 换层 | 尽量同层完成，换层处加地孔 |

### 8.4 SWD 与 UART

| 项目 | 规则 |
|---|---|
| SWCLK | 从 CH32 到接口短而直，串 22R~47R 靠近 CH32 |
| SWDIO | 走线短，避免靠近 ESP 天线和 DCDC 电感 |
| NRST | 使用 NMOS/开漏，只拉低目标复位，不强推高 |
| UART | 目标侧 TX/RX 串 47R~100R 或按实际速率调整 |
| ESD | 所有外接到目标板的信号靠近接口放保护 |
| VTREF | 先保护和分压，再进 ADC；不要用细线绕很远 |

### 8.5 RF 与天线

| 场景 | 规则 |
|---|---|
| WROOM-1U | U.FL 座和外接天线远离 USB-C、金属外壳、电源电感、大电流线 |
| WROOM-1 | 板载天线必须伸出板边，天线下方和前方不铺铜、不走线、不放器件 |
| 模组下方 | 严格按官方推荐封装和 keepout，不自行缩小禁布区 |
| 地孔 | 模组地焊盘周围多打地孔，但不要破坏天线净空 |

## 9. 必焊、可选与测试点

### 9.1 第一版必须焊接

| 类别 | 器件/网络 |
|---|---|
| 主控 | CH32V307RCT6、8MHz 晶振、CH32 去耦、WCH-Link 调试口 |
| USB | USB-C、CC 电阻、USB ESD、VBUS 保护、USB HS 线 |
| 电源 | 3.3V 稳压器、CH32/ESP 去耦、电源指示 LED |
| 无线 | ESP32-C6-WROOM-1U、EN RC、BOOT 按键/焊盘、UART0 焊盘 |
| 主通道 | CH32-ESP SPI、ESP_IRQ、ESP_EN_CTRL、ESP_BOOT_CTRL |
| 目标 | SWD 6Pin、UART 5Pin、NRST 开漏、VTREF ADC、目标信号串阻/ESD |

### 9.2 第一版建议预留但可不焊

| 类别 | 器件/网络 |
|---|---|
| SDIO | `ESP_SDIO_CLK/CMD/D0~D3` 串阻、上拉、测试点 |
| ESP USB | `ESP_USB_DP/DM` 测试点或调试 USB 焊盘 |
| 目标供电 | `TARGET_5V_SW`、`TARGET_3V3_SW` 负载开关 |
| 电平转换 | SWD/UART 低压目标电平转换器位置 |
| Cortex 接口 | 1.27mm 2x5 焊盘或座子 |
| 电流测量 | ESP 3.3V 支路 0R/电流采样焊盘 |

### 9.3 必须放测试点

| 测试点 | 网络标签 | 用途 |
|---|---|---|
| `TP_5V` | `5V_SYS` | 检查 USB 输入保护后电压 |
| `TP_3V3` | `3V3_SYS` | 检查主 3.3V |
| `TP_GND` | `GND` | 示波器/逻辑分析仪地夹 |
| `TP_USB_DP/DM` | `USB_DP_HS`、`USB_DM_HS` | USB 枚举排查 |
| `TP_ESP_EN` | `ESP_EN` | ESP 复位排查 |
| `TP_ESP_BOOT` | `ESP_BOOT` | ESP 下载模式排查 |
| `TP_ESP_UART_TX/RX` | `ESP_UART_TXD`、`ESP_UART_RXD` | ESP 日志和下载 |
| `TP_SPI_CLK` | `ESP_SPI_SCK` | SPI 时钟检查 |
| `TP_TARGET_SWCLK` | `TARGET_SWCLK` | SWD 波形检查 |
| `TP_TARGET_SWDIO` | `TARGET_SWDIO` | SWD 数据检查 |
| `TP_VTREF` | `VTREF` | 目标电压检查 |

## 10. 嘉立创EDA绘制顺序建议

| 步骤 | 操作 | 检查点 |
|---|---|---|
| 1 | 先画电源页 | `USB_VBUS`、`5V_SYS`、`3V3_SYS`、`3V3_ESP`、`VTREF` 标签清楚 |
| 2 | 画 CH32 最小系统 | 电源、HSE、NRST、BOOT0、PA13/PA14 调试口完整 |
| 3 | 画 USB-C 到 CH32 | `USB_DP_HS/USB_DM_HS` 不和 ESP USB 混接 |
| 4 | 画 ESP 最小系统 | `ESP_EN`、`ESP_BOOT`、UART0、3V3 去耦完整 |
| 5 | 画 CH32-ESP SPI | SPI、IRQ、EN、BOOT 网络标签一致 |
| 6 | 画 SDIO 预留 | 串阻、上拉、测试点全部标成可选 |
| 7 | 画目标 SWD/UART | SWD、NRST、UART、VTREF、ESD、串阻完整 |
| 8 | 放连接器和测试点 | 所有外接接口都有丝印和方向标识 |
| 9 | 进入 PCB 摆放 | 先固定 USB-C、ESP 天线、目标接口，再摆 CH32 和电源 |
| 10 | 走关键线 | 先走 USB HS、SPI/SDIO、SWD，再走电源和低速线 |

## 11. PCB 最终检查清单

| 检查项 | 通过标准 |
|---|---|
| USB HS | `PB6/PB7` 到 USB-C 差分短、等长、连续参考地、ESD 靠近接口 |
| CH32 调试 | `PA13/PA14/NRST/3V3/GND` 引出，未误接目标 SWD |
| ESP 启动 | `EN` 有 10k 上拉和 1uF 到地，`IO9/BOOT` 默认电平正确 |
| ESP 通信 | SPI 全部有串阻焊盘，`ESP_IRQ` 有明确默认电平 |
| SDIO 预留 | 6 根线都有串阻、上拉焊盘和测试点，未和 SPI 硬冲突 |
| 目标 SWD | `SWCLK/SWDIO/NRST/VTREF/GND` 线序清晰，串阻和 ESD 靠近正确位置 |
| 目标 UART | TX/RX 方向丝印清楚，5V 不进入 CH32 GPIO |
| 目标供电 | 5V/3.3V 输出默认关闭或不焊，不会误给目标板反灌 |
| RF | WROOM-1U 外接天线远离电源电感和金属接口；WROOM-1 板载天线有净空 |
| 电源 | ESP 3.3V 支路有 10uF 以上电容，DCDC 电感远离 RF 和晶振 |
| 测试点 | 3V3、GND、ESP_EN、ESP_BOOT、SPI_CLK、SWCLK、SWDIO、VTREF 可测 |

## 12. 推荐定版结论

第一版 PCB 建议按下面方式定版：

| 决策 | 推荐 |
|---|---|
| 主控 | `CH32V307RCT6` |
| 无线 | `ESP32-C6-WROOM-1U-N8`，外接天线 |
| PCB | 4 层长条形，USB 左、CH32 中、ESP 右上、目标接口右下 |
| 主控到 ESP | SPI 必连，SDIO 预留，UART0 必留 |
| 目标接口 | 6Pin SWD + 5Pin UART + 可选 Cortex 10Pin |
| 电平 | 第一版默认 3.3V SWD/UART，低压/5V 逻辑只预留增强位 |
| 电源 | USB 5V 输入，板上 3.3V 至少按 1A 级设计，目标供电默认关闭 |
| 调试 | WCH-Link、ESP UART0、ESP EN/BOOT、SWD 波形测试点全部保留 |

这套布局的核心目标不是把板子做得最小，而是让第一版容易焊、容易测、容易改。只要 USB、电源、CH32、ESP、目标接口四个区域不互相挤压，后续无论是把 SPI 提速、启用 SDIO，还是加目标电平转换，都有继续迭代的空间。
