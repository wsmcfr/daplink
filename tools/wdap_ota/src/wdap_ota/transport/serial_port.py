from __future__ import annotations

import struct
from types import TracebackType
from typing import Any

from wdap_ota.protocol.frame import FrameDecodeError, HostFrame


class SerialTransportError(RuntimeError):
    """串口管理通道传输层基础错误。"""


class TransportTimeoutError(SerialTransportError):
    """串口读取超时或数据流提前结束。"""


class SerialTransport:
    """基于 pyserial 的 CDC1_MGMT 管理通道传输层。

    第一版只负责可靠地收发 HostFrame：
    1. write_frame 把 HostFrame.encode() 后的完整字节写入串口。
    2. read_frame 从串口中同步 SOF，读取固定帧头，再按 payload_len 读取 payload。
    3. 最后交给 HostFrame.decode 做 magic、版本、CRC 和枚举校验。
    后续如果替换成 USB Vendor/Bulk，应该新增另一个 Transport 实现，而不是改 OTA 会话层。
    """

    def __init__(
        self,
        port: str | None = None,
        *,
        baudrate: int = 2_000_000,
        timeout: float = 1.0,
        serial_instance: Any | None = None,
    ) -> None:
        """创建串口传输对象。

        参数:
            port: Windows 串口名，例如 COM7。传入 serial_instance 时可为空。
            baudrate: 串口波特率，第一版默认 2Mbps，后续实测后可调整。
            timeout: pyserial 读超时时间。
            serial_instance: 测试注入用对象，需实现 read/write/flush/close。
        返回:
            None。真实端口会在构造时打开。
        """

        if serial_instance is not None:
            self._serial = serial_instance
            return

        if port is None:
            raise ValueError("port is required when serial_instance is not provided")

        # pyserial 只在真实硬件路径中需要导入，避免单元测试强依赖物理串口。
        import serial

        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)

    def write_frame(self, frame: HostFrame) -> None:
        """写出一帧已编码的管理通道数据。

        参数:
            frame: OtaSession 构造的 HostFrame。
        返回:
            None。底层写入异常会向上传递，CLI/GUI 负责展示。
        """

        packet = frame.encode()
        written = self._serial.write(packet)
        if written != len(packet):
            raise SerialTransportError(f"short serial write: {written}/{len(packet)}")
        self._serial.flush()

    def read_frame(self, timeout_s: float | None = None) -> HostFrame:
        """从串口读取并解码一帧管理通道数据。

        参数:
            timeout_s: 可选临时超时，真实 pyserial 对象支持 timeout 属性时会临时覆盖。
        返回:
            HostFrame，已经通过 HostFrame.decode 校验。
        异常:
            TransportTimeoutError: 没有读到完整 SOF、帧头或 payload。
            FrameDecodeError: 读到完整帧但协议校验失败。
        """

        old_timeout = getattr(self._serial, "timeout", None)
        timeout_changed = timeout_s is not None and hasattr(self._serial, "timeout")
        if timeout_changed:
            self._serial.timeout = timeout_s

        try:
            packet = self._read_packet_bytes()
            return HostFrame.decode(packet)
        finally:
            # 临时超时只影响本次 read_frame，避免 GUI/CLI 后续读操作继承意外配置。
            if timeout_changed:
                self._serial.timeout = old_timeout

    def close(self) -> None:
        """关闭底层串口资源。"""

        self._serial.close()

    def __enter__(self) -> "SerialTransport":
        """支持 with SerialTransport(...) as transport 形式管理端口生命周期。"""

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出上下文时关闭串口，避免端口被长期占用。"""

        self.close()

    def _read_packet_bytes(self) -> bytes:
        """按 SOF、帧头、payload 的顺序读取完整原始帧。

        返回:
            bytes，包含 SOF、28 字节帧头和 payload，可直接传给 HostFrame.decode。
        """

        sof = self._read_sof()
        header = self._read_exact(HostFrame.HEADER_SIZE)

        try:
            payload_len = HostFrame._HEADER_STRUCT.unpack(header)[8]
        except struct.error as exc:
            raise FrameDecodeError("invalid header") from exc

        payload = self._read_exact(payload_len)
        return sof + header + payload

    def _read_sof(self) -> bytes:
        """在串口流中寻找 0x55 0xAA 帧起始符。

        这样做可以跳过设备启动日志、噪声字节或上一次残留的半帧；
        但 OTA 仍然只在 CDC1_MGMT 上执行，不会去扫描用户无线串口数据。
        """

        first = b""
        while True:
            byte = self._serial.read(1)
            if byte == b"":
                raise TransportTimeoutError("timeout while waiting for SOF")

            if first == b"\x55" and byte == b"\xAA":
                return HostFrame.SOF

            # 当前字节如果是 0x55，可能是下一帧 SOF 的第一个字节，需要保留状态。
            first = byte if byte == b"\x55" else b""

    def _read_exact(self, size: int) -> bytes:
        """读取指定长度的字节，数据不足时抛超时错误。

        参数:
            size: 期望读取的字节数。
        返回:
            bytes，长度一定等于 size。
        """

        chunks = bytearray()
        while len(chunks) < size:
            chunk = self._serial.read(size - len(chunks))
            if chunk == b"":
                raise TransportTimeoutError(f"timeout while reading {size} bytes")
            chunks.extend(chunk)
        return bytes(chunks)
