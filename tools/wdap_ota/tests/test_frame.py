import pytest

from wdap_ota.protocol.constants import FrameType, Target
from wdap_ota.protocol.frame import FrameDecodeError, HostFrame


def test_host_frame_header_size_matches_protocol():
    assert HostFrame.HEADER_SIZE == 28


def test_encode_decode_round_trip_with_payload():
    frame = HostFrame(
        frame_type=FrameType.HELLO,
        target=Target.LOCAL_CH32,
        session_id=0x12345678,
        seq=7,
        offset=0,
        payload=b"hello",
    )

    packet = frame.encode()

    assert packet.startswith(HostFrame.SOF)
    decoded = HostFrame.decode(packet)
    assert decoded.frame_type == FrameType.HELLO
    assert decoded.target == Target.LOCAL_CH32
    assert decoded.session_id == 0x12345678
    assert decoded.seq == 7
    assert decoded.payload == b"hello"


def test_decode_rejects_bad_magic():
    packet = HostFrame(frame_type=FrameType.HELLO, target=Target.LOCAL_CH32).encode()
    corrupted = bytearray(packet)
    corrupted[2:6] = b"BAD!"

    with pytest.raises(FrameDecodeError, match="magic"):
        HostFrame.decode(bytes(corrupted))


def test_decode_rejects_bad_payload_crc():
    packet = HostFrame(
        frame_type=FrameType.OTA_DATA,
        target=Target.LOCAL_CH32,
        payload=b"firmware-chunk",
    ).encode()
    corrupted = bytearray(packet)
    corrupted[-1] ^= 0xFF

    with pytest.raises(FrameDecodeError, match="payload CRC"):
        HostFrame.decode(bytes(corrupted))
