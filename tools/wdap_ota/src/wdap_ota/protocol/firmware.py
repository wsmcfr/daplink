from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

from .crc import crc32


class FirmwareParseError(ValueError):
    """固件包解析或校验失败。"""


@dataclass(frozen=True)
class FirmwareHeader:
    """WDAP 固件包头。

    字段含义与《无线DAP OTA上位机与升级协议设计.md》中的 wdap_fw_header_t 对齐。
    """

    package_version: int
    header_size: int
    target_chip: int
    target_role: int
    hardware_rev_mask: int
    fw_version: int
    min_boot_version: int
    image_size: int
    image_crc32: int
    image_sha256: bytes
    flags: int


@dataclass(frozen=True)
class FirmwarePackage:
    """已校验的 WDAP 固件包。"""

    MAGIC = b"WDAPFW"
    HEADER_FORMAT = "<6sHHHHIIIII32sI"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    header: FirmwareHeader
    payload: bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> "FirmwarePackage":
        """解析并校验 .wdapfw 固件包。

        主要流程:
        1. 检查文件长度和 magic。
        2. 解析固定包头。
        3. 按 header_size 跳到 payload。
        4. 校验 payload 长度、CRC32 和 SHA256。
        返回:
            FirmwarePackage，包含头部和固件 payload。
        """

        if len(data) < cls.HEADER_SIZE:
            raise FirmwareParseError("firmware package too short")

        unpacked = struct.unpack(cls.HEADER_FORMAT, data[: cls.HEADER_SIZE])
        (
            magic,
            package_version,
            header_size,
            target_chip,
            target_role,
            hardware_rev_mask,
            fw_version,
            min_boot_version,
            image_size,
            image_crc32,
            image_sha256,
            flags,
        ) = unpacked

        if magic != cls.MAGIC:
            raise FirmwareParseError("bad firmware magic")
        if header_size < cls.HEADER_SIZE:
            raise FirmwareParseError("header size too small")
        if len(data) < header_size + image_size:
            raise FirmwareParseError("payload length mismatch")

        payload = data[header_size : header_size + image_size]
        if crc32(payload) != image_crc32:
            raise FirmwareParseError("payload CRC32 mismatch")
        if hashlib.sha256(payload).digest() != image_sha256:
            raise FirmwareParseError("payload SHA256 mismatch")

        return cls(
            header=FirmwareHeader(
                package_version=package_version,
                header_size=header_size,
                target_chip=target_chip,
                target_role=target_role,
                hardware_rev_mask=hardware_rev_mask,
                fw_version=fw_version,
                min_boot_version=min_boot_version,
                image_size=image_size,
                image_crc32=image_crc32,
                image_sha256=image_sha256,
                flags=flags,
            ),
            payload=payload,
        )

    def is_compatible(self, *, target_chip: int, hardware_rev: int, role: int) -> bool:
        """检查固件包是否匹配用户选择的芯片、硬件版本和角色。"""

        if self.header.target_chip != target_chip:
            return False
        if not (self.header.hardware_rev_mask & (1 << hardware_rev)):
            return False
        if self.header.target_role not in (role, 0xFFFF):
            return False
        return True
