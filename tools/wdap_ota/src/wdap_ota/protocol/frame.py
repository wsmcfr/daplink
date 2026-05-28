from __future__ import annotations

from dataclasses import dataclass
import struct

from .constants import FrameFlags, FrameType, Target
from .crc import crc16_ccitt, crc32


class FrameDecodeError(ValueError):
    """管理帧解码失败。"""


@dataclass(frozen=True)
class HostFrame:
    """WDAP OTA 管理通道帧。

    该结构只用于 CDC1_MGMT 或后续 Vendor/Bulk 管理通道，不用于用户无线串口。
    编码格式和文档中的 wdap_host_frame_t 保持一致，所有多字节字段为小端序。
    """

    SOF = b"\x55\xAA"
    MAGIC = 0x50414457
    VERSION = 1
    HEADER_SIZE = 28
    _HEADER_STRUCT = struct.Struct("<IBBBBIIIHHI")

    frame_type: FrameType
    target: Target
    flags: FrameFlags = FrameFlags.NONE
    session_id: int = 0
    seq: int = 0
    offset: int = 0
    payload: bytes = b""

    def encode(self) -> bytes:
        """编码为可写入串口的完整帧。

        主要流程:
        1. 先按 header_crc=0 组装帧头。
        2. 对帧头计算 CRC16。
        3. 对 payload 计算 CRC32。
        4. 拼接 SOF、帧头和 payload。
        返回:
            bytes，包含 SOF、28 字节帧头和 payload。
        """

        payload_crc = crc32(self.payload)
        header_without_crc = self._pack_header(header_crc=0, payload_crc=payload_crc)
        header_crc = crc16_ccitt(header_without_crc)
        header = self._pack_header(header_crc=header_crc, payload_crc=payload_crc)
        return self.SOF + header + self.payload

    @classmethod
    def decode(cls, packet: bytes) -> "HostFrame":
        """从完整串口帧解码 HostFrame。

        参数:
            packet: 包含 SOF、帧头和 payload 的完整字节流。
        返回:
            HostFrame 实例。
        异常:
            FrameDecodeError: 帧长度、magic、CRC 或枚举值不合法。
        """

        min_len = len(cls.SOF) + cls.HEADER_SIZE
        if len(packet) < min_len:
            raise FrameDecodeError("frame too short")
        if not packet.startswith(cls.SOF):
            raise FrameDecodeError("missing SOF")

        header = packet[len(cls.SOF) : min_len]
        fields = list(cls._HEADER_STRUCT.unpack(header))
        (
            magic,
            version,
            frame_type,
            target,
            flags,
            session_id,
            seq,
            offset,
            payload_len,
            header_crc,
            payload_crc,
        ) = fields

        if magic != cls.MAGIC:
            raise FrameDecodeError("bad magic")
        if version != cls.VERSION:
            raise FrameDecodeError("unsupported version")
        if len(packet) != min_len + payload_len:
            raise FrameDecodeError("payload length mismatch")

        fields[9] = 0
        header_without_crc = cls._HEADER_STRUCT.pack(*fields)
        if crc16_ccitt(header_without_crc) != header_crc:
            raise FrameDecodeError("bad header CRC")

        payload = packet[min_len:]
        if crc32(payload) != payload_crc:
            raise FrameDecodeError("bad payload CRC")

        try:
            typed_frame = FrameType(frame_type)
            typed_target = Target(target)
            typed_flags = FrameFlags(flags)
        except ValueError as exc:
            raise FrameDecodeError(str(exc)) from exc

        return cls(
            frame_type=typed_frame,
            target=typed_target,
            flags=typed_flags,
            session_id=session_id,
            seq=seq,
            offset=offset,
            payload=payload,
        )

    def _pack_header(self, *, header_crc: int, payload_crc: int) -> bytes:
        """按协议固定小端序打包 28 字节帧头。"""

        return self._HEADER_STRUCT.pack(
            self.MAGIC,
            self.VERSION,
            int(self.frame_type),
            int(self.target),
            int(self.flags),
            self.session_id,
            self.seq,
            self.offset,
            len(self.payload),
            header_crc,
            payload_crc,
        )
