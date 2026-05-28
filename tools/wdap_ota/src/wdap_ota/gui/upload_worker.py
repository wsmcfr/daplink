from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from wdap_ota.ota.workflow import OtaWorkflow, UploadConfig, UploadResult
from wdap_ota.protocol.firmware import FirmwarePackage


class UploadWorker(QObject):
    """GUI 后台上传任务。

    该对象不直接操作任何控件，只通过 Qt Signal 把进度、完成和错误通知主线程；
    真正的协议流程委托给 OtaWorkflow，避免 UI 层拼帧或复制 OTA 状态机。
    """

    progress = Signal(str, int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        workflow: OtaWorkflow,
        config: UploadConfig,
        package: FirmwarePackage,
    ) -> None:
        """创建上传任务。

        参数:
            workflow: CLI/GUI 共用的上传流程对象。
            config: 串口、目标和分片设置。
            package: 已校验固件包。
        返回:
            None。
        """

        super().__init__()
        self._workflow = workflow
        self._config = config
        self._package = package

    @Slot()
    def run(self) -> None:
        """执行上传流程并发出 Qt 信号。

        返回:
            None。成功发出 finished，异常发出 failed，便于主线程恢复按钮状态。
        """

        try:
            result = self._workflow.upload_package(
                self._config,
                self._package,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:  # noqa: BLE001 - GUI 线程边界需要把未知异常转成错误信号。
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
