import zlib


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    """计算 CRC-16/CCITT-FALSE。

    参数:
        data: 需要计算的字节数据。
        initial: 初始值，协议默认使用 0xFFFF。
    返回:
        16 位 CRC 值，范围为 0 到 0xFFFF。
    """

    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc32(data: bytes) -> int:
    """计算协议使用的无符号 CRC32。"""

    return zlib.crc32(data) & 0xFFFFFFFF
