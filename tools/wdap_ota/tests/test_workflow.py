import hashlib
import struct

from wdap_ota.ota.workflow import OtaWorkflow, UploadConfig
from wdap_ota.protocol.constants import FrameType, Target
from wdap_ota.protocol.crc import crc32
from wdap_ota.protocol.firmware import FirmwarePackage
from wdap_ota.protocol.frame import HostFrame
from wdap_ota.transport.mock import MockTransport


def build_package(payload: bytes = b"abc") -> FirmwarePackage:
    """构造已校验的测试固件包。"""

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
    return FirmwarePackage.from_bytes(header + payload)


def test_workflow_uploads_package_through_ota_session():
    """验证上层 workflow 复用 OtaSession 完成 hello/query/upload。"""

    transport = MockTransport(
        scripted_responses=[
            HostFrame(
                frame_type=FrameType.HELLO_RSP,
                target=Target.BROADCAST_INFO,
                payload=struct.pack("<HH", 512, 1),
            ),
            HostFrame(
                frame_type=FrameType.OTA_QUERY_RSP,
                target=Target.LOCAL_CH32,
                session_id=0x33,
                payload=struct.pack("<II", 0, 0),
            ),
            HostFrame(
                frame_type=FrameType.OTA_ACK,
                target=Target.LOCAL_CH32,
                session_id=0x33,
                payload=struct.pack("<IIIH", 0, 3, 3, 0),
            ),
        ]
    )
    events: list[tuple[str, int, int]] = []
    workflow = OtaWorkflow(lambda config: transport)

    result = workflow.upload_package(
        UploadConfig(port="COM7", target=Target.LOCAL_CH32, chunk_size=512),
        build_package(b"abc"),
        progress_callback=lambda stage, current, total: events.append((stage, current, total)),
    )

    assert result.final_offset == 3
    assert [frame.frame_type for frame in transport.written_frames] == [
        FrameType.HELLO,
        FrameType.OTA_QUERY,
        FrameType.OTA_DATA,
    ]
    assert ("upload", 3, 3) in events
    assert events[-1] == ("done", 3, 3)
