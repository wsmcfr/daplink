from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wdap_ota.protocol.constants import Target
from wdap_ota.protocol.firmware import FirmwarePackage
from wdap_ota.ota.workflow import OtaWorkflow, UploadConfig, UploadResult
from wdap_ota.transport.ports import SerialPortInfo, list_serial_ports
from wdap_ota.gui.upload_worker import UploadWorker


class OtaMainWindow(QMainWindow):
    """WDAP OTA 上位机第一版主窗口。

    界面定位是工程调试工具，不做营销页：
    左侧放连接、目标和固件选择这些高频操作；
    右侧放固件包信息、升级进度和日志，方便联调时快速定位问题。
    """

    def __init__(
        self,
        *,
        port_lister: Callable[[], list[SerialPortInfo]] = list_serial_ports,
        upload_worker_factory: Callable[[UploadConfig, FirmwarePackage], UploadWorker | None]
        | None = None,
    ) -> None:
        """创建主窗口并初始化控件状态。

        参数:
            port_lister: 串口枚举函数，测试可注入固定列表，真实运行使用 pyserial 枚举。
            upload_worker_factory: 上传任务工厂，测试可注入记录函数，真实运行创建 UploadWorker。
        """

        super().__init__()
        self.setWindowTitle("WDAP OTA Host")
        self.resize(960, 620)
        self._port_lister = port_lister
        self._upload_worker_factory = upload_worker_factory or self._create_upload_worker
        self.current_package: FirmwarePackage | None = None
        self._upload_thread: QThread | None = None
        self._upload_worker: UploadWorker | None = None

        self._build_widgets()
        self._build_layout()
        self._connect_static_actions()
        self.refresh_ports()

    def _build_widgets(self) -> None:
        """创建所有控件并设置 objectName，便于测试和后续自动化操作定位。"""

        self.port_combo = QComboBox()
        self.port_combo.setObjectName("portCombo")
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(160)

        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("refreshButton")
        self.connect_button = QPushButton("连接")
        self.connect_button.setObjectName("connectButton")

        self.target_combo = QComboBox()
        self.target_combo.setObjectName("targetCombo")
        for target in Target:
            if target != Target.BROADCAST_INFO:
                self.target_combo.addItem(target.name, target)

        self.firmware_path_edit = QLineEdit()
        self.firmware_path_edit.setObjectName("firmwarePathEdit")
        self.firmware_path_edit.setPlaceholderText("选择 .wdapfw 固件包")
        self.browse_button = QPushButton("浏览")
        self.browse_button.setObjectName("browseButton")

        self.package_table = QTableWidget(0, 2)
        self.package_table.setObjectName("packageTable")
        self.package_table.setHorizontalHeaderLabels(["字段", "值"])
        self.package_table.horizontalHeader().setStretchLastSection(True)
        self.package_table.verticalHeader().setVisible(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.status_label = QLabel("未连接")
        self.status_label.setObjectName("statusLabel")

        self.start_button = QPushButton("开始")
        self.start_button.setObjectName("startButton")
        self.pause_button = QPushButton("暂停")
        self.pause_button.setObjectName("pauseButton")
        self.resume_button = QPushButton("继续")
        self.resume_button.setObjectName("resumeButton")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("cancelButton")

        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("升级日志")

    def _build_layout(self) -> None:
        """按工程工具布局组织控件，保持信息密度和操作路径清晰。"""

        central = QWidget()
        root_layout = QGridLayout(central)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setHorizontalSpacing(14)
        root_layout.setVerticalSpacing(12)

        connection_group = QGroupBox("连接")
        connection_layout = QFormLayout(connection_group)
        connection_row = QHBoxLayout()
        connection_row.addWidget(self.port_combo, 1)
        connection_row.addWidget(self.refresh_button)
        connection_row.addWidget(self.connect_button)
        connection_layout.addRow("管理串口", connection_row)

        target_group = QGroupBox("目标")
        target_layout = QFormLayout(target_group)
        target_layout.addRow("升级目标", self.target_combo)

        firmware_group = QGroupBox("固件")
        firmware_layout = QFormLayout(firmware_group)
        firmware_row = QHBoxLayout()
        firmware_row.addWidget(self.firmware_path_edit, 1)
        firmware_row.addWidget(self.browse_button)
        firmware_layout.addRow("固件包", firmware_row)

        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)
        action_layout.addWidget(self.status_label)
        action_layout.addWidget(self.progress_bar)
        button_row = QHBoxLayout()
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.pause_button)
        button_row.addWidget(self.resume_button)
        button_row.addWidget(self.cancel_button)
        action_layout.addLayout(button_row)

        left_panel = QVBoxLayout()
        left_panel.addWidget(connection_group)
        left_panel.addWidget(target_group)
        left_panel.addWidget(firmware_group)
        left_panel.addWidget(action_group)
        left_panel.addStretch(1)

        package_group = QGroupBox("固件包信息")
        package_layout = QVBoxLayout(package_group)
        package_layout.addWidget(self.package_table)

        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(self.log_output)

        root_layout.addLayout(left_panel, 0, 0, 2, 1)
        root_layout.addWidget(package_group, 0, 1)
        root_layout.addWidget(log_group, 1, 1)
        root_layout.setColumnStretch(0, 0)
        root_layout.setColumnStretch(1, 1)
        root_layout.setRowStretch(0, 1)
        root_layout.setRowStretch(1, 1)

        self.setCentralWidget(central)

    def _connect_static_actions(self) -> None:
        """连接当前阶段的静态按钮行为。

        第一版 GUI 壳先把操作路径和状态区搭好；真实上传线程后续再接入 OtaSession，
        这样可以避免 UI 直接拼协议帧。
        """

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(lambda: self.append_log("连接 CDC1_MGMT 待接入"))
        self.browse_button.clicked.connect(self.browse_firmware)
        self.start_button.clicked.connect(self.start_upload)
        self.pause_button.clicked.connect(lambda: self.append_log("暂停任务待接入"))
        self.resume_button.clicked.connect(lambda: self.append_log("继续任务待接入"))
        self.cancel_button.clicked.connect(lambda: self.append_log("取消任务待接入"))

    def refresh_ports(self) -> None:
        """刷新串口下拉框。

        返回:
            None。每项 itemData 保存真实 COM 名称，itemText 显示描述辅助用户识别。
        """

        current_port = self.selected_port()
        self.port_combo.clear()
        for port in self._port_lister():
            text = f"{port.device} - {port.description}" if port.description else port.device
            self.port_combo.addItem(text, port.device)

        if current_port:
            for index in range(self.port_combo.count()):
                if self.port_combo.itemData(index) == current_port:
                    self.port_combo.setCurrentIndex(index)
                    break
        self.append_log(f"已刷新串口列表：{self.port_combo.count()} 个")

    def selected_port(self) -> str:
        """返回当前选择的真实串口名。"""

        data = self.port_combo.currentData()
        if isinstance(data, str):
            return data
        return self.port_combo.currentText().split(" - ", 1)[0].strip()

    def selected_target(self) -> Target:
        """返回当前选择的 OTA 目标。"""

        data = self.target_combo.currentData()
        if isinstance(data, Target):
            return data
        return Target[self.target_combo.currentText()]

    def browse_firmware(self) -> None:
        """打开固件选择对话框并解析选中的 .wdapfw。

        真实解析逻辑放在 load_firmware_package，方便测试直接调用而不依赖弹窗。
        """

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择 WDAP 固件包",
            "",
            "WDAP Firmware (*.wdapfw);;All Files (*)",
        )
        if not filename:
            return
        self.load_firmware_package(Path(filename))

    def load_firmware_package(self, path: str | Path) -> FirmwarePackage:
        """从磁盘读取、校验并展示固件包信息。

        参数:
            path: .wdapfw 文件路径。
        返回:
            FirmwarePackage，供后续启动上传任务使用。
        """

        firmware_path = Path(path)
        package = FirmwarePackage.from_bytes(firmware_path.read_bytes())
        self.current_package = package
        self.firmware_path_edit.setText(str(firmware_path))
        self.set_package_rows(_package_rows(package))
        self.status_label.setText("固件包已解析")
        self.append_log(f"固件包已解析：{firmware_path}")
        return package

    def start_upload(self) -> None:
        """根据当前界面状态创建并启动 OTA 上传任务。

        返回:
            None。真实任务会放到 QThread，测试注入工厂返回 None 时只验证配置生成。
        """

        if self.current_package is None:
            self.status_label.setText("请先选择固件包")
            self.append_log("未选择固件包，无法开始升级")
            return

        port = self.selected_port()
        if not port:
            self.status_label.setText("请先选择 CDC1_MGMT 串口")
            self.append_log("未选择管理串口，无法开始升级")
            return

        config = UploadConfig(port=port, target=self.selected_target())
        worker = self._upload_worker_factory(config, self.current_package)
        self.status_label.setText("升级任务已创建")
        self.append_log(f"升级任务已创建：{port} -> {config.target.name}")

        if worker is None:
            return

        self._start_worker_thread(worker)

    def _create_upload_worker(
        self,
        config: UploadConfig,
        package: FirmwarePackage,
    ) -> UploadWorker:
        """创建真实上传 worker。

        参数:
            config: 界面生成的上传配置。
            package: 当前已解析固件包。
        返回:
            UploadWorker，会复用 OtaWorkflow。
        """

        return UploadWorker(OtaWorkflow(), config, package)

    def _start_worker_thread(self, worker: UploadWorker) -> None:
        """把上传 worker 移入后台线程并启动。

        这样串口读写和 OTA ACK 等待不会阻塞 Qt 主线程；所有 UI 更新都通过 signal 回到主线程。
        """

        self._upload_thread = QThread(self)
        self._upload_worker = worker
        worker.moveToThread(self._upload_thread)
        self._upload_thread.started.connect(worker.run)
        worker.progress.connect(self.on_upload_progress)
        worker.finished.connect(self.on_upload_finished)
        worker.failed.connect(self.on_upload_failed)
        worker.finished.connect(self._upload_thread.quit)
        worker.failed.connect(self._upload_thread.quit)
        self._upload_thread.finished.connect(worker.deleteLater)
        self._upload_thread.finished.connect(self.on_upload_cleanup)
        self._upload_thread.finished.connect(self._upload_thread.deleteLater)
        self.start_button.setEnabled(False)
        self._upload_thread.start()

    def on_upload_cleanup(self) -> None:
        """清理后台上传任务引用。

        Qt 线程 finished 后 worker/thread 会被 deleteLater 释放；
        这里同步清空 Python 侧引用，避免下一次上传误碰已释放对象。
        """

        self._upload_thread = None
        self._upload_worker = None

    def on_upload_progress(self, stage: str, current: int, total: int) -> None:
        """处理后台上传进度信号。"""

        if total > 0:
            self.progress_bar.setValue(int(current * 100 / total))
        self.status_label.setText(f"{stage}: {current}/{total}")
        if stage in {"upload", "done"}:
            self.append_log(f"{stage}: {current}/{total}")

    def on_upload_finished(self, result: UploadResult) -> None:
        """处理上传完成信号，恢复按钮状态并记录结果。"""

        self.start_button.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText("上传完成")
        self.append_log(
            f"上传完成：final_offset={result.final_offset}, "
            f"image_size={result.image_size}, session_id=0x{result.session_id:08X}"
        )

    def on_upload_failed(self, message: str) -> None:
        """处理上传失败信号，恢复按钮并显示错误原因。"""

        self.start_button.setEnabled(True)
        self.status_label.setText("上传失败")
        self.append_log(f"上传失败：{message}")

    def append_log(self, message: str) -> None:
        """向日志窗口追加一行文本。

        参数:
            message: 要显示给用户的日志内容。
        返回:
            None。光标会移动到底部，便于持续观察最新状态。
        """

        self.log_output.appendPlainText(message)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

    def set_package_rows(self, rows: list[tuple[str, str]]) -> None:
        """更新固件包信息表。

        参数:
            rows: 每项为 字段名/字段值 的二元组。
        返回:
            None。该方法后续由固件选择逻辑调用。
        """

        self.package_table.setRowCount(len(rows))
        for row_index, (name, value) in enumerate(rows):
            name_item = QTableWidgetItem(name)
            value_item = QTableWidgetItem(value)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            self.package_table.setItem(row_index, 0, name_item)
            self.package_table.setItem(row_index, 1, value_item)


def _package_rows(package: FirmwarePackage) -> list[tuple[str, str]]:
    """把固件包头转换成 GUI 表格行。

    返回:
        list[tuple[str, str]]，字段名保持稳定，便于后续日志导出和测试定位。
    """

    header = package.header
    return [
        ("package_version", str(header.package_version)),
        ("target_chip", str(header.target_chip)),
        ("target_role", str(header.target_role)),
        ("hardware_rev_mask", f"0x{header.hardware_rev_mask:08X}"),
        ("fw_version", f"0x{header.fw_version:08X}"),
        ("min_boot_version", f"0x{header.min_boot_version:08X}"),
        ("image_size", str(header.image_size)),
        ("image_crc32", f"0x{header.image_crc32:08X}"),
        ("image_sha256", header.image_sha256.hex()),
    ]
