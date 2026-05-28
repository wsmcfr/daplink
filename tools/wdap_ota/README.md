# WDAP OTA Host

WDAP OTA Host 是无线 DAP 项目的第一版桌面 OTA 上位机。当前目标是先把协议核心、固件包校验、断点续传状态机、串口收发和基础 GUI 壳做稳定，方便后续 CH32V307RCT6 与 ESP32-C6 固件端联调。

## 当前正在做什么

| 模块 | 第一版做法 | 当前状态 |
|---|---|---|
| 协议帧 | `HostFrame` 固定帧头，包含 SOF、magic、type、target、session、seq、offset、CRC | 已实现并有单元测试 |
| 固件包 | `.wdapfw` 包头 + payload，校验 CRC32 和 SHA256 | 已实现并有单元测试 |
| 续传 | 严格顺序 `next_offset`，断线后重新 query 再从设备返回偏移继续 | 已实现会话层和 Mock 测试 |
| 传输 | `CDC1_MGMT` 管理串口，用户无线串口 `CDC0_USER_UART` 不参与 OTA | 已实现串口帧收发骨架 |
| CLI | `parse`、`hello`、`info`、`query`、`upload` | 已实现第一版入口 |
| GUI | PySide6 工程工具，含串口枚举、固件解析、目标选择、后台上传 worker、进度和日志区域 | 已实现主机侧骨架 |

## 后续优化应该换成什么

| 方向 | 现在先用 | 后续建议替换/升级 | 原因 |
|---|---|---|---|
| UI 技术栈 | Python + PySide6 | Tauri + Rust + Web UI | 协议稳定后更适合做签名发布、自动更新和更好的 Windows 体验 |
| 数据通道 | pyserial 管理串口 | USB Vendor/Bulk 或 WinUSB | 提高吞吐，减少 CDC 串口驱动和波特率限制 |
| 续传机制 | 单调递增 `next_offset` | bitmap 缺块恢复 + sliding window ACK | 断线或丢包后不用回退到单点偏移，速度和鲁棒性更好 |
| 完整性 | 每帧 CRC + 镜像 SHA256 | 固件包签名，Ed25519 或 ECDSA | 防止非法固件被刷入 |
| 协议实现 | Python/C 手写结构 | 统一 schema/codegen | 避免 Python、CH32、ESP 三端字段漂移 |
| 打包发布 | 源码运行或 PyInstaller | 签名 Windows 安装包 | 方便非开发环境使用 |

## 命令行使用

```powershell
cd tools/wdap_ota
python -m pip install -e .[dev]
python -m wdap_ota.cli --help
python -m wdap_ota.cli parse path\to\firmware.wdapfw
python -m wdap_ota.cli hello --port COM7
python -m wdap_ota.cli info --port COM7
python -m wdap_ota.cli query --port COM7 --target LOCAL_CH32 path\to\firmware.wdapfw
python -m wdap_ota.cli upload --port COM7 --target LOCAL_CH32 path\to\firmware.wdapfw
```

## GUI 使用

```powershell
cd tools/wdap_ota
python -m wdap_ota.gui.app
```

第一版 GUI 已经把串口枚举、固件包解析、后台上传 worker 和进度信号接到主机侧流程上。UI 不直接拼协议帧，上传路径通过 `OtaWorkflow -> OtaSession -> Transport` 复用同一套协议代码。

## 协议边界

| 规则 | 说明 |
|---|---|
| OTA 只连接 `CDC1_MGMT` | 上位机不能把用户无线串口数据误识别为 OTA |
| 用户串口固定为 `CDC0_USER_UART` | 用户发什么数据都只作为透明串口数据处理 |
| OTA 必须有 magic、type、session_id 和状态校验 | 防止随机字节、旧包或串台响应写入 Flash |
| 完成传输不等于立即启用固件 | 后续固件端必须通过显式 verify/commit 流程切换镜像 |

## 验证

```powershell
cd tools/wdap_ota
pytest -v
python -c "import wdap_ota; print(wdap_ota.__version__)"
python -m wdap_ota.cli --help
```

真实设备升级还需要 CH32V307RCT6/ESP32-C6 固件端实现 `CDC1_MGMT` 协议、Flash 写入、镜像校验和 commit/rollback 逻辑。

## 当前仍缺什么

| 缺口 | 当前处理 | 后续实现 |
|---|---|---|
| `DEVICE_INFO_RSP` 结构 | 先按原始 payload 十六进制显示 | 固件端字段定稿后解析成设备 ID、角色、CH32/ESP 版本 |
| `OTA_BEGIN/VERIFY/COMMIT` | 主机侧预留帧类型，第一版 workflow 先做 query + 顺序 data | 固件端状态机定稿后接入完整 begin/verify/commit 流程 |
| GUI 暂停/继续/取消 | 按钮和日志入口已保留 | 增加 worker 取消标志、重新 query 后续传 |
| 串口识别 | 当前枚举全部 COM | 按 VID/PID、接口号或描述优先标注 `CDC1_MGMT` |
