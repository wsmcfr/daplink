import struct

import pytest

from wdap_ota.ota.session import OffsetMismatchError, OtaSession
from wdap_ota.protocol.constants import FrameType, Target
from wdap_ota.protocol.frame import HostFrame
from wdap_ota.transport.mock import MockTransport


def test_hello_returns_device_capabilities():
    transport = MockTransport(
        scripted_responses=[
            HostFrame(
                frame_type=FrameType.HELLO_RSP,
                target=Target.BROADCAST_INFO,
                payload=struct.pack("<HH", 512, 1),
            )
        ]
    )
    session = OtaSession(transport)

    hello = session.hello()

    assert hello.max_chunk_size == 512
    assert hello.protocol_version == 1
    assert transport.written_frames[0].frame_type == FrameType.HELLO


def test_query_resume_returns_next_offset():
    transport = MockTransport(
        scripted_responses=[
            HostFrame(
                frame_type=FrameType.OTA_QUERY_RSP,
                target=Target.LOCAL_CH32,
                session_id=0x22,
                payload=struct.pack("<II", 1024, 0),
            )
        ]
    )
    session = OtaSession(transport)

    resume = session.query_resume(Target.LOCAL_CH32, image_sha256=b"\x11" * 32)

    assert resume.session_id == 0x22
    assert resume.next_offset == 1024
    assert resume.state == 0


def test_device_info_returns_raw_payload_for_early_firmware_bringup():
    transport = MockTransport(
        scripted_responses=[
            HostFrame(
                frame_type=FrameType.DEVICE_INFO_RSP,
                target=Target.BROADCAST_INFO,
                payload=b"wdap-device-info",
            )
        ]
    )
    session = OtaSession(transport)

    info = session.device_info()

    assert info.raw_payload == b"wdap-device-info"
    assert info.hex_payload == b"wdap-device-info".hex()
    assert transport.written_frames[0].frame_type == FrameType.DEVICE_INFO_REQ


def test_upload_starts_from_resume_offset():
    transport = MockTransport(
        scripted_responses=[
            HostFrame(
                frame_type=FrameType.OTA_ACK,
                target=Target.LOCAL_CH32,
                session_id=0x33,
                payload=struct.pack("<IIIH", 4, 4, 8, 0),
            )
        ]
    )
    session = OtaSession(transport)

    final_offset = session.upload_bytes(
        Target.LOCAL_CH32,
        payload=b"abcdefgh",
        session_id=0x33,
        start_offset=4,
        chunk_size=4,
    )

    assert final_offset == 8
    written = transport.written_frames[0]
    assert written.frame_type == FrameType.OTA_DATA
    assert written.offset == 4
    assert written.payload == b"efgh"


def test_upload_rejects_offset_mismatch():
    transport = MockTransport(
        scripted_responses=[
            HostFrame(
                frame_type=FrameType.OTA_ACK,
                target=Target.LOCAL_CH32,
                session_id=0x33,
                payload=struct.pack("<IIIH", 0, 4, 2, 0),
            )
        ]
    )
    session = OtaSession(transport)

    with pytest.raises(OffsetMismatchError):
        session.upload_bytes(
            Target.LOCAL_CH32,
            payload=b"abcd",
            session_id=0x33,
            start_offset=0,
            chunk_size=4,
        )


def test_upload_reports_progress_after_each_ack():
    transport = MockTransport(
        scripted_responses=[
            HostFrame(
                frame_type=FrameType.OTA_ACK,
                target=Target.LOCAL_CH32,
                session_id=0x33,
                payload=struct.pack("<IIIH", 0, 4, 4, 0),
            ),
            HostFrame(
                frame_type=FrameType.OTA_ACK,
                target=Target.LOCAL_CH32,
                session_id=0x33,
                payload=struct.pack("<IIIH", 4, 4, 8, 0),
            ),
        ]
    )
    session = OtaSession(transport)
    offsets = []

    final_offset = session.upload_bytes(
        Target.LOCAL_CH32,
        payload=b"abcdefgh",
        session_id=0x33,
        start_offset=0,
        chunk_size=4,
        progress_callback=offsets.append,
    )

    assert final_offset == 8
    assert offsets == [4, 8]
