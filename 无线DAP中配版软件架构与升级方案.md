# 无线 DAP 中配版软件架构与升级方案

日期：2026-05-28

## 1. 文档目标

本文面向 `CH32V307RCT6 + ESP32-C6-WROOM-1U` 中配硬件，定义第一版到后续提速版的软件方向。重点回答以下问题：

| 问题 | 结论 |
|---|---|
| 是否需要 Bootloader | 需要。CH32 和 ESP 都要有可靠升级路径，避免量产后必须拆机或接下载器 |
| CH32 是否做完整 A/B | 不建议。CH32V307RCT6 常见资源只有 256KB Flash，片内容量不适合放两个完整应用 |
| ESP 是否做 A/B OTA | 建议。ESP32-C6 模组有外部 Flash，ESP-IDF 原生支持 OTA 分区和回滚 |
| CH32 新固件放哪里 | 优先暂存在 ESP32-C6 Flash，再由 ESP 通过 UART/SPI 投递给 CH32 Bootloader |
| 第一版主链路 | USB CMSIS-DAP v1/v2 + CDC + CH32-ESP SPI + ESP 无线 |
| 软件核心原则 | CH32 负责确定性实时任务，ESP 负责无线、配对、OTA、文件缓存和远程管理 |

## 2. 联网资料结论

| 资料方向 | 结论 | 对本项目的影响 |
|---|---|---|
| Arm CMSIS-DAP 官方固件 | CMSIS-DAP 通过 `DAP_config.h` 适配硬件，核心命令包括 `DAP_Transfer`、`DAP_TransferBlock`、`DAP_SWJ_Clock` | CH32 应移植 CMSIS-DAP 命令层和 SWD GPIO 层，不应从零定义调试协议 |
| DAPLink 架构 | DAPLink 通常包含 Bootloader、Interface、USB MSC/CDC/CMSIS-DAP 等模块 | 第一版不建议完整搬 DAPLink，但可以借鉴“Bootloader + Interface 应用”分层 |
| ESP-IDF OTA | ESP-IDF 支持 OTA app 分区、OTA data 分区和回滚确认机制 | ESP32-C6 应使用官方 OTA 机制，负责自身无线升级和失败回滚 |
| ESP-NOW / Wi-Fi | ESP-NOW 适合低延迟点对点，Wi-Fi UDP/TCP 适合更大包和配置网络；ESP-NOW v2 支持更大数据体但要考虑兼容性 | 第一版可用固定信道私有可靠帧，后续可切 UDP/私有协议 |
| ESP-Hosted | Espressif 提供通过 SPI/SDIO/UART 让 ESP 作为无线协处理器的思路 | 本项目不必完整跑 ESP-Hosted 网络栈，但应借鉴“主机-协处理器命令/数据通道”设计 |
| TinyUSB / USB 设备栈 | TinyUSB 支持 HID、CDC、MSC、Vendor 等 USB Device Class | 如果 CH32 移植可控，可考虑 TinyUSB；否则第一版优先使用 WCH 官方 USBHS 例程改造 |
| WCH CH32 生态 | CH32V307 有 WCH 官方 EVT 例程、USBHS、UART、IAP/ISP 相关示例 | CH32 底层驱动应先基于 WCH EVT 跑通，再抽象出项目自己的 HAL |

## 3. 总体软件分工

### 3.1 两颗芯片职责

| 芯片 | 固件身份 | 主要职责 | 不建议承担 |
|---|---|---|---|
| `CH32V307RCT6` | 实时主控 / USB 设备 / SWD 执行器 | USB CMSIS-DAP、USB CDC、目标 SWD、目标 UART、VTREF 检测、与 ESP 交换帧、CH32 自身 Bootloader | Wi-Fi 协议栈、大文件 OTA 缓存、网页配置、复杂加密握手 |
| `ESP32-C6-WROOM-1U` | 无线协处理器 / OTA 管理器 | Wi-Fi/ESP-NOW、配对、链路维护、加密、ESP 自身 OTA、CH32 固件暂存、网页配置、远程日志 | 直接生成目标 SWD 波形、直接承接 USB CMSIS-DAP 主接口 |

一句话原则：`CH32V307RCT6` 是调试器本体，`ESP32-C6` 是无线网卡和 OTA 管家。目标 SWD 的实时性、方向切换、ACK 采样、NRST 控制都放在 CH32 上，ESP 只转发“已经打包好的 DAP/UART/控制帧”。

| 设计问题 | 推荐做法 | 原因 |
|---|---|---|
| 谁枚举 USB CMSIS-DAP | CH32 | CH32 有 USB High-Speed，适合做电脑侧调试器接口 |
| 谁生成 SWCLK/SWDIO | CH32 | SWD 需要确定性时序，不能经过无线链路 |
| 谁负责无线重传 | ESP32-C6 | ESP 有 Wi-Fi/ESP-NOW 协议栈和更大的 Flash/NVS |
| 谁保存大固件包 | ESP32-C6 | CH32 片内 Flash 小，不适合暂存完整升级包 |
| 谁判断 VTREF | CH32 | VTREF 直接影响是否允许驱动目标 SWD |
| 谁控制 CH32 升级恢复 | ESP32-C6 + CH32 Bootloader | ESP 暂存固件，CH32 Bootloader 负责写片内 App |

### 3.2 电脑端与板端角色

同一块 PCB 可以通过固件配置区或按键进入角色选择。建议第一版先用编译宏或 NVS/Flash 配置固定角色，后续再做运行时切换。

| 角色 | CH32 工作 | ESP 工作 |
|---|---|---|
| 电脑端 | 枚举 USB CMSIS-DAP + CDC，转发 DAP/UART/控制帧到 ESP | 与板端无线连接，发送电脑端请求，接收板端响应 |
| 板端 | 接收 ESP 转发的 DAP 请求，本地执行 SWD，桥接目标 UART | 与电脑端无线连接，转发 DAP/UART/控制帧 |
| 工厂测试端 | USB CDC/厂家命令、硬件自检、烧录配置 | 配对测试、射频测试、版本写入 |
| 升级模式 | 进入 CH32 Bootloader 接收固件 | 暂存固件、校验、控制 CH32 复位进 Bootloader |

### 3.3 CH32 与 ESP 硬件链路怎么用

第一版建议以 SPI 为主通道，UART 为救援和日志通道，EN/BOOT/IRQ 作为控制通道，SDIO 只预留不启用。

| 连接 | 推荐用途 | 第一版策略 |
|---|---|---|
| `ESP_SPI_CS/SCK/MISO/MOSI` | CH32 与 ESP 的主数据通道 | 必须启用，承载 DAP、UART、控制、升级分片 |
| `ESP_IRQ` | ESP 通知 CH32 有新帧 | 必须启用，避免 CH32 频繁轮询 |
| `ESP_EN_CTRL` | CH32 复位 ESP | 必须保留，用于 ESP 卡死恢复 |
| `ESP_BOOT_CTRL` | CH32 控制 ESP 进入下载模式 | 必须保留，用于出厂和救援 |
| `ESP_UART_TXD/RXD` | ESP 日志、救援下载、早期调试 | 第一版必须能用，速度要求不高 |
| `ESP_SDIO_*` | 后续高速通道 | PCB 预留，固件第二阶段以后再评估 |

推荐数据路径如下：

```text
电脑 Keil / pyOCD / 串口助手
  │ USB CMSIS-DAP / CDC
  ▼
CH32 电脑端应用
  │ SPI 本地帧
  ▼
ESP32-C6 电脑端
  │ Wi-Fi / ESP-NOW 可靠帧
  ▼
ESP32-C6 板端
  │ SPI 本地帧
  ▼
CH32 板端应用
  │ SWCLK / SWDIO / NRST / UART
  ▼
目标 MCU
```

## 4. Flash 与 Bootloader 规划

### 4.1 CH32 Flash 规划

CH32V307RCT6 片内 Flash 较小，建议采用“小 Bootloader + 单 App + 配置区”的结构，而不是片内双 App。

| 区域 | 建议大小 | 用途 |
|---|---:|---|
| `CH32_BOOT` | 16KB~24KB | 最小 Bootloader，支持 UART/SPI 升级、CRC 校验、跳转 App |
| `CH32_APP` | 216KB~232KB | 主应用：USB、DAP、CDC、SPI、SWD、UART、协议栈 |
| `CH32_CONFIG` | 4KB~8KB | 角色、版本、设备 ID、配对摘要、升级状态、崩溃计数 |
| `CH32_BOOT_FLAG` | 1KB~4KB | Bootloader 和 App 之间的启动原因、升级命令、回滚标记 |

说明：最终大小必须按链接脚本、WCH Flash 页大小和实际编译产物调整。第一版应先保守给 Bootloader 24KB，避免后续加密校验和协议解析放不下。

### 4.2 CH32 Bootloader 功能

| 功能 | 是否第一版需要 | 说明 |
|---|---|---|
| App 有效性检查 | 必须 | 启动前检查 App 魔数、长度、版本、CRC32 |
| 串口升级 | 必须 | 通过 CH32 调试 UART 或 ESP UART 通道接收固件 |
| SPI 升级 | 建议 | CH32 作为 SPI 从机或主机读取 ESP 暂存固件，后续提速 |
| USB DFU | 可选 | CH32 USBHS 稳定后再做，第一版不要阻塞主功能 |
| 回滚 | 必须有最低限度 | 若新 App 未确认成功，允许请求 ESP 重新投递上一版 |
| 加密验签 | 后续增强 | 第一版先 CRC32 + 版本检查，量产前再加签名 |
| 工厂恢复 | 必须 | 长按按键或 BOOT0 组合进入 Bootloader，不跳 App |

### 4.3 CH32 启动流程

```text
上电/复位
  │
  ▼
CH32 Bootloader
  │
  ├─ 检查强制升级按键 / BOOT 标记
  │      └─ 是：进入升级接收模式
  │
  ├─ 检查 App 头部、长度、CRC32、向量表
  │      └─ 无效：进入升级接收模式
  │
  ├─ 检查 pending_confirm 标记
  │      └─ 超过启动失败次数：请求 ESP 回滚或停留 Bootloader
  │
  └─ 跳转 CH32_APP
```

### 4.4 ESP32-C6 Flash 规划

ESP32-C6 使用 ESP-IDF 官方分区表，建议至少包含：

| 分区 | 用途 |
|---|---|
| `nvs` | 配对信息、设备 ID、角色、信道、密钥摘要 |
| `otadata` | ESP-IDF OTA 状态 |
| `app_factory` | 出厂固件，可选 |
| `ota_0` | ESP 当前/候选应用 |
| `ota_1` | ESP OTA 备用应用 |
| `ch32_fw_a` | CH32 固件暂存 A |
| `ch32_fw_b` | CH32 固件暂存 B 或上一版备份 |
| `log_store` | 关键升级日志、错误码、最近崩溃原因 |

ESP 的 OTA 和 CH32 的升级应拆开管理：ESP 先保证自己能升级和回滚，再负责把 CH32 固件安全送到 CH32 Bootloader。

## 5. 固件镜像格式

### 5.1 统一固件包

后续上位机或网页上传的固件包建议采用统一容器，里面可以同时包含 CH32 App 和 ESP App 信息。

| 字段 | 说明 |
|---|---|
| `magic` | 固定魔数，例如 `WDAPFW` |
| `format_version` | 固件包格式版本 |
| `target_chip` | `CH32V307`、`ESP32C6` 或 `BUNDLE` |
| `hardware_rev` | 硬件版本匹配 |
| `role_mask` | 电脑端、板端、通用 |
| `fw_version` | 固件版本号 |
| `image_size` | 镜像长度 |
| `image_crc32` | 镜像 CRC32 |
| `image_sha256` | 镜像 SHA256，后续验签使用 |
| `min_boot_version` | 最低 Bootloader 版本 |
| `payload` | 固件正文 |

### 5.2 CH32 App 头部

CH32 App 起始位置建议放一个固定头部，Bootloader 先读头部再决定是否跳转。

```c
/*
 * CH32 应用镜像头部。
 * 该结构放在 CH32_APP 区域起始位置，用于 Bootloader 判断应用是否完整、是否匹配当前硬件。
 * Bootloader 只依赖这个头部和 CRC，不依赖主应用内部变量，避免升级失败时无法恢复。
 */
typedef struct __attribute__((packed)) {
    uint32_t magic;          // 固定魔数，用于识别有效 App
    uint16_t header_version; // 头部格式版本，便于后续兼容
    uint16_t header_size;    // 头部长度，Bootloader 用于跳过扩展字段
    uint32_t image_size;     // App 镜像总长度，不包含空白 Flash
    uint32_t image_crc32;    // App 镜像 CRC32，用于完整性校验
    uint32_t vector_addr;    // App 向量表地址，跳转前设置 MTVEC/向量入口
    uint32_t fw_version;     // 固件版本，用于防止误降级
    uint32_t hw_mask;        // 支持的硬件版本掩码
    uint32_t flags;          // 标志位，例如是否需要首次启动确认
} ch32_app_header_t;

_Static_assert(sizeof(ch32_app_header_t) == 32, "ch32_app_header_t size error");
```

这里建议使用 `__attribute__((packed))`，因为镜像头会固化在 Flash 和固件包中，必须保证字节布局稳定。注意：`packed` 只解决结构体填充字节问题，不解决大小端、非对齐访问和跨编译器语义问题。Bootloader 读取外部固件包时，推荐先从 `uint8_t buffer[]` 中按小端解析字段，校验通过后再复制到本地结构体，避免直接把未对齐地址强转成结构体指针。

### 5.3 协议结构体对齐规则

| 场景 | 是否使用 `packed` | 说明 |
|---|---|---|
| Flash 中固定镜像头 | 使用 | Bootloader 和 App 必须看到同样布局 |
| SPI/UART/无线帧头 | 使用 | 双芯片、双固件、后续上位机工具都要解析 |
| MCU 内部运行状态结构体 | 不使用 | 默认对齐访问更快，也更安全 |
| 高频 DMA 缓冲描述符 | 按外设要求 | 以 CH32/ESP 外设手册要求为准 |

协议结构体还必须配合以下规则：

| 规则 | 原因 |
|---|---|
| 所有字段使用 `uint8_t/uint16_t/uint32_t` 等定宽类型 | 避免不同编译器下类型大小变化 |
| 所有多字节字段固定小端序 | 避免后续上位机或其他 MCU 解析歧义 |
| 每个协议结构体加 `_Static_assert(sizeof(...))` | 编译期发现布局变化 |
| 帧头包含 `version/header_size/payload_len/crc` | 便于后续兼容升级 |
| 接收外部数据时先校验长度再解析 | 防止错误帧导致越界访问 |

## 6. CH32 主应用软件分层

### 6.1 推荐分层

| 层级 | 模块 | 作用 |
|---|---|---|
| BSP/HAL | `bsp_clock`、`bsp_gpio`、`bsp_usbhs`、`bsp_spi`、`bsp_uart`、`bsp_flash`、`bsp_adc` | 封装 WCH 底层驱动，隔离寄存器和官方库差异 |
| Driver | `drv_usb_dap`、`drv_usb_cdc`、`drv_esp_link`、`drv_swd_io`、`drv_target_uart`、`drv_vtref` | 面向业务的硬件驱动 |
| Protocol | `wdap_frame`、`dap_router`、`uart_tunnel`、`upgrade_proto`、`diag_proto` | 统一帧、DAP 转发、串口通道、升级协议、诊断协议 |
| Service | `cmsis_dap_service`、`radio_bridge_service`、`target_service`、`upgrade_service`、`pairing_service` | 业务状态机 |
| App | `role_pc`、`role_probe`、`factory_test` | 根据角色组合不同服务 |

### 6.2 任务划分

如果第一版使用裸机超级循环，也要按任务思想组织；后续可切换到 RTOS。

| 任务/循环 | 优先级 | 职责 |
|---|---|---|
| `usb_poll_task` | 高 | 处理 USBHS 中断后的包收发、CMSIS-DAP 请求、CDC 数据 |
| `esp_link_task` | 高 | 处理 CH32 与 ESP 的 SPI/UART 数据帧 |
| `dap_exec_task` | 最高 | 板端执行 SWD 事务，短时间进入临界区 |
| `uart_bridge_task` | 中 | 处理 USB CDC 与目标 UART 的双向缓冲 |
| `upgrade_task` | 中 | 处理升级命令、写标志、准备重启 |
| `diag_task` | 低 | LED、日志、统计、心跳 |

关键规则：

| 规则 | 原因 |
|---|---|
| SWD 位操作期间禁止长时间被 USB/ESP 打断 | SWDIO turnaround、ACK 采样、SWCLK 周期需要稳定 |
| USB 接收和 ESP 收发使用环形缓冲 | 避免无线短时阻塞导致 USB 丢包 |
| DAP 队列优先级高于 UART 队列 | Keil 超时比串口日志丢延迟更严重 |
| 升级任务不能在 SWD 执行中擦写 Flash | Flash 擦写会影响实时性和稳定性 |

## 7. ESP32-C6 软件分层

### 7.1 推荐分层

| 层级 | 模块 | 作用 |
|---|---|---|
| ESP-IDF Driver | Wi-Fi、ESP-NOW、NVS、OTA、SPI Slave/Master、UART、GPIO | 使用官方能力，不重复造底层 |
| Link Driver | `ch32_link_spi`、`ch32_link_uart`、`wireless_link` | 管理 CH32 本地链路和无线链路 |
| Protocol | `wdap_frame`、`reliable_window`、`pairing_proto`、`upgrade_proto` | 和 CH32 共享帧格式 |
| Service | `radio_service`、`pairing_service`、`ota_service`、`ch32_update_service`、`web_config_service` | 无线、配对、升级、配置 |
| App | `pc_side_role`、`target_side_role`、`factory_role` | 根据角色决定转发方向和策略 |

### 7.2 ESP 任务划分

| 任务 | 职责 |
|---|---|
| `wireless_rx_task` | 接收对端无线帧，校验 CRC/序号，投递给业务队列 |
| `wireless_tx_task` | 按优先级发送 DAP、UART、控制、ACK 帧 |
| `ch32_link_task` | 和 CH32 通过 SPI/UART 交换本地帧 |
| `pairing_task` | 按键配对、设备 ID 交换、信道和密钥保存 |
| `ota_task` | ESP 自身 OTA，下载、校验、设置 OTA 分区 |
| `ch32_fw_task` | 接收并暂存 CH32 固件，触发 CH32 Bootloader 升级 |
| `diag_task` | RSSI、丢包率、重传次数、错误码、LED 状态 |

## 8. CH32 与 ESP 本地协议

### 8.1 统一帧格式

CH32-ESP 本地链路和 ESP-ESP 无线链路建议使用同一套上层帧头，减少转换逻辑。

```c
/*
 * 无线 DAP 统一传输帧头。
 * 该帧头用于 USB DAP、UART、控制、升级、诊断等所有业务。
 * CH32-ESP 本地链路和 ESP-ESP 无线链路共用该结构，区别只在底层承载方式。
 */
typedef struct __attribute__((packed)) {
    uint16_t magic;       // 固定魔数，例如 0x5744，表示 Wireless DAP
    uint8_t  version;     // 协议版本
    uint8_t  type;        // 帧类型
    uint16_t seq;         // 帧序号，用于 ACK、重传、请求响应匹配
    uint8_t  flags;       // 标志位，例如 NEED_ACK、FRAG、ENCRYPTED
    uint8_t  priority;    // 优先级，DAP 高于 UART，控制高于普通日志
    uint16_t frag_id;     // 分片组 ID
    uint8_t  frag_idx;    // 当前分片序号
    uint8_t  frag_cnt;    // 总分片数量
    uint16_t payload_len; // 负载长度
    uint16_t header_crc;  // 头部 CRC，快速发现头部错误
    uint32_t payload_crc; // 负载 CRC32，用于升级和大包校验
} wdap_frame_header_t;

_Static_assert(sizeof(wdap_frame_header_t) == 20, "wdap_frame_header_t size error");
```

接收帧时不要直接做下面这种强转：

```c
/*
 * 不推荐：外部 buffer 可能未对齐，长度也可能不足。
 */
const wdap_frame_header_t *hdr = (const wdap_frame_header_t *)rx_buffer;
```

更稳的做法是：先检查 `rx_len >= sizeof(wdap_frame_header_t)`，再用安全读取函数按小端序解析字段；或者 `memcpy` 到本地对齐变量后再访问。这样在 CH32、ESP 和未来 PC 上位机之间都更稳。

### 8.2 帧类型

| 类型 | 方向 | 用途 |
|---|---|---|
| `WDAP_DAP_REQ` | 电脑端 CH32 -> 板端 CH32 | CMSIS-DAP 请求 |
| `WDAP_DAP_RSP` | 板端 CH32 -> 电脑端 CH32 | CMSIS-DAP 响应 |
| `WDAP_UART_DATA` | 双向 | 无线串口数据 |
| `WDAP_CTRL` | 双向 | 设置角色、设置 SWD 时钟、设置 UART 参数 |
| `WDAP_HEARTBEAT` | 双向 | 链路在线、RSSI、延迟、版本 |
| `WDAP_ACK` | 双向 | 应用层确认 |
| `WDAP_NACK` | 双向 | CRC 错误、忙、分片缺失 |
| `WDAP_UPG_META` | 上位机/ESP -> 目标芯片 | 固件元数据 |
| `WDAP_UPG_DATA` | 上位机/ESP -> 目标芯片 | 固件分片 |
| `WDAP_UPG_COMMIT` | 上位机/ESP -> 目标芯片 | 固件校验通过后提交 |
| `WDAP_DIAG` | 双向 | 诊断日志和错误码 |

### 8.3 优先级

| 优先级 | 业务 | 规则 |
|---|---|---|
| P0 | ACK/NACK、心跳超时、升级提交 | 必须立即处理 |
| P1 | DAP 请求/响应 | 下载和调试优先 |
| P2 | UART 数据 | 可合包，可短时延迟 |
| P3 | 诊断日志、网页状态 | 不影响核心功能 |

## 9. USB 设备设计

### 9.1 第一版 USB 组合

| USB 接口 | 第一版建议 | 说明 |
|---|---|---|
| CMSIS-DAP v1 HID | 必须 | 兼容性好，Windows 免驱概率高，先跑通 Keil |
| CDC ACM | 必须 | 无线串口、日志、工厂命令 |
| Vendor/Bulk | 建议预留 | 后续做 CMSIS-DAP v2 或私有高速下载 |
| MSC 拖拽烧录 | 不建议第一版做 | DAPLink 的 MSC/Flash Algorithm 复杂，和当前目标不一致 |

### 9.2 CMSIS-DAP 路线

| 阶段 | 功能 |
|---|---|
| V0 | `DAP_Info`、`DAP_Connect`、`DAP_Disconnect`、`DAP_SWJ_Clock`、`DAP_SWJ_Sequence` |
| V1 | `DAP_Transfer`、`DAP_TransferBlock`，能读 IDCODE 和下载 STM32 blink |
| V2 | CMSIS-DAP v2 Bulk，增大包队列和并发处理 |
| V3 | DAP 批处理优化，减少无线往返 |
| V4 | 私有高速下载命令，让板端本地执行 Flash Loader |

## 10. 无线链路策略

### 10.1 第一版建议

| 项目 | 建议 |
|---|---|
| 无线模式 | ESP-NOW 或固定信道 Wi-Fi 私有 UDP 二选一，第一版优先低延迟和简单配对 |
| 包可靠性 | 应用层 ACK、超时重传、序号去重 |
| DAP 模式 | 严格请求-响应，不乱序执行 |
| UART 模式 | 环形缓冲、定时合包、软件水位线 |
| 心跳 | 100ms~500ms 周期，根据调试状态调整 |
| 断线处理 | DAP 返回错误，CDC 保持端口但提示链路断开 |

### 10.2 后续提速

| 提速点 | 说明 |
|---|---|
| SPI DMA | CH32 与 ESP 本地链路先提速，避免无线外的瓶颈 |
| SDIO | PCB 已预留，驱动成熟后切换为高速主通道 |
| 窗口 ACK | 对 UART 和升级数据启用窗口发送，DAP 仍保持顺序一致 |
| DAP 批处理 | 合并多个 DP/AP 操作，减少无线 RTT |
| Vendor Command | 给私有高速下载和远程配置留入口 |

## 11. 升级路径设计

### 11.1 升级入口

| 入口 | 可升级对象 | 第一版建议 |
|---|---|---|
| USB CDC 工具 | CH32 App、ESP App | 必须支持，最可控 |
| ESP 网页配置页 | ESP App、CH32 App | 后续支持，适合用户体验 |
| 无线对端转发 | 板端 CH32/ESP | 建议支持，方便两端成套升级 |
| CH32 BOOT 按键 | CH32 App | 必须支持，救砖 |
| ESP USB/UART 下载 | ESP App | 必须预留，救砖 |

### 11.2 ESP 自身 OTA 流程

```text
收到 ESP 固件包
  │
  ├─ 校验包头、硬件版本、长度、CRC/SHA
  ├─ 写入 ESP-IDF OTA 分区 ota_0/ota_1
  ├─ 设置下次启动分区
  ├─ 重启 ESP
  ├─ 新固件启动后执行自检
  └─ 自检通过后调用确认，失败则回滚
```

### 11.3 CH32 远程升级流程

```text
上位机/网页上传 CH32 固件到 ESP
  │
  ├─ ESP 校验固件包头、长度、CRC32、硬件版本
  ├─ ESP 写入 ch32_fw_a 或 ch32_fw_b 暂存区
  ├─ ESP 通知 CH32 App 准备升级
  ├─ CH32 App 写入 BOOT_FLAG：进入 Bootloader
  ├─ ESP 控制 CH32 复位
  ├─ CH32 Bootloader 启动，向 ESP 请求固件分片
  ├─ CH32 擦除 CH32_APP 区并按分片写入
  ├─ CH32 Bootloader 校验 App CRC32
  ├─ 校验通过后设置 pending_confirm 并跳转 App
  ├─ CH32 App 完成 USB/ESP/SWD 基础自检
  └─ CH32 App 写入 confirm 标记，升级完成
```

### 11.4 失败处理

| 失败点 | 处理 |
|---|---|
| ESP 下载固件失败 | 保持旧 ESP App，不改 OTA 分区 |
| CH32 固件包 CRC 错 | ESP 拒绝升级，不复位 CH32 |
| CH32 写 Flash 中断电 | 下次启动停留 Bootloader，等待 ESP 重新投递 |
| CH32 新 App 启动失败 | Bootloader 根据 pending 标记和失败计数进入升级模式 |
| ESP 新 App 启动失败 | ESP-IDF OTA 回滚到旧分区 |
| 两端版本不兼容 | 协议握手失败后进入兼容模式，只允许升级和诊断 |

## 12. 配置与状态管理

### 12.1 设备配置

| 配置项 | 保存位置 | 说明 |
|---|---|---|
| 设备 ID | ESP NVS + CH32 CONFIG | 成套配对和防串扰 |
| 角色 | ESP NVS + CH32 CONFIG | 电脑端/板端 |
| 对端 ID | ESP NVS | 已配对设备 |
| 信道 | ESP NVS | 固定信道降低连接时间 |
| 加密密钥摘要 | ESP NVS | 后续加密认证 |
| SWD 默认频率 | CH32 CONFIG | 例如 100kHz、500kHz、1MHz |
| UART 默认参数 | CH32 CONFIG | 默认 115200 8N1 |
| 硬件版本 | CH32 CONFIG + ESP NVS | 防止刷错固件 |

### 12.2 运行状态

| 状态 | 用途 |
|---|---|
| `BOOT_REASON` | 判断是普通启动、升级启动、异常复位 |
| `LINK_STATE` | 未配对、已配对、连接中、在线、弱信号、断开 |
| `DAP_STATE` | 空闲、连接目标、下载中、调试中、错误 |
| `UPGRADE_STATE` | 空闲、接收中、校验中、写入中、待确认、失败 |
| `TARGET_STATE` | 无 VTREF、目标已上电、SWD 已连接、目标复位中 |

## 13. 错误码与诊断

第一版就要定义错误码，否则无线和升级问题很难排查。

| 错误码范围 | 模块 | 示例 |
|---|---|---|
| `0x0001~0x00FF` | 系统启动 | App CRC 错、Boot 标记异常 |
| `0x0100~0x01FF` | USB | 枚举失败、端点堵塞 |
| `0x0200~0x02FF` | ESP 本地链路 | SPI 超时、帧 CRC 错、IRQ 卡死 |
| `0x0300~0x03FF` | 无线 | 配对失败、心跳超时、重传过多 |
| `0x0400~0x04FF` | DAP/SWD | WAIT 超限、FAULT、IDCODE 读取失败 |
| `0x0500~0x05FF` | UART | 缓冲溢出、波特率不支持 |
| `0x0600~0x06FF` | 升级 | 固件包无效、写 Flash 失败、回滚触发 |

LED 建议：

| LED | 状态 |
|---|---|
| Power | 上电常亮 |
| Link | 未配对慢闪，连接中快闪，在线常亮 |
| DAP | DAP 请求时闪烁，错误时三连闪 |
| UART | 串口数据时闪烁 |
| Upgrade | 升级中呼吸灯或固定节奏闪烁 |

## 14. 开发阶段路线

推荐严格按“先 CH32 本体，再 ESP 协处理，再无线闭环”的顺序推进。不要一开始就同时调 USB、Wi-Fi、SWD、OTA，否则问题会互相掩盖。

| 阶段 | 目标 | 验收标准 |
|---|---|---|
| P0 CH32 最小系统 | CH32 时钟、串口、Flash、Bootloader 跳转 | Bootloader 能跳 App，App 能回写版本和启动确认 |
| P1 CH32 USB | USBHS 枚举 HID/CDC | Windows 识别 CMSIS-DAP 名称和 COM 口 |
| P2 CH32 SWD | 本地读目标 IDCODE | 逻辑分析仪确认 SWCLK/SWDIO/turnaround 正确 |
| P3 ESP 最小系统 | ESP Wi-Fi/ESP-NOW、NVS、OTA | ESP 可 OTA 升级并回滚 |
| P4 CH32-ESP 本地链路 | SPI/UART 帧收发 | 1 万帧 CRC 正确，无死锁 |
| P5 无线 DAP 闭环 | 电脑端到板端 DAP 请求响应 | Keil/pyOCD 能读目标 IDCODE |
| P6 无线串口 | CDC 到目标 UART 双向桥接 | 115200 连续 10 分钟稳定 |
| P7 CH32 远程升级 | ESP 暂存并投递 CH32 固件 | 中断电后能恢复升级，不变砖 |
| P8 性能优化 | CMSIS-DAP v2、SPI DMA、DAP 批处理 | 下载速度进入中配 V1/V2 目标 |

### 14.1 第一轮最小闭环建议

| 顺序 | 只做什么 | 不做什么 | 验收 |
|---|---|---|---|
| 1 | CH32 Bootloader + App 跳转 | 不接 ESP、不做 USB | 上电能跳 App，按键能停 Bootloader |
| 2 | CH32 USB CDC | 不做 CMSIS-DAP | PC 出现 COM，能回显版本号 |
| 3 | CH32 本地 SWD | 不做无线 | 能读目标 DP IDCODE |
| 4 | ESP 最小固件 | 不接无线对端 | UART 打印版本，NVS 可保存角色 |
| 5 | CH32-ESP SPI 帧 | 不走 Wi-Fi | 1 万帧收发 CRC 正确 |
| 6 | 两个 ESP 无线心跳 | 不转 DAP | RSSI、延迟、丢包率可查询 |
| 7 | DAP 请求无线转发 | 不做 OTA | Keil/pyOCD 能读 IDCODE |
| 8 | CH32 远程升级 | 不做提速 | 升级断电后能恢复 |

## 15. 第一版最小可行软件范围

第一版不要一次性做满所有功能。建议最低可用版本定义如下：

| 模块 | 第一版范围 |
|---|---|
| CH32 Bootloader | UART 升级、App CRC、强制升级按键、跳转 App、启动确认 |
| CH32 USB | CMSIS-DAP HID v1、CDC ACM、基础厂家命令 |
| CH32 DAP | SWD 模式、读 IDCODE、`DAP_Transfer`、`DAP_TransferBlock` |
| CH32 目标 UART | CDC 到 UART 双向桥接，支持 115200 8N1 |
| ESP 无线 | 固定信道配对、可靠帧、心跳、基础重传 |
| ESP OTA | ESP 自身 OTA + 回滚 |
| CH32 远程升级 | ESP 暂存 CH32 固件，控制 CH32 进 Bootloader 并投递固件 |
| 诊断 | 版本查询、错误码查询、链路统计、LED 状态 |

## 16. 不建议第一版做的内容

| 功能 | 原因 |
|---|---|
| MSC 拖拽烧录 | DAPLink 的 MSD 和目标 Flash Algorithm 管理复杂，容易拖慢主线 |
| 完整 JTAG | 中配硬件和软件目标先聚焦 SWD |
| 低压/全电平自动适配 | 需要硬件增强和更多测试，第一版先 3.3V |
| 完整网页配置系统 | ESP 资源够，但第一版应先把链路和升级跑通 |
| 复杂加密签名 | 量产前必须做，第一版可先 CRC/SHA 和版本限制 |
| 多目标芯片私有高速下载 | 需要各家 Flash Loader，放在 CMSIS-DAP 稳定后 |

## 17. 推荐最终方向

| 决策 | 推荐 |
|---|---|
| 软件总架构 | `CH32 Bootloader + CH32 Interface App + ESP Wireless/OTA App` |
| CH32 升级 | 小 Bootloader，单 App，ESP 暂存固件并投递，失败后停留 Bootloader 等待恢复 |
| ESP 升级 | 使用 ESP-IDF OTA 双分区和回滚确认 |
| 主程序通信 | 统一 `wdap_frame` 帧格式，业务用类型和优先级区分 |
| USB | 第一版 HID CMSIS-DAP + CDC，后续加 v2 Bulk/Vendor |
| 无线 | 第一版可靠点对点帧，后续优化窗口 ACK、SDIO、批处理 |
| 目标侧 | CH32 本地执行 SWD，DAP 请求无线转发，禁止透明透传 SWD 波形 |
| 开发顺序 | 先 Bootloader 和本地 USB/SWD，再 ESP 链路，再无线闭环，最后做远程升级和提速 |

这个方向的关键好处是：CH32 只承担实时和 USB/DAP 核心功能，ESP 承担无线和大容量升级缓存；CH32 即使升级失败，也能通过 ESP 或串口重新投递固件；ESP 自己则依赖 ESP-IDF OTA 做回滚。这样比单纯“串口 Bootloader + 主程序”更适合两端式无线调试器，也给后续 OTA、批量升级和产品化留下空间。

## 18. 参考资料

| 资料 | 链接 |
|---|---|
| Arm CMSIS-DAP Firmware | https://arm-software.github.io/CMSIS-DAP/latest/dap_firmware.html |
| Arm CMSIS-DAP Transfer Commands | https://arm-software.github.io/CMSIS-DAP/latest/group__DAP__Transfer.html |
| DAPLink GitHub | https://github.com/ARMmbed/DAPLink |
| ESP-IDF OTA 文档 | https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/ota.html |
| ESP-IDF Partition Tables | https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/partition-tables.html |
| ESP-NOW 文档 | https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/network/esp_now.html |
| ESP-Hosted GitHub | https://github.com/espressif/esp-hosted |
| TinyUSB 文档 | https://docs.tinyusb.org/ |
| WCH CH32V307 官方资料仓库 | https://github.com/openwch/ch32v307 |
