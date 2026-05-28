from __future__ import annotations

import struct

from collections.abc import Callable

from wdap_ota.ota.state import AckInfo, DeviceInfo, HelloInfo, ResumeInfo
from wdap_ota.protocol.constants import FrameFlags, FrameType, Target
from wdap_ota.protocol.frame import HostFrame
from wdap_ota.transport.base import Transport


class OtaSessionError(RuntimeError):
    """OTA 会话层基础错误。"""


class UnexpectedFrameError(OtaSessionError):
    """设备返回了当前步骤不期望的帧类型或目标。"""


class OffsetMismatchError(OtaSessionError):
    """设备确认的 next_offset 和主机期望值不一致，主机应重新 query 后再续传。"""


class DeviceAckError(OtaSessionError):
    """设备 ACK 中携带了非 0 错误码。"""


class OtaSession:
    """WDAP OTA 主机会话状态机。

    第一版会话层只处理严格顺序传输：
    1. hello 读取设备能力。
    2. query_resume 查询设备当前 next_offset。
    3. upload_bytes 从指定偏移顺序发送数据块并等待 ACK。
    后续如果升级为 bitmap 续传或滑动窗口 ACK，应优先扩展本类，而不是让 GUI 直接拼协议帧。
    """

    HELLO_RSP_FORMAT = struct.Struct("<HH")
    QUERY_RSP_FORMAT = struct.Struct("<II")
    ACK_FORMAT = struct.Struct("<IIIH")

    def __init__(self, transport: Transport) -> None:
        """创建 OTA 会话。

        参数:
            transport: 管理通道传输实现，可以是真实串口、USB Vendor/Bulk 或 MockTransport。
        返回:
            None。会话不拥有端口生命周期，连接和关闭由传输层外部管理。
        """

        self.transport = transport
        self._seq = 0

    def hello(self) -> HelloInfo:
        """发送 HELLO 并解析设备能力。

        主要流程:
        1. 向 BROADCAST_INFO 目标发送 HELLO，避免绑定某个芯片目标。
        2. 等待 HELLO_RSP。
        3. 从 payload 中解析最大块大小和协议版本。
        返回:
            HelloInfo，供 CLI/GUI 决定 chunk_size 和兼容性提示。
        """

        self.transport.write_frame(
            self._make_frame(
                frame_type=FrameType.HELLO,
                target=Target.BROADCAST_INFO,
            )
        )
        response = self.transport.read_frame()
        self._expect_frame(response, FrameType.HELLO_RSP)
        if len(response.payload) != self.HELLO_RSP_FORMAT.size:
            raise UnexpectedFrameError("invalid HELLO_RSP payload length")
        max_chunk_size, protocol_version = self.HELLO_RSP_FORMAT.unpack(response.payload)
        return HelloInfo(max_chunk_size=max_chunk_size, protocol_version=protocol_version)

    def query_resume(self, target: Target, *, image_sha256: bytes) -> ResumeInfo:
        """查询指定目标的 OTA 续传位置。

        参数:
            target: 要升级的芯片目标，例如 LOCAL_CH32。
            image_sha256: 完整固件镜像 SHA256，设备用它识别是否属于同一个固件。
        返回:
            ResumeInfo，包含设备会话号、next_offset 和设备状态。
        """

        if len(image_sha256) != 32:
            raise ValueError("image_sha256 must be 32 bytes")

        self.transport.write_frame(
            self._make_frame(
                frame_type=FrameType.OTA_QUERY,
                target=target,
                payload=image_sha256,
            )
        )
        response = self.transport.read_frame()
        self._expect_frame(response, FrameType.OTA_QUERY_RSP, target=target)
        if len(response.payload) != self.QUERY_RSP_FORMAT.size:
            raise UnexpectedFrameError("invalid OTA_QUERY_RSP payload length")
        next_offset, state = self.QUERY_RSP_FORMAT.unpack(response.payload)
        return ResumeInfo(
            session_id=response.session_id,
            next_offset=next_offset,
            state=state,
        )

    def device_info(self) -> DeviceInfo:
        """请求设备信息。

        当前固件端 DEVICE_INFO_RSP 的 payload 结构尚未最终冻结，第一版先返回原始字节；
        CLI 可以打印十六进制，后续协议字段定稿后再升级为结构化解析。
        返回:
            DeviceInfo，包含 raw_payload 和 hex_payload。
        """

        self.transport.write_frame(
            self._make_frame(
                frame_type=FrameType.DEVICE_INFO_REQ,
                target=Target.BROADCAST_INFO,
            )
        )
        response = self.transport.read_frame()
        self._expect_frame(response, FrameType.DEVICE_INFO_RSP)
        return DeviceInfo(raw_payload=response.payload)

    def upload_bytes(
        self,
        target: Target,
        *,
        payload: bytes,
        session_id: int,
        start_offset: int,
        chunk_size: int,
        progress_callback: Callable[[int], None] | None = None,
    ) -> int:
        """从 start_offset 开始顺序上传固件字节。

        参数:
            target: OTA 目标芯片。
            payload: 完整固件 payload。
            session_id: query/begin 后设备确认的 OTA 会话号。
            start_offset: 续传起始偏移，通常来自 ResumeInfo.next_offset。
            chunk_size: 每帧最多发送的 payload 长度，通常不超过 HelloInfo.max_chunk_size。
            progress_callback: 每个 ACK 后回调当前 next_offset，供 CLI/GUI 更新进度。
        返回:
            int，设备最后确认的 next_offset。
        异常:
            OffsetMismatchError: 设备期望偏移和主机顺序发送结果不一致，需要重新 query。
        """

        if start_offset < 0:
            raise ValueError("start_offset must be >= 0")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if start_offset > len(payload):
            raise ValueError("start_offset is beyond payload length")

        offset = start_offset
        while offset < len(payload):
            chunk = payload[offset : offset + chunk_size]
            expected_next = offset + len(chunk)
            flags = FrameFlags.LAST_CHUNK if expected_next == len(payload) else FrameFlags.NONE
            self.transport.write_frame(
                self._make_frame(
                    frame_type=FrameType.OTA_DATA,
                    target=target,
                    flags=flags,
                    session_id=session_id,
                    offset=offset,
                    payload=chunk,
                )
            )
            ack = self._read_ack(target=target, session_id=session_id)

            if ack.last_error != 0:
                raise DeviceAckError(f"device reported OTA error {ack.last_error}")
            if ack.accepted_offset != offset or ack.accepted_len != len(chunk):
                raise OffsetMismatchError(
                    "device acknowledged a different data block "
                    f"(expected offset={offset}, len={len(chunk)}, "
                    f"got offset={ack.accepted_offset}, len={ack.accepted_len})"
                )
            if ack.next_offset != expected_next:
                raise OffsetMismatchError(
                    f"device next_offset mismatch: expected {expected_next}, got {ack.next_offset}"
                )

            offset = ack.next_offset
            if progress_callback is not None:
                progress_callback(offset)

        return offset

    def _read_ack(self, *, target: Target, session_id: int) -> AckInfo:
        """读取并解析 OTA_DATA 对应的 ACK。

        参数:
            target: 当前升级目标，用于防止串台响应被误用。
            session_id: 当前 OTA 会话号，用于防止旧会话 ACK 被误用。
        返回:
            AckInfo，包含设备确认的块和下一偏移。
        """

        response = self.transport.read_frame()
        self._expect_frame(response, FrameType.OTA_ACK, target=target, session_id=session_id)
        if len(response.payload) != self.ACK_FORMAT.size:
            raise UnexpectedFrameError("invalid OTA_ACK payload length")
        accepted_offset, accepted_len, next_offset, last_error = self.ACK_FORMAT.unpack(
            response.payload
        )
        return AckInfo(
            accepted_offset=accepted_offset,
            accepted_len=accepted_len,
            next_offset=next_offset,
            last_error=last_error,
        )

    def _make_frame(
        self,
        *,
        frame_type: FrameType,
        target: Target,
        flags: FrameFlags = FrameFlags.NONE,
        session_id: int = 0,
        offset: int = 0,
        payload: bytes = b"",
    ) -> HostFrame:
        """创建带递增 seq 的 HostFrame。

        seq 用于后续排查丢包和乱序；第一版测试暂不强依赖它，但真实设备日志会用到。
        """

        frame = HostFrame(
            frame_type=frame_type,
            target=target,
            flags=flags,
            session_id=session_id,
            seq=self._seq,
            offset=offset,
            payload=payload,
        )
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return frame

    @staticmethod
    def _expect_frame(
        frame: HostFrame,
        expected_type: FrameType,
        *,
        target: Target | None = None,
        session_id: int | None = None,
    ) -> None:
        """校验设备响应是否属于当前会话步骤。

        参数:
            frame: 设备返回的帧。
            expected_type: 当前步骤期望的帧类型。
            target: 如果传入，则响应目标必须一致。
            session_id: 如果传入，则响应会话号必须一致。
        返回:
            None。校验失败时抛 UnexpectedFrameError，避免错误响应继续写入流程。
        """

        if frame.frame_type != expected_type:
            raise UnexpectedFrameError(
                f"expected {expected_type.name}, got {frame.frame_type.name}"
            )
        if target is not None and frame.target != target:
            raise UnexpectedFrameError(f"unexpected target {frame.target.name}")
        if session_id is not None and frame.session_id != session_id:
            raise UnexpectedFrameError(f"unexpected session_id {frame.session_id}")
