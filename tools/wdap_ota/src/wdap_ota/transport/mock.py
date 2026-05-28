from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterable

from wdap_ota.protocol.frame import HostFrame


class MockTransportError(RuntimeError):
    """测试传输层错误，例如脚本响应已经读完。"""


@dataclass
class MockTransport:
    """面向单元测试的内存传输层。

    scripted_responses 是预置的设备响应队列，read_frame 每调用一次弹出一帧；
    written_frames 会记录主机侧写出的所有帧，方便测试检查 OtaSession 是否发了正确命令。
    """

    scripted_responses: Iterable[HostFrame] = ()
    written_frames: list[HostFrame] = field(default_factory=list)

    def __post_init__(self) -> None:
        """把外部传入的响应序列转成队列，保证 read_frame 按顺序消费。"""

        self._responses: Deque[HostFrame] = deque(self.scripted_responses)

    def write_frame(self, frame: HostFrame) -> None:
        """记录主机写出的管理帧。

        参数:
            frame: OtaSession 组好的 HostFrame。
        返回:
            None。Mock 不模拟底层写失败，错误路径由后续专门测试补充。
        """

        self.written_frames.append(frame)

    def read_frame(self, timeout_s: float | None = None) -> HostFrame:
        """返回下一帧预置设备响应。

        参数:
            timeout_s: 为了匹配真实传输接口保留，Mock 当前不使用。
        返回:
            HostFrame，来自 scripted_responses 队列。
        异常:
            MockTransportError: 没有更多响应可读，说明测试脚本没有覆盖当前交互。
        """

        if not self._responses:
            raise MockTransportError("no scripted response available")
        return self._responses.popleft()
