from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SerialPortInfo:
    """可展示给 GUI/CLI 的串口信息。

    device 是真实串口名，例如 COM7；
    description 是系统返回的描述，用于帮助用户区分 CDC0_USER_UART 和 CDC1_MGMT。
    """

    device: str
    description: str


def list_serial_ports() -> list[SerialPortInfo]:
    """枚举当前系统串口。

    返回:
        list[SerialPortInfo]，按系统枚举顺序返回。
    说明:
        第一版先把所有串口列出来；后续可以根据 USB VID/PID、接口号或产品字符串优先标注
        `CDC1_MGMT`，进一步降低用户误选用户无线串口的概率。
    """

    from serial.tools import list_ports

    return [
        SerialPortInfo(device=port.device, description=port.description or "")
        for port in list_ports.comports()
    ]
