from enum import IntEnum, IntFlag


class FrameType(IntEnum):
    """管理通道帧类型，数值需要和 CH32/ESP 固件保持一致。"""

    HELLO = 0x01
    HELLO_RSP = 0x02
    DEVICE_INFO_REQ = 0x03
    DEVICE_INFO_RSP = 0x04
    OTA_QUERY = 0x10
    OTA_QUERY_RSP = 0x11
    OTA_BEGIN = 0x12
    OTA_BEGIN_RSP = 0x13
    OTA_DATA = 0x14
    OTA_ACK = 0x15
    OTA_STATUS = 0x16
    OTA_VERIFY = 0x17
    OTA_VERIFY_RSP = 0x18
    OTA_COMMIT = 0x19
    OTA_RESULT = 0x1A
    OTA_ABORT = 0x1B
    ERROR_RSP = 0x7F


class Target(IntEnum):
    """升级目标枚举，用于区分本机/对端和 CH32/ESP。"""

    LOCAL_CH32 = 0x01
    LOCAL_ESP = 0x02
    PEER_CH32 = 0x11
    PEER_ESP = 0x12
    BROADCAST_INFO = 0xF0


class FrameFlags(IntFlag):
    """管理帧标志位。"""

    NONE = 0
    NEED_ACK = 1 << 0
    LAST_CHUNK = 1 << 1
    ENCRYPTED = 1 << 2
