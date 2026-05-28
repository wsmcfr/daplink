import hashlib
import struct

import pytest

from wdap_ota.protocol.crc import crc32
from wdap_ota.protocol.firmware import FirmwarePackage


def build_test_package(payload: bytes = b"firmware") -> bytes:
    """构造测试用 .wdapfw 固件包。

    参数:
        payload: 固件镜像内容。
    返回:
        bytes，包含合法包头和 payload，可直接传给 CLI parse 命令。
    """

    header = struct.pack(
        FirmwarePackage.HEADER_FORMAT,
        b"WDAPFW",
        1,
        FirmwarePackage.HEADER_SIZE,
        1,
        3,
        0x00000001,
        0x00010002,
        0x00000001,
        len(payload),
        crc32(payload),
        hashlib.sha256(payload).digest(),
        0,
    )
    return header + payload


def test_parse_command_prints_firmware_summary(tmp_path, capsys):
    """验证 CLI parse 能离线解析固件包并输出关键摘要。"""

    firmware_path = tmp_path / "app.wdapfw"
    firmware_path.write_bytes(build_test_package(b"abc"))

    from wdap_ota.cli import main

    exit_code = main(["parse", str(firmware_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Firmware package OK" in output
    assert "target_chip: 1" in output
    assert "image_size: 3" in output


def test_help_command_lists_parse_and_hello(capsys):
    """验证 CLI 帮助中能看到第一版计划暴露的核心命令。"""

    from wdap_ota.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    output = capsys.readouterr().out
    assert exc_info.value.code == 0
    assert "parse" in output
    assert "hello" in output
    assert "info" in output
