import pytest

from wdap_ota.protocol.constants import FrameType, Target
from wdap_ota.protocol.frame import HostFrame


class FakeSerial:
    """测试用串口对象，模拟 pyserial 的 read/write/flush/close 最小接口。"""

    def __init__(self, incoming: bytes = b"") -> None:
        """创建内存串口。

        参数:
            incoming: read 会按顺序返回的字节流。
        返回:
            None。written 用于记录 write 写出的内容。
        """

        self._incoming = bytearray(incoming)
        self.written = bytearray()
        self.flushed = False
        self.closed = False

    def write(self, data: bytes) -> int:
        """记录写出的字节并返回写入长度，模拟 pyserial.Serial.write。"""

        self.written.extend(data)
        return len(data)

    def read(self, size: int = 1) -> bytes:
        """从 incoming 中读取指定长度，数据不足时返回空字节模拟超时。"""

        if not self._incoming:
            return b""
        chunk = bytes(self._incoming[:size])
        del self._incoming[:size]
        return chunk

    def flush(self) -> None:
        """记录 flush 调用，验证写帧后会刷新底层缓冲。"""

        self.flushed = True

    def close(self) -> None:
        """记录 close 调用，验证传输层能释放串口资源。"""

        self.closed = True


def test_serial_transport_writes_encoded_frame():
    """验证 SerialTransport.write_frame 会写出 HostFrame.encode 的完整字节。"""

    from wdap_ota.transport.serial_port import SerialTransport

    fake_serial = FakeSerial()
    frame = HostFrame(frame_type=FrameType.HELLO, target=Target.BROADCAST_INFO)

    transport = SerialTransport(serial_instance=fake_serial)
    transport.write_frame(frame)

    assert bytes(fake_serial.written) == frame.encode()
    assert fake_serial.flushed is True


def test_serial_transport_reads_frame_after_noise():
    """验证 SerialTransport.read_frame 能跳过噪声并返回 CRC 校验后的管理帧。"""

    from wdap_ota.transport.serial_port import SerialTransport

    frame = HostFrame(
        frame_type=FrameType.HELLO_RSP,
        target=Target.BROADCAST_INFO,
        payload=b"\x00\x02\x01\x00",
    )
    fake_serial = FakeSerial(b"\x00\x99" + frame.encode())

    transport = SerialTransport(serial_instance=fake_serial)
    decoded = transport.read_frame()

    assert decoded.frame_type == FrameType.HELLO_RSP
    assert decoded.payload == b"\x00\x02\x01\x00"


def test_serial_transport_raises_timeout_when_stream_ends():
    """验证读取过程中没有足够字节时抛出传输超时错误。"""

    from wdap_ota.transport.serial_port import SerialTransport, TransportTimeoutError

    fake_serial = FakeSerial(b"\x55")
    transport = SerialTransport(serial_instance=fake_serial)

    with pytest.raises(TransportTimeoutError):
        transport.read_frame()
