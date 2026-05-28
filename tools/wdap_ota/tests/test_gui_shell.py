import os
import hashlib
import struct

from wdap_ota.protocol.crc import crc32
from wdap_ota.protocol.firmware import FirmwarePackage


def test_main_window_exposes_expected_controls():
    """验证 GUI 壳包含连接、目标、固件、进度和日志这些第一版核心控件。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from wdap_ota.gui.main_window import OtaMainWindow

    app = QApplication.instance() or QApplication([])
    window = OtaMainWindow()

    assert window.windowTitle() == "WDAP OTA Host"
    assert window.findChild(type(window.port_combo), "portCombo") is window.port_combo
    assert window.findChild(type(window.target_combo), "targetCombo") is window.target_combo
    assert window.findChild(type(window.progress_bar), "progressBar") is window.progress_bar
    assert window.findChild(type(window.log_output), "logOutput") is window.log_output

    window.close()
    # 保留引用，避免部分 Qt 绑定在测试结束前提前清理应用对象。
    assert app is not None


def test_main_window_refresh_ports_uses_injected_lister():
    """验证 GUI 能通过注入的串口枚举函数刷新 COM 列表。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from wdap_ota.gui.main_window import OtaMainWindow
    from wdap_ota.transport.ports import SerialPortInfo

    app = QApplication.instance() or QApplication([])
    window = OtaMainWindow(port_lister=lambda: [SerialPortInfo("COM7", "WDAP CDC1")])

    window.refresh_ports()

    assert window.port_combo.count() == 1
    assert window.port_combo.itemText(0) == "COM7 - WDAP CDC1"
    assert window.port_combo.itemData(0) == "COM7"

    window.close()
    assert app is not None


def test_main_window_loads_firmware_package(tmp_path):
    """验证 GUI 能离线解析 .wdapfw 并展示关键包头字段。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from wdap_ota.gui.main_window import OtaMainWindow

    app = QApplication.instance() or QApplication([])
    firmware_path = tmp_path / "app.wdapfw"
    firmware_path.write_bytes(_build_package_bytes(b"abc"))
    window = OtaMainWindow()

    package = window.load_firmware_package(firmware_path)

    assert package.header.image_size == 3
    assert window.package_table.rowCount() > 0
    assert _table_value(window, "image_size") == "3"
    assert "固件包已解析" in window.status_label.text()

    window.close()
    assert app is not None


def _build_package_bytes(payload: bytes) -> bytes:
    """构造 GUI 测试用固件包字节。"""

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


def _table_value(window, name: str) -> str | None:
    """从固件包信息表中读取指定字段值。"""

    for row in range(window.package_table.rowCount()):
        key_item = window.package_table.item(row, 0)
        value_item = window.package_table.item(row, 1)
        if key_item is not None and key_item.text() == name and value_item is not None:
            return value_item.text()
    return None
