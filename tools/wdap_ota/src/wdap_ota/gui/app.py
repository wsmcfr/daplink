from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from wdap_ota.gui.main_window import OtaMainWindow


def main(argv: list[str] | None = None) -> int:
    """启动 WDAP OTA 图形上位机。

    参数:
        argv: Qt 应用参数，None 时使用 sys.argv。
    返回:
        int，Qt 事件循环退出码。
    """

    app = QApplication(argv if argv is not None else sys.argv)
    window = OtaMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    # 作为模块运行时启动 Qt 事件循环；测试只导入窗口类，不会进入这里。
    raise SystemExit(main(sys.argv))
