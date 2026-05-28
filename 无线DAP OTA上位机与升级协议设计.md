# 无线 DAP OTA 上位机与升级协议设计

日期：2026-05-28

## 1. 文档目标

本文定义无线 DAP 中配版的 OTA 上位机方向、界面功能、升级协议、断点续传机制和防串口误触发机制。

核心目标：

| 目标 | 说明 |
|---|---|
| 做一个可维护的 OTA 上位机 | 第一版先快速可靠，后续再美化和产品化 |
| 严格区分 OTA 与无线串口 | 不能用户串口发了某些字节就误判为 OTA |
| 支持本机和对端升级 | 当前 USB 插入设备、无线对端设备都要能升级 |
| 支持 CH32 和 ESP 分别升级 | CH32 走 Bootloader，ESP 走 ESP-IDF OTA |
| 支持断点续传 | 中途 USB 断开、无线断开、软件关闭后可恢复 |
| 支持明确状态和错误码 | 用户必须知道卡在哪一步、为什么失败、能否继续 |

## 2. 上位机技术选型

### 2.1 推荐第一版：Python + PySide6 + pyserial

| 项目 | 推荐 |
|---|---|
| 编程语言 | Python 3.11+ |
| UI 框架 | PySide6 |
| 串口通信 | pyserial |
| 打包 | PyInstaller 或 Nuitka |
| 日志 | Python logging + UI 日志窗口 |
| 固件包解析 | Python `struct` + `hashlib` + `zlib.crc32` |

推荐理由：

| 原因 | 说明 |
|---|---|
| 串口调试快 | pyserial 操作 COM 口方便，适合协议频繁调整 |
| UI 够用 | PySide6 可以快速做稳定的桌面工具 |
| 跨平台 | Windows 是主目标，也能兼顾 Linux/macOS |
| 易调试 | 协议日志、分片重传、断点续传可以直接打印和保存 |
| 后续可迁移 | 协议层用纯 Python 写清楚后，未来可以迁移到 Rust/Tauri |

### 2.2 后续正式版备选

| 方案 | 适合阶段 | 优点 | 缺点 |
|---|---|---|---|
| `Python + PySide6` | 第一版和工程调试版 | 开发快、调试方便 | 打包体积偏大，UI 质感一般 |
| `Tauri + Rust + Web UI` | 正式产品版 | 体积小、界面现代、协议层安全 | 前期开发慢，串口/USB 权限处理更复杂 |
| `C# WPF/WinUI` | Windows 专用版 | Windows 体验好 | 跨平台弱 |
| `Electron + React` | 不推荐第一版 | 前端生态丰富 | 体积大，做烧录工具偏重 |

## 3. 上位机界面设计

OTA 工具属于工程工具，界面应安静、清晰、信息密度适中，不做营销式大卡片布局。

### 3.1 主界面布局

```text
┌──────────────────────────────────────────────────────────────┐
│ 顶部设备栏：COM口  刷新  连接  设备ID  本机版本  对端状态       │
├───────────────┬──────────────────────────────────────────────┤
│ 目标选择区     │ 固件包信息区                                  │
│ - 本机CH32     │ 文件路径 / 选择文件                            │
│ - 本机ESP      │ 目标芯片 / 版本 / 大小 / CRC / SHA256           │
│ - 对端CH32     │ 硬件版本匹配 / 最低Boot版本 / 签名状态          │
│ - 对端ESP      ├──────────────────────────────────────────────┤
│               │ 升级控制区                                    │
│               │ 检查版本  开始升级  暂停  恢复  取消  强制Boot  │
│               ├──────────────────────────────────────────────┤
│               │ 进度区                                        │
│               │ 当前阶段 / 总进度 / 分片进度 / 速度 / 重传次数 │
│               ├──────────────────────────────────────────────┤
│               │ 日志区                                        │
│               │ 协议日志 / 错误码 / 断点续传信息 / 保存日志     │
└───────────────┴──────────────────────────────────────────────┘
```

### 3.2 页面功能区

| 区域 | 必须功能 | 说明 |
|---|---|---|
| 设备连接栏 | COM 扫描、刷新、连接、断开、读取设备信息 | 第一版通过管理 CDC 串口连接 |
| 目标选择区 | `LOCAL_CH32`、`LOCAL_ESP`、`PEER_CH32`、`PEER_ESP` | 明确升级对象，避免刷错芯片 |
| 固件包区 | 选择 `.wdapfw`、解析包头、显示版本/大小/校验 | 不接受裸 `.bin` 直接升级，除非高级模式 |
| 兼容性检查 | 检查芯片、硬件版本、角色、最低 Bootloader | 不匹配时默认禁止升级 |
| 升级控制 | 开始、暂停、恢复、取消、强制 Bootloader | 操作必须有状态约束 |
| 进度显示 | 阶段、百分比、offset、速度、剩余时间 | 断点续传时显示从哪里继续 |
| 日志区 | 协议帧摘要、错误码、重传、状态切换 | 支持导出日志 |
| 高级设置 | 分片大小、窗口大小、降级允许、只校验不写入 | 默认折叠，避免误操作 |

### 3.3 状态颜色和交互

| 状态 | UI 表现 |
|---|---|
| 未连接 | 灰色状态，升级按钮禁用 |
| 已连接 | 显示设备 ID、角色、版本 |
| 固件匹配 | 显示可升级，开始按钮启用 |
| 固件不匹配 | 红色错误，必须高级模式才允许强制 |
| 传输中 | 显示进度条、速度、当前 offset |
| 暂停/断开 | 显示可恢复状态和最后确认 offset |
| 校验中 | 禁止断电提示，显示校验阶段 |
| 完成 | 显示新版本和确认状态 |
| 失败 | 显示错误码、可恢复/不可恢复、建议动作 |

## 4. 通道隔离原则

### 4.1 绝对不能靠串口内容识别 OTA

用户明确担心“无线串口发东西被误认为 OTA”。这个风险必须从设计上消灭。

禁止方案：

```text
用户无线串口 CDC
  │
  ├─ 扫描 payload 里有没有 OTA_MAGIC
  └─ 如果碰巧匹配就进入 OTA
```

这个方案不能用，因为普通串口数据是用户业务数据，可能包含任何字节序列。

### 4.2 推荐三层隔离

| 隔离层 | 推荐做法 | 目的 |
|---|---|---|
| USB 接口层 | `CDC0` 做无线串口，`CDC1` 做管理/OTA；后续可用 Vendor/Bulk | 物理 USB 接口上隔离 |
| 协议类型层 | OTA 只接受 `WDAP_OTA_*` 类型帧，串口只接受 `WDAP_UART_DATA` | 协议类型上隔离 |
| 状态机层 | 只有 `OTA_BEGIN` 成功并分配 `session_id` 后才接受 `OTA_DATA` | 状态上隔离 |

第一版建议：

| USB 接口 | 用途 | 说明 |
|---|---|---|
| `CDC0_USER_UART` | 用户无线串口 | 用户发什么都只当串口数据 |
| `CDC1_MGMT` | OTA、诊断、配置 | OTA 上位机只连接这个口 |
| `CMSIS_DAP_HID/BULK` | Keil/pyOCD 调试 | 不承载 OTA |

如果 CH32 USB 复合设备第一版只想做一个 CDC，也必须在产品说明中明确：升级时该 CDC 进入“管理模式”，用户串口暂停。但更推荐从一开始就做双 CDC，减少后续重构。

## 5. 协议分层

### 5.1 层次结构

```text
上位机 UI
  │
  ▼
OTA Session 层：开始、暂停、恢复、提交、取消
  │
  ▼
WDAP Host Frame 层：帧头、类型、target、session_id、seq、offset、CRC
  │
  ▼
CDC1 管理串口 / 后续 Vendor Bulk
  │
  ▼
CH32 管理协议入口
  │
  ├─ 本机 CH32 升级
  ├─ 本机 ESP 升级
  └─ 经 ESP 无线转发到对端升级
```

### 5.2 帧头设计

所有管理帧都使用固定帧头。OTA 与 UART 的区别由 USB 通道和 `type` 字段共同决定，不能靠 payload 猜。

```c
/*
 * 上位机到设备的管理帧头。
 * 该帧头只用于管理通道 CDC1 或后续 Vendor/Bulk，不用于用户无线串口 CDC0。
 * 所有多字节字段固定使用小端序，接收端必须先校验长度、magic、header_crc，再处理 payload。
 */
typedef struct __attribute__((packed)) {
    uint32_t magic;        // 固定为 0x50414457，即小端 "WDAP"
    uint8_t  version;      // 管理协议版本，第一版为 1
    uint8_t  type;         // 帧类型，例如 HELLO、OTA_BEGIN、OTA_DATA
    uint8_t  target;       // 升级目标：LOCAL_CH32、PEER_ESP 等
    uint8_t  flags;        // 标志位：NEED_ACK、LAST_CHUNK、ENCRYPTED 等
    uint32_t session_id;   // OTA 会话 ID，非 OTA 帧为 0
    uint32_t seq;          // 帧序号，用于 ACK 和重传
    uint32_t offset;       // OTA 分片偏移，非 OTA 帧为 0
    uint16_t payload_len;  // payload 长度
    uint16_t header_crc;   // 帧头 CRC16，计算时该字段按 0 处理
    uint32_t payload_crc;  // payload CRC32
} wdap_host_frame_t;

_Static_assert(sizeof(wdap_host_frame_t) == 28, "wdap_host_frame_t size error");
```

### 5.3 目标枚举

| target | 数值建议 | 含义 |
|---|---:|---|
| `LOCAL_CH32` | `0x01` | 当前 USB 连接设备的 CH32 |
| `LOCAL_ESP` | `0x02` | 当前 USB 连接设备的 ESP32-C6 |
| `PEER_CH32` | `0x11` | 无线对端设备的 CH32 |
| `PEER_ESP` | `0x12` | 无线对端设备的 ESP32-C6 |
| `BROADCAST_INFO` | `0xF0` | 查询本机和对端信息，不用于升级写入 |

### 5.4 帧类型

| 类型 | 方向 | 作用 |
|---|---|---|
| `HELLO` | 上位机 -> 设备 | 建立管理会话，读取协议能力 |
| `HELLO_RSP` | 设备 -> 上位机 | 返回协议版本、最大分片、能力位 |
| `DEVICE_INFO_REQ` | 上位机 -> 设备 | 请求设备信息 |
| `DEVICE_INFO_RSP` | 设备 -> 上位机 | 返回设备 ID、角色、CH32/ESP 版本 |
| `OTA_QUERY` | 上位机 -> 设备 | 查询是否有未完成升级，是否可恢复 |
| `OTA_QUERY_RSP` | 设备 -> 上位机 | 返回当前 OTA 状态、next_offset、session_id |
| `OTA_BEGIN` | 上位机 -> 设备 | 申请开始升级 |
| `OTA_BEGIN_RSP` | 设备 -> 上位机 | 返回是否允许、session_id、建议 chunk_size |
| `OTA_DATA` | 上位机 -> 设备 | 发送固件分片 |
| `OTA_ACK` | 设备 -> 上位机 | 确认已接收 offset 或窗口 |
| `OTA_STATUS` | 双向 | 查询或返回升级状态 |
| `OTA_VERIFY` | 上位机 -> 设备 | 请求设备校验完整固件 |
| `OTA_VERIFY_RSP` | 设备 -> 上位机 | 返回 CRC/SHA 校验结果 |
| `OTA_COMMIT` | 上位机 -> 设备 | 确认写入启动标记或触发 Bootloader |
| `OTA_RESULT` | 设备 -> 上位机 | 返回最终升级结果 |
| `OTA_ABORT` | 上位机 -> 设备 | 取消升级 |
| `DIAG_LOG` | 设备 -> 上位机 | 返回诊断日志 |
| `ERROR_RSP` | 设备 -> 上位机 | 返回错误码 |

用户无线串口数据只允许走 `CDC0_USER_UART` 和内部 `WDAP_UART_DATA`，不允许出现在管理 CDC 的 OTA 状态机里。

## 6. OTA 固件包格式

### 6.1 文件后缀

上位机默认只接受 `.wdapfw` 固件包。高级模式可以加载 `.bin`，但必须手动选择目标芯片和版本，不建议第一版开放。

### 6.2 固件包头

```c
/*
 * WDAP 固件包头。
 * 该头部由打包工具生成，上位机先解析并校验，再发送给设备。
 * payload 之后是实际固件镜像，CH32 和 ESP 的镜像格式可以不同，但外层包头统一。
 */
typedef struct __attribute__((packed)) {
    uint8_t  magic[6];          // 固定 "WDAPFW"
    uint16_t package_version;   // 包格式版本
    uint16_t header_size;       // 包头长度
    uint16_t target_chip;       // CH32V307 / ESP32C6
    uint16_t target_role;       // PC_SIDE / PROBE_SIDE / UNIVERSAL
    uint32_t hardware_rev_mask; // 支持的硬件版本掩码
    uint32_t fw_version;        // 固件版本
    uint32_t min_boot_version;  // 最低 Bootloader 版本
    uint32_t image_size;        // 固件镜像长度
    uint32_t image_crc32;       // 固件镜像 CRC32
    uint8_t  image_sha256[32];  // 固件镜像 SHA256
    uint32_t flags;             // 是否加密、是否签名、是否允许降级
} wdap_fw_header_t;
```

### 6.3 包校验顺序

| 顺序 | 检查 |
|---|---|
| 1 | 文件后缀和最小长度 |
| 2 | `magic == "WDAPFW"` |
| 3 | `package_version` 是否支持 |
| 4 | `target_chip` 是否匹配用户选择 |
| 5 | `hardware_rev_mask` 是否覆盖当前设备 |
| 6 | `min_boot_version` 是否满足 |
| 7 | `image_size` 是否等于实际 payload 长度 |
| 8 | `image_crc32` 是否正确 |
| 9 | `image_sha256` 是否正确 |
| 10 | 后续正式版校验签名 |

## 7. OTA 会话流程

### 7.1 正常升级流程

```text
上位机连接 CDC1
  │
  ├─ HELLO
  ├─ DEVICE_INFO_REQ
  ├─ 选择目标 target
  ├─ 解析 .wdapfw 并做本地校验
  ├─ OTA_QUERY(target, image_sha256)
  ├─ OTA_BEGIN(target, image_size, crc32, sha256, fw_version)
  ├─ 设备返回 session_id、chunk_size、next_offset
  ├─ OTA_DATA(offset=next_offset)
  ├─ 设备 OTA_ACK(next_offset)
  ├─ 循环发送直到 image_size
  ├─ OTA_VERIFY
  ├─ OTA_COMMIT
  └─ OTA_RESULT
```

### 7.2 CH32 升级流程

| 阶段 | 设备侧动作 |
|---|---|
| `OTA_BEGIN` | ESP 或 CH32 管理层确认固件目标是 CH32 |
| `OTA_DATA` | 固件先写入 ESP 暂存区，或本机 CH32 可直接写临时接收区/顺序转 Bootloader |
| `OTA_VERIFY` | ESP 对暂存固件做整包 CRC/SHA 校验 |
| `OTA_COMMIT` | ESP 通知 CH32 App 写 BootFlag，控制 CH32 复位进 Bootloader |
| Bootloader 写入 | CH32 Bootloader 从 ESP 请求分片，写入 `CH32_APP` |
| 启动确认 | CH32 新 App 启动后写确认标记 |

### 7.3 ESP 升级流程

| 阶段 | 设备侧动作 |
|---|---|
| `OTA_BEGIN` | ESP 确认目标是本机或对端 ESP |
| `OTA_DATA` | 写入 ESP-IDF OTA 备用分区 |
| `OTA_VERIFY` | ESP 校验 OTA 分区镜像 |
| `OTA_COMMIT` | 设置下次启动分区并重启 |
| 启动确认 | 新 ESP App 自检通过后调用确认；失败回滚 |

## 8. 断点续传设计

### 8.1 第一版续传模型

第一版建议使用顺序写入模型，只记录连续完成的 `next_offset`。这样实现简单，断线恢复可靠。

设备端保存：

| 字段 | 说明 |
|---|---|
| `valid` | 是否存在未完成会话 |
| `session_id` | OTA 会话 ID |
| `target` | 升级目标 |
| `image_size` | 固件总大小 |
| `image_crc32` | 固件 CRC32 |
| `image_sha256` | 固件 SHA256 |
| `chunk_size` | 分片大小 |
| `next_offset` | 下一个需要接收的偏移 |
| `state` | `RECEIVING / VERIFYING / READY_COMMIT / FAILED` |
| `last_error` | 最近错误码 |

恢复流程：

```text
上位机重新连接
  │
  ├─ HELLO
  ├─ OTA_QUERY(target, image_sha256)
  ├─ 设备返回 session_id、state、next_offset
  ├─ 上位机检查本地固件 SHA256 是否一致
  ├─ 一致：从 next_offset 继续 OTA_DATA
  └─ 不一致：提示用户重新开始或取消旧会话
```

### 8.2 后续增强：bitmap 缺块恢复

当无线链路和存储策略成熟后，可以把顺序写入升级为块位图：

| 字段 | 说明 |
|---|---|
| `block_size` | 固定块大小，例如 1024 字节 |
| `block_count` | 固件总块数 |
| `received_bitmap` | 每 bit 表示一个块是否收到 |
| `missing_list` | 设备返回缺失块列表 |

第一版不建议上来做 bitmap，因为 CH32 和 ESP 两侧都要维护更多状态，调试成本高。

## 9. OTA 状态机

| 状态 | 允许命令 | 说明 |
|---|---|---|
| `IDLE` | `OTA_BEGIN`、`OTA_QUERY` | 无升级任务 |
| `PREPARED` | `OTA_DATA`、`OTA_ABORT` | 已创建会话，等待数据 |
| `RECEIVING` | `OTA_DATA`、`OTA_STATUS`、`OTA_ABORT` | 正在接收分片 |
| `VERIFYING` | `OTA_STATUS` | 正在校验，不接受数据 |
| `READY_COMMIT` | `OTA_COMMIT`、`OTA_ABORT` | 固件完整，等待提交 |
| `COMMITTING` | `OTA_STATUS` | 正在写启动标记或重启 |
| `PENDING_CONFIRM` | `OTA_STATUS`、`CONFIRM` | 新固件启动后等待确认 |
| `DONE` | `OTA_QUERY` | 升级完成 |
| `FAILED` | `OTA_QUERY`、`OTA_ABORT`、`OTA_BEGIN` | 失败，可按错误类型决定恢复 |

严格规则：

| 规则 | 说明 |
|---|---|
| `OTA_DATA` 只在 `PREPARED/RECEIVING` 有效 | 防止普通数据触发写入 |
| `session_id` 必须匹配 | 防止旧包、乱包、误包 |
| `target` 必须匹配会话记录 | 防止 CH32/ESP 刷错 |
| `offset` 必须等于 `next_offset` | 第一版顺序写入模型更可靠 |
| `payload_crc` 必须正确 | 单片错误不写入 |
| `OTA_COMMIT` 必须显式发送 | 传完不等于启用新固件 |

## 10. ACK、超时与重传

### 10.1 第一版 ACK

| 项目 | 推荐 |
|---|---|
| 分片大小 | 512 字节起步；稳定后试 1024 字节 |
| ACK 策略 | 每片 ACK |
| 超时 | USB 本机 500ms，无线对端 1500ms 起步 |
| 重传次数 | 单片 5 次，整次升级允许用户继续 |
| 速度统计 | 按 ACK 后的有效字节计算 |

### 10.2 ACK 内容

`OTA_ACK` payload 建议包含：

| 字段 | 说明 |
|---|---|
| `session_id` | 当前会话 |
| `accepted_offset` | 本次接受的 offset |
| `accepted_len` | 本次接受长度 |
| `next_offset` | 下一片应发送位置 |
| `state` | 当前 OTA 状态 |
| `last_error` | 最近错误码 |

## 11. 错误码设计

| 错误码 | 含义 | 上位机动作 |
|---|---|---|
| `OTA_OK` | 成功 | 继续下一步 |
| `ERR_BAD_MAGIC` | magic 错 | 终止，提示协议不匹配 |
| `ERR_BAD_VERSION` | 协议版本不支持 | 终止，提示升级上位机或固件 |
| `ERR_TARGET_MISMATCH` | 目标不匹配 | 禁止升级 |
| `ERR_HW_MISMATCH` | 硬件版本不匹配 | 禁止升级，除非高级强制 |
| `ERR_BOOT_TOO_OLD` | Bootloader 太旧 | 禁止升级或要求有线救援 |
| `ERR_SESSION_MISMATCH` | session_id 不匹配 | 重新查询状态 |
| `ERR_OFFSET_MISMATCH` | offset 不匹配 | 使用设备返回的 next_offset 恢复 |
| `ERR_CHUNK_CRC` | 分片 CRC 错 | 重发该片 |
| `ERR_IMAGE_CRC` | 整包 CRC 错 | 重新传输或重新选择固件 |
| `ERR_FLASH_WRITE` | 写 Flash 失败 | 停止，提示救援 |
| `ERR_LINK_LOST` | 无线链路断开 | 保持会话，等待恢复 |
| `ERR_USER_ABORT` | 用户取消 | 清理或保留会话由用户选择 |

## 12. 防混淆设计总结

| 风险 | 防护 |
|---|---|
| 用户串口数据像 OTA magic | OTA 不监听用户串口 CDC0 |
| 用户串口发二进制文件 | 仍然只作为 `WDAP_UART_DATA` 转发 |
| 管理口收到随机字节 | 必须通过 magic、version、header_crc、payload_crc |
| 旧 OTA 包重复到达 | `session_id + seq + offset` 校验 |
| 升级目标选错 | `.wdapfw` 包头 + `target` + 设备信息三重匹配 |
| 无线中间断开 | 设备保存会话，恢复后 `OTA_QUERY` |
| 传完但用户不想启用 | 必须显式 `OTA_COMMIT` 才切换/写入 |

## 13. 上位机内部模块设计

| 模块 | 职责 |
|---|---|
| `SerialPortManager` | 扫描 COM、连接、断开、读写帧 |
| `FrameCodec` | 帧编码、解码、CRC、转义或定长读取 |
| `FirmwarePackage` | 解析 `.wdapfw`、计算 CRC/SHA、检查兼容性 |
| `OtaSession` | OTA 状态机、重传、暂停、恢复 |
| `DeviceModel` | 本机/对端 CH32/ESP 信息 |
| `LogModel` | UI 日志、协议日志、错误码 |
| `MainWindow` | 界面和用户操作 |

### 13.1 帧同步

串口是字节流，管理通道也要考虑丢字节和粘包。建议第一版使用：

```text
[SOF 2字节 0x55 0xAA]
[wdap_host_frame_t 28字节]
[payload N字节]
[EOF 2字节 0x0D 0x0A 可选]
```

如果不使用 EOF，也可以完全依赖 `payload_len` 定长读取。关键是：接收端找到 SOF 后，必须完整读够帧头，再根据 `payload_len` 读 payload，然后校验 CRC。

## 14. 上位机第一版开发路线

| 阶段 | 目标 | 验收标准 |
|---|---|---|
| PC-0 | 命令行版串口通信 | 能 HELLO 并读取设备信息 |
| PC-1 | 固件包解析 | 能显示 `.wdapfw` 包头、CRC、SHA |
| PC-2 | OTA 顺序传输 | 能从 0 传到末尾，每片 ACK |
| PC-3 | 断点续传 | 中途断开后能从 `next_offset` 恢复 |
| PC-4 | PySide6 GUI | 能选择设备、固件、开始/暂停/恢复 |
| PC-5 | 对端升级 | 能经无线链路升级 `PEER_CH32/PEER_ESP` |
| PC-6 | 日志和错误码 | 出错后能导出日志定位 |

## 15. 第一版最小功能范围

| 功能 | 第一版是否做 |
|---|---|
| COM 自动扫描 | 做 |
| HELLO/设备识别 | 做 |
| `.wdapfw` 固件包解析 | 做 |
| 本机 CH32 升级 | 做 |
| 本机 ESP 升级 | 做 |
| 对端 CH32 升级 | 第二阶段做，但协议第一版预留 |
| 对端 ESP 升级 | 第二阶段做，但协议第一版预留 |
| 断点续传 | 做顺序 `next_offset` 版本 |
| bitmap 缺块重传 | 后续 |
| 签名校验 | 预留字段，正式版做 |
| 升级日志导出 | 做 |
| 串口终端 | 可做，但必须和 OTA 管理通道分开 |

## 16. 推荐定版结论

| 项目 | 决策 |
|---|---|
| 第一版上位机 | `Python + PySide6 + pyserial` |
| 第一版通信入口 | 独立 `CDC1_MGMT` 管理口 |
| 用户串口 | 独立 `CDC0_USER_UART`，永不解析 OTA |
| 固件格式 | `.wdapfw` 外层统一包头 |
| OTA 识别 | `CDC1 + WDAP magic + type + session_id + 状态机` |
| 续传方式 | 第一版使用 `next_offset` 顺序续传 |
| 分片大小 | 512 字节起步，稳定后 1024 字节 |
| 校验方式 | 分片 CRC32 + 整包 CRC32/SHA256 |
| 启用方式 | 传输完成后显式 `OTA_VERIFY` + `OTA_COMMIT` |
| 回滚 | ESP 用 ESP-IDF OTA 回滚；CH32 失败停 Bootloader 等待重新投递 |

最重要的设计点是：OTA 不属于用户无线串口的数据内容，而属于独立管理通道上的管理协议。这样无论用户串口发文本、二进制、固件文件还是随机数据，都不会被当作 OTA。

## 17. 参考资料

| 资料 | 链接 |
|---|---|
| pySerial 文档 | https://pyserial.readthedocs.io/ |
| Qt for Python / PySide6 文档 | https://doc.qt.io/qtforpython-6/ |
| Tauri 文档 | https://tauri.app/ |
| ESP-IDF OTA 文档 | https://docs.espressif.com/projects/esp-idf/en/latest/esp32c6/api-reference/system/ota.html |
| ESP-IDF Partition Tables | https://docs.espressif.com/projects/esp-idf/en/latest/esp32c6/api-guides/partition-tables.html |
