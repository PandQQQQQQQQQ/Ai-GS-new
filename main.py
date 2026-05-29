"""
A股上市公司新闻自动化收集与AI评估软件
程序启动入口

作者: AI Assistant
创建日期: 2026-05-29
"""

import sys
import subprocess
from PySide6.QtWidgets import QApplication, QSplashScreen, QLabel, QVBoxLayout, QProgressBar
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QColor, QFont
from ui.main_window import MainWindow


def auto_update_akshare():
    """
    自动更新 AkShare 库
    在后台静默执行 pip install --upgrade akshare
    """
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "akshare", "-q"],
            capture_output=True,
            timeout=120
        )
    except Exception:
        pass  # 更新失败不影响程序启动


def show_splash_and_launch(app: QApplication) -> MainWindow:
    """
    显示启动画面，在后台更新AkShare后启动主窗口
    
    Args:
        app: QApplication实例
        
    Returns:
        MainWindow: 主窗口实例
    """
    # 创建启动画面
    splash_pixmap = QPixmap(600, 300)
    splash_pixmap.fill(QColor("#1a1a2e"))

    splash = QSplashScreen(splash_pixmap)
    splash.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

    # 启动画面内容
    layout = QVBoxLayout(splash)
    layout.setContentsMargins(40, 40, 40, 40)

    title_label = QLabel("A股新闻AI评估系统")
    title_label.setStyleSheet("color: #e0e0e0; font-size: 28px; font-weight: bold;")
    title_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(title_label)

    version_label = QLabel("v1.0.0")
    version_label.setStyleSheet("color: #888; font-size: 14px;")
    version_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(version_label)

    layout.addSpacing(20)

    status_label = QLabel("正在启动...")
    status_label.setStyleSheet("color: #4FC3F7; font-size: 14px;")
    status_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(status_label)

    progress = QProgressBar()
    progress.setRange(0, 0)  # 不确定进度条（滚动模式）
    progress.setMaximumHeight(6)
    progress.setTextVisible(False)
    progress.setStyleSheet("""
        QProgressBar {
            background-color: #333;
            border-radius: 3px;
        }
        QProgressBar::chunk {
            background-color: #4FC3F7;
            border-radius: 3px;
        }
    """)
    layout.addWidget(progress)

    splash.show()
    app.processEvents()

    # 后台自动更新 AkShare
    status_label.setText("正在检查 AkShare 更新...")
    app.processEvents()
    auto_update_akshare()

    status_label.setText("正在加载主界面...")
    app.processEvents()

    # 创建主窗口
    window = MainWindow()

    splash.finish(window)
    return window


def main():
    """
    程序主入口函数
    初始化Qt应用并启动主窗口
    """
    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # 创建Qt应用实例
    app = QApplication(sys.argv)
    app.setApplicationName("A股新闻AI评估系统")
    app.setApplicationVersion("1.0.0")
    
    # 设置全局样式
    app.setStyle("Fusion")
    
    # 显示启动画面并自动更新AkShare
    window = show_splash_and_launch(app)
    window.show()
    
    # 进入事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
