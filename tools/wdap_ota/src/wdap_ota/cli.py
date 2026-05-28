from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wdap_ota.ota.session import OtaSession
from wdap_ota.ota.workflow import OtaWorkflow, UploadConfig
from wdap_ota.protocol.constants import Target
from wdap_ota.protocol.firmware import FirmwarePackage
from wdap_ota.transport.serial_port import SerialTransport


def main(argv: list[str] | None = None) -> int:
    """WDAP OTA 命令行入口。

    参数:
        argv: 传入 None 时使用 sys.argv；测试可传入列表避免依赖真实命令行。
    返回:
        int，0 表示命令执行成功，非 0 表示失败。
    """

    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    """创建 CLI 参数解析器。

    第一版保留 parse/hello/info/query/upload 命令：
    parse 不需要硬件，适合先检查固件包；
    hello/query/upload 走 CDC1_MGMT 串口，绝不连接用户无线串口。
    """

    parser = argparse.ArgumentParser(
        prog="wdap-ota",
        description="WDAP OTA host tool for CDC1_MGMT management channel",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="parse and verify a .wdapfw package")
    parse_cmd.add_argument("firmware", type=Path, help="path to .wdapfw package")
    parse_cmd.set_defaults(func=_cmd_parse)

    hello_cmd = subparsers.add_parser("hello", help="query device protocol capabilities")
    _add_port_args(hello_cmd)
    hello_cmd.set_defaults(func=_cmd_hello)

    info_cmd = subparsers.add_parser("info", help="read raw device info payload")
    _add_port_args(info_cmd)
    info_cmd.set_defaults(func=_cmd_info)

    query_cmd = subparsers.add_parser("query", help="query OTA resume offset")
    _add_port_args(query_cmd)
    query_cmd.add_argument("--target", required=True, choices=_target_names(), help="OTA target")
    query_cmd.add_argument("firmware", type=Path, help="path to .wdapfw package")
    query_cmd.set_defaults(func=_cmd_query)

    upload_cmd = subparsers.add_parser("upload", help="upload firmware payload sequentially")
    _add_port_args(upload_cmd)
    upload_cmd.add_argument("--target", required=True, choices=_target_names(), help="OTA target")
    upload_cmd.add_argument("--chunk-size", type=int, default=0, help="override chunk size")
    upload_cmd.add_argument("firmware", type=Path, help="path to .wdapfw package")
    upload_cmd.set_defaults(func=_cmd_upload)

    return parser


def _add_port_args(parser: argparse.ArgumentParser) -> None:
    """给需要硬件连接的命令增加串口参数。"""

    parser.add_argument("--port", required=True, help="CDC1_MGMT serial port, for example COM7")
    parser.add_argument("--baudrate", type=int, default=2_000_000, help="serial baudrate")
    parser.add_argument("--timeout", type=float, default=1.0, help="serial read timeout in seconds")


def _target_names() -> list[str]:
    """返回 CLI 支持输入的 Target 枚举名。"""

    return [target.name for target in Target if target != Target.BROADCAST_INFO]


def _cmd_parse(args: argparse.Namespace) -> int:
    """解析并打印固件包摘要。

    参数:
        args: argparse 解析出的命令参数，必须包含 firmware。
    返回:
        int，解析成功返回 0。
    """

    package = _load_package(args.firmware)
    _print_package_summary(package)
    return 0


def _cmd_hello(args: argparse.Namespace) -> int:
    """连接 CDC1_MGMT 并读取设备能力。"""

    with SerialTransport(port=args.port, baudrate=args.baudrate, timeout=args.timeout) as transport:
        session = OtaSession(transport)
        hello = session.hello()
    print("HELLO OK")
    print(f"max_chunk_size: {hello.max_chunk_size}")
    print(f"protocol_version: {hello.protocol_version}")
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    """读取设备信息原始 payload。

    固件端字段未完全定稿前，CLI 先输出十六进制原文，便于联调确认帧方向和长度。
    """

    with SerialTransport(port=args.port, baudrate=args.baudrate, timeout=args.timeout) as transport:
        session = OtaSession(transport)
        info = session.device_info()
    print("DEVICE INFO OK")
    print(f"payload_len: {len(info.raw_payload)}")
    print(f"payload_hex: {info.hex_payload}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    """查询设备对当前固件包的续传位置。"""

    package = _load_package(args.firmware)
    target = Target[args.target]
    with SerialTransport(port=args.port, baudrate=args.baudrate, timeout=args.timeout) as transport:
        session = OtaSession(transport)
        resume = session.query_resume(target, image_sha256=package.header.image_sha256)
    print("QUERY OK")
    print(f"session_id: 0x{resume.session_id:08X}")
    print(f"next_offset: {resume.next_offset}")
    print(f"state: {resume.state}")
    return 0


def _cmd_upload(args: argparse.Namespace) -> int:
    """顺序上传固件 payload。

    第一版 upload 只做严格 next_offset 续传；如果中途断线，重新执行 query/upload 即可从设备返回的
    next_offset 继续。后续优化可以换成 bitmap 缺块恢复和滑动窗口 ACK。
    """

    package = _load_package(args.firmware)
    target = Target[args.target]
    result = OtaWorkflow().upload_package(
        UploadConfig(
            port=args.port,
            baudrate=args.baudrate,
            timeout=args.timeout,
            target=target,
            chunk_size=args.chunk_size,
        ),
        package,
        progress_callback=lambda stage, current, total: print(
            f"{stage}: {current}/{total}"
        )
        if stage in {"upload", "done"}
        else None,
    )

    print("UPLOAD OK")
    print(f"final_offset: {result.final_offset}")
    print(f"image_size: {result.image_size}")
    return 0


def _load_package(path: Path) -> FirmwarePackage:
    """从磁盘读取并校验 .wdapfw 固件包。"""

    return FirmwarePackage.from_bytes(path.read_bytes())


def _print_package_summary(package: FirmwarePackage) -> None:
    """以稳定的文本格式打印固件包摘要，便于用户和测试读取。"""

    header = package.header
    print("Firmware package OK")
    print(f"package_version: {header.package_version}")
    print(f"target_chip: {header.target_chip}")
    print(f"target_role: {header.target_role}")
    print(f"hardware_rev_mask: 0x{header.hardware_rev_mask:08X}")
    print(f"fw_version: 0x{header.fw_version:08X}")
    print(f"min_boot_version: 0x{header.min_boot_version:08X}")
    print(f"image_size: {header.image_size}")
    print(f"image_crc32: 0x{header.image_crc32:08X}")
    print(f"image_sha256: {header.image_sha256.hex()}")


if __name__ == "__main__":
    # 作为模块直接运行时返回系统退出码；单元测试直接调用 main(argv) 不走这里。
    raise SystemExit(main(sys.argv[1:]))
