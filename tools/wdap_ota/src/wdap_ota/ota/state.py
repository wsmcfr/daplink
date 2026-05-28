from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelloInfo:
    """设备 HELLO 响应能力。

    max_chunk_size 表示设备当前愿意接收的最大 OTA 数据块长度；
    protocol_version 表示设备侧管理协议版本，后续用于兼容性分支。
    """

    max_chunk_size: int
    protocol_version: int


@dataclass(frozen=True)
class ResumeInfo:
    """设备 OTA 续传查询结果。

    session_id 是设备返回的升级会话号；
    next_offset 是设备期望主机继续发送的固件偏移；
    state 是设备侧升级状态原始值，第一版先保留整数，后续可收敛成枚举。
    """

    session_id: int
    next_offset: int
    state: int


@dataclass(frozen=True)
class DeviceInfo:
    """设备信息响应。

    第一版固件端 DEVICE_INFO_RSP 的结构还可能调整，因此主机先保留 raw_payload；
    hex_payload 便于 CLI 和日志直接展示，后续字段稳定后再拆成设备 ID、角色和版本号。
    """

    raw_payload: bytes

    @property
    def hex_payload(self) -> str:
        """返回设备信息 payload 的十六进制字符串。"""

        return self.raw_payload.hex()


@dataclass(frozen=True)
class AckInfo:
    """设备 OTA 数据块确认信息。

    accepted_offset/accepted_len 表示设备刚确认写入的块；
    next_offset 表示设备期望的下一段偏移；
    last_error 保留设备侧错误码，用于后续在 UI 中展示具体失败原因。
    """

    accepted_offset: int
    accepted_len: int
    next_offset: int
    last_error: int
