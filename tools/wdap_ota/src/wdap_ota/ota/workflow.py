from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from wdap_ota.ota.session import OtaSession
from wdap_ota.protocol.constants import Target
from wdap_ota.protocol.firmware import FirmwarePackage
from wdap_ota.transport.base import Transport
from wdap_ota.transport.serial_port import SerialTransport


ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class UploadConfig:
    """一次 OTA 上传任务的主机侧配置。

    port/baudrate/timeout 描述 CDC1_MGMT 连接；
    target 描述要升级的目标芯片；
    chunk_size 为 0 时使用设备 HELLO 返回的最大分片长度。
    """

    port: str
    target: Target
    baudrate: int = 2_000_000
    timeout: float = 1.0
    chunk_size: int = 0


@dataclass(frozen=True)
class UploadResult:
    """一次上传流程的结果摘要。"""

    final_offset: int
    image_size: int
    session_id: int
    chunk_size: int


class OtaWorkflow:
    """CLI 和 GUI 共用的 OTA 主机侧流程。

    这个类负责把“打开传输层 -> HELLO -> QUERY -> DATA 上传”的步骤串起来；
    具体帧构造仍然由 OtaSession 负责，避免 CLI 和 GUI 各自拼协议。
    后续加入 OTA_BEGIN/VERIFY/COMMIT 时，应优先扩展这里和 OtaSession。
    """

    def __init__(
        self,
        transport_factory: Callable[[UploadConfig], Transport] | None = None,
    ) -> None:
        """创建 workflow。

        参数:
            transport_factory: 可注入的传输层工厂，测试使用 MockTransport，真实运行使用 SerialTransport。
        返回:
            None。
        """

        self._transport_factory = transport_factory or self._open_serial_transport

    def upload_package(
        self,
        config: UploadConfig,
        package: FirmwarePackage,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> UploadResult:
        """执行第一版顺序 OTA 上传流程。

        参数:
            config: 串口、目标和分片配置。
            package: 已通过 CRC32/SHA256 校验的固件包。
            progress_callback: 可选进度回调，参数为 stage/current/total。
        返回:
            UploadResult，包含最终偏移、镜像大小、会话号和实际分片大小。
        """

        total = package.header.image_size
        with self._managed_transport(config) as transport:
            session = OtaSession(transport)

            self._emit(progress_callback, "hello", 0, total)
            hello = session.hello()

            self._emit(progress_callback, "query", 0, total)
            resume = session.query_resume(config.target, image_sha256=package.header.image_sha256)

            chunk_size = config.chunk_size or hello.max_chunk_size
            final_offset = session.upload_bytes(
                config.target,
                payload=package.payload,
                session_id=resume.session_id,
                start_offset=resume.next_offset,
                chunk_size=chunk_size,
                progress_callback=lambda offset: self._emit(
                    progress_callback, "upload", offset, total
                ),
            )

        self._emit(progress_callback, "done", final_offset, total)
        return UploadResult(
            final_offset=final_offset,
            image_size=total,
            session_id=resume.session_id,
            chunk_size=chunk_size,
        )

    @contextmanager
    def _managed_transport(self, config: UploadConfig) -> Iterator[Transport]:
        """统一管理真实串口和测试传输层的生命周期。

        有些传输层实现了上下文管理器，有些测试 Mock 没有；
        这里做一次适配，避免 workflow 主流程里出现资源释放分支。
        """

        transport = self._transport_factory(config)
        enter = getattr(transport, "__enter__", None)
        exit_ = getattr(transport, "__exit__", None)
        if enter is not None and exit_ is not None:
            with transport:  # type: ignore[operator]
                yield transport
            return

        try:
            yield transport
        finally:
            close = getattr(transport, "close", None)
            if close is not None:
                close()

    @staticmethod
    def _open_serial_transport(config: UploadConfig) -> SerialTransport:
        """按 UploadConfig 打开 CDC1_MGMT 串口传输层。"""

        return SerialTransport(
            port=config.port,
            baudrate=config.baudrate,
            timeout=config.timeout,
        )

    @staticmethod
    def _emit(
        callback: ProgressCallback | None,
        stage: str,
        current: int,
        total: int,
    ) -> None:
        """安全触发进度回调。

        callback 为 None 时直接忽略，便于 CLI 在不需要实时进度时复用同一流程。
        """

        if callback is not None:
            callback(stage, current, total)
