import hashlib
import struct
import zlib

import pytest

from wdap_ota.protocol.firmware import FirmwarePackage, FirmwareParseError


def build_package(payload: bytes = b"firmware") -> bytes:
    header_size = FirmwarePackage.HEADER_SIZE
    image_crc32 = zlib.crc32(payload) & 0xFFFFFFFF
    image_sha256 = hashlib.sha256(payload).digest()
    header = struct.pack(
        FirmwarePackage.HEADER_FORMAT,
        b"WDAPFW",
        1,
        header_size,
        1,
        3,
        0x00000001,
        0x00010002,
        0x00000001,
        len(payload),
        image_crc32,
        image_sha256,
        0,
    )
    return header + payload


def test_parse_valid_package():
    package = FirmwarePackage.from_bytes(build_package(b"abc"))

    assert package.header.target_chip == 1
    assert package.header.target_role == 3
    assert package.header.fw_version == 0x00010002
    assert package.payload == b"abc"


def test_rejects_bad_magic():
    data = bytearray(build_package())
    data[0:6] = b"BADFW!"

    with pytest.raises(FirmwareParseError, match="magic"):
        FirmwarePackage.from_bytes(bytes(data))


def test_rejects_bad_crc():
    data = bytearray(build_package())
    data[-1] ^= 0xFF

    with pytest.raises(FirmwareParseError, match="CRC32"):
        FirmwarePackage.from_bytes(bytes(data))


def test_rejects_bad_sha256():
    data = bytearray(build_package())
    sha_start = 6 + 2 + 2 + 2 + 2 + 4 + 4 + 4 + 4 + 4
    data[sha_start] ^= 0xFF

    with pytest.raises(FirmwareParseError, match="SHA256"):
        FirmwarePackage.from_bytes(bytes(data))
