from __future__ import annotations

from typing import Protocol

from wdap_ota.protocol.frame import HostFrame


class Transport(Protocol):
    """OTA 管理通道传输接口。

    这个接口只表达 OtaSession 需要的最小能力：
    1. write_frame 负责把已经组好的 HostFrame 发到 CDC1_MGMT 或测试传输层。
    2. read_frame 负责读取并返回一个已经解码的 HostFrame。
    后续如果替换成 USB Vendor/Bulk，只要实现这个接口，上层 OTA 状态机不需要改。
    """

    def write_frame(self, frame: HostFrame) -> None:
        """写出一帧管理通道数据。

        参数:
            frame: 已经包含 frame_type、target、session_id、offset 和 payload 的协议帧。
        返回:
            None。真实串口实现如果写入失败，应抛出传输层异常。
        """

    def read_frame(self, timeout_s: float | None = None) -> HostFrame:
        """读取一帧管理通道数据。

        参数:
            timeout_s: 可选超时时间，None 表示使用传输层默认超时。
        返回:
            HostFrame，必须已经完成 SOF、magic 和 CRC 校验。
        """
