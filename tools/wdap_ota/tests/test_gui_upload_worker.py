import hashlib
import os
import struct

from wdap_ota.ota.workflow import UploadResult
from wdap_ota.protocol.constants import Target
from wdap_ota.protocol.crc import crc32
from wdap_ota.protocol.firmware import FirmwarePackage


class FakeWorkflow:
    """测试用 workflow，记录 GUI 传入配置并同步触发进度回调。"""

    def __init__(self) -> None:
        """创建测试对象。"""

        self.config = None
        self.package = None

    def upload_package(self, config, package, *, progress_callback=None):
        """模拟一次上传成功。"""

        self.config = config
        self.package = package
        if progress_callback is not None:
            progress_callback("upload", package.header.image_size, package.header.image_size)
        return UploadResult(
            final_offset=package.header.image_size,
            image_size=package.header.image_size,
            session_id=0x33,
            chunk_size=512,
        )


def test_upload_worker_calls_workflow_and_emits_progress():
    """验证 GUI 后台 worker 复用 OtaWorkflow，并把进度和完成信号发出来。"""

    from wdap_ota.gui.upload_worker import UploadWorker
    from wdap_ota.ota.workflow import UploadConfig

    workflow = FakeWorkflow()
    package = _build_package(b"abc")
    config = UploadConfig(port="COM7", target=Target.LOCAL_CH32, chunk_size=512)
    worker = UploadWorker(workflow, config, package)
    progress_events = []
    finished_results = []

    worker.progress.connect(lambda stage, current, total: progress_events.append((stage, current, total)))
    worker.finished.connect(finished_results.append)

    worker.run()

    assert workflow.config == config
    assert workflow.package == package
    assert progress_events == [("upload", 3, 3)]
    assert finished_results[0].final_offset == 3


def test_main_window_start_upload_uses_injected_worker_factory(tmp_path):
    """验证主窗口开始按钮会根据界面状态创建上传任务配置。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from wdap_ota.gui.main_window import OtaMainWindow
    from wdap_ota.ota.workflow import UploadConfig

    created = []

    def fake_worker_factory(config: UploadConfig, package: FirmwarePackage):
        """记录 GUI 生成的上传配置，返回 None 让测试不启动真实线程。"""

        created.append((config, package))
        return None

    app = QApplication.instance() or QApplication([])
    firmware_path = tmp_path / "app.wdapfw"
    firmware_path.write_bytes(_build_package_bytes(b"abc"))
    window = OtaMainWindow(
        port_lister=lambda: [],
        upload_worker_factory=fake_worker_factory,
    )
    window.port_combo.addItem("COM7 - WDAP CDC1", "COM7")
    window.load_firmware_package(firmware_path)

    window.start_upload()

    assert created[0][0].port == "COM7"
    assert created[0][0].target == Target.LOCAL_CH32
    assert created[0][1].payload == b"abc"
    assert "升级任务已创建" in window.status_label.text()

    window.close()
    assert app is not None


def test_main_window_clears_worker_references_after_cleanup():
    """验证上传线程结束后的引用清理逻辑，避免下一次上传复用已释放 Qt 对象。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from wdap_ota.gui.main_window import OtaMainWindow

    app = QApplication.instance() or QApplication([])
    window = OtaMainWindow(port_lister=lambda: [])
    window._upload_thread = object()
    window._upload_worker = object()

    window.on_upload_cleanup()

    assert window._upload_thread is None
    assert window._upload_worker is None

    window.close()
    assert app is not None


def _build_package(payload: bytes) -> FirmwarePackage:
    """构造已校验的测试固件包。"""

    return FirmwarePackage.from_bytes(_build_package_bytes(payload))


def _build_package_bytes(payload: bytes) -> bytes:
    """构造测试固件包字节。"""

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
    return header + payload
