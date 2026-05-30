"""
主窗口模块
使用 PySide6 构建现代化的主界面
布局：左侧新闻列表，右侧详情和AI评估结果
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QLabel, QPushButton, QGroupBox, QProgressBar,
    QMessageBox, QAbstractItemView, QComboBox, QLineEdit,
    QDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QDateTime, QUrl, QTimer
from PySide6.QtGui import QFont, QColor, QBrush, QDesktopServices
from PySide6.QtWebEngineWidgets import QWebEngineView

from db.database import Database
from scraper.news_scraper import NewsScraper
from ai.analyzer import AIAnalyzer
from ui.market_radar_dialog import MarketRadarDialog


class NewsFetchWorker(QThread):
    """
    新闻获取工作线程
    避免在UI主线程中进行网络请求，防止界面卡顿
    """
    # 定义信号：获取到新闻数据时发射
    news_fetched = Signal(list)
    # 定义信号：发生错误时发射
    error_occurred = Signal(str)
    # 定义信号：进度更新
    progress_updated = Signal(int)
    
    def __init__(self, scraper: NewsScraper):
        super().__init__()
        self.scraper = scraper
        self.is_running = True
    
    def run(self):
        """线程执行函数"""
        try:
            self.progress_updated.emit(20)
            # 获取最新新闻
            news_list = self.scraper.fetch_latest_news()
            self.progress_updated.emit(80)
            
            if self.is_running:
                self.news_fetched.emit(news_list)
            self.progress_updated.emit(100)
        except Exception as e:
            if self.is_running:
                self.error_occurred.emit(str(e))
    
    def stop(self):
        """停止线程"""
        self.is_running = False
        self.wait()


class NewsRefreshWorker(QThread):
    """
    新闻刷新工作线程（仅负责采集新闻，不操作数据库）
    数据库保存操作在主线程执行，避免SQLite线程安全问题
    """
    # 定义信号：采集完成时发射，携带新闻列表
    data_fetched = Signal(list)
    # 定义信号：发生错误时发射
    error_occurred = Signal(str)
    # 定义信号：进度更新
    progress_updated = Signal(int)
    
    def __init__(self, scraper: NewsScraper):
        super().__init__()
        self.scraper = scraper
        self.is_running = True
    
    def run(self):
        """
        线程执行函数
        仅执行采集操作，不涉及数据库操作
        """
        try:
            self.progress_updated.emit(30)
            
            # 采集新闻（仅网络请求，无数据库操作）
            news_list = self.scraper.fetch_all_sources(limit_per_source=50)
            
            if not self.is_running:
                return
            
            self.progress_updated.emit(80)
            
            # 发射信号，将数据传回主线程
            self.data_fetched.emit(news_list)
            self.progress_updated.emit(100)
            
        except Exception as e:
            if self.is_running:
                self.error_occurred.emit(str(e))
    
    def stop(self):
        """停止线程"""
        self.is_running = False
        self.wait()


class FullContentFetchWorker(QThread):
    """
    全文抓取工作线程
    当新闻内容可能被截断时，后台抓取原文网页的完整内容
    """
    # 定义信号：抓取完成时发射
    content_ready = Signal(dict)
    
    def __init__(self, scraper, url: str, original_content: str):
        super().__init__()
        self.scraper = scraper
        self.url = url
        self.original_content = original_content
    
    def run(self):
        """线程执行函数"""
        try:
            full_content = self.scraper.fetch_full_content(self.url)
            if full_content and len(full_content) > len(self.original_content):
                self.content_ready.emit({
                    'success': True,
                    'content': full_content,
                    'original': self.original_content
                })
            else:
                self.content_ready.emit({
                    'success': False,
                    'content': None,
                    'original': self.original_content
                })
        except Exception as e:
            print(f"全文抓取线程异常: {e}")
            self.content_ready.emit({
                'success': False,
                'content': None,
                'original': self.original_content
            })


class AIAnalyzeWorker(QThread):
    """
    AI分析工作线程
    在后台进行AI评估，不阻塞UI
    """
    # 定义信号：分析完成时发射
    analysis_completed = Signal(dict)
    # 定义信号：发生错误时发射
    error_occurred = Signal(str)
    # 定义信号：进度更新
    progress_updated = Signal(int)
    
    def __init__(self, analyzer: AIAnalyzer, news_content: str):
        super().__init__()
        self.analyzer = analyzer
        self.news_content = news_content
        self.is_running = True
    
    def run(self):
        """线程执行函数"""
        try:
            self.progress_updated.emit(30)
            # 调用AI进行分析
            result = self.analyzer.analyze_news(self.news_content)
            self.progress_updated.emit(100)
            
            if self.is_running:
                self.analysis_completed.emit(result)
        except Exception as e:
            if self.is_running:
                self.error_occurred.emit(str(e))
    
    def stop(self):
        """停止线程"""
        self.is_running = False
        self.wait()


class IndexButtonWorker(QThread):
    """
    大盘按钮文本刷新工作线程
    通过新浪财经接口获取上证指数
    """
    index_ready = Signal(str)   # 格式如 "上证指数 +1.23%"
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._is_running = True

    def run(self):
        # ========== 禁用代理 ==========
        import os
        os.environ['NO_PROXY'] = '*'
        os.environ['no_proxy'] = '*'
        for _key in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
            if _key in os.environ:
                del os.environ[_key]

        # ========== 通过新浪接口获取指数数据 ==========
        import time
        import random
        
        for attempt in range(1, 3):  # 最多2次
            if not self._is_running:
                return
            try:
                from ui.market_radar_dialog import _fetch_index_data
                time.sleep(random.uniform(0.1, 0.3))
                
                records = _fetch_index_data()
                
                if not self._is_running:
                    return
                # 查找上证指数（代码 000001）
                for rec in records:
                    code = str(rec.get("代码", ""))
                    if code == "000001":
                        price = float(rec.get("最新价", 0))
                        change_pct = float(rec.get("涨跌幅", 0))
                        if change_pct > 0:
                            text = f"上证指数 {price:.2f}  +{change_pct:.2f}%"
                        else:
                            text = f"上证指数 {price:.2f}  {change_pct:.2f}%"
                        if self._is_running:
                            self.index_ready.emit(text)
                        return
            except Exception as e:
                print(f"[Debug] IndexButtonWorker 第{attempt}次异常: {e}")
                if attempt < 2:
                    time.sleep(2)

    def stop(self):
        self._is_running = False
        self.wait()


class MainWindow(QMainWindow):
    """
    应用程序主窗口
    采用左右分栏布局设计
    """
    
    def __init__(self):
        super().__init__()
        
        # 初始化组件
        self.db = Database()
        self.scraper = NewsScraper()
        self.analyzer = AIAnalyzer()
        
        # 工作线程
        self.fetch_worker = None
        self.analyze_worker = None
        
        # 当前选中的新闻
        self.current_news = None
        
        # ---------- 大盘行情定时器（每10秒刷新按钮文本） ----------
        self.market_timer = QTimer(self)
        self.market_timer.timeout.connect(self._update_market_btn_text)
        self._market_btn_text = "上证指数 --  🔄 点击进入雷达"
        
        # 初始化UI
        self.init_ui()
        
        # 加载已有新闻
        self.load_news_from_db()
        
        # 启动大盘定时器
        self._update_market_btn_text()   # 立即首次刷新
        self.market_timer.start(5000)   # 每5秒刷新
    
    def init_ui(self):
        """初始化用户界面"""
        # 设置窗口属性
        self.setWindowTitle("A股上市公司新闻AI评估系统 v1.0")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 创建分割器，实现左右分栏
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # ========== 左侧区域：新闻列表 ==========
        left_widget = self.create_left_panel()
        splitter.addWidget(left_widget)
        
        # ========== 右侧区域：详情和AI评估 ==========
        right_widget = self.create_right_panel()
        splitter.addWidget(right_widget)
        
        # 设置分割比例（左:右 = 2:3）
        splitter.setSizes([600, 900])
        
        # 设置状态栏
        self.statusBar().showMessage("就绪")
    
    def create_left_panel(self) -> QWidget:
        """
        创建左侧面板：新闻列表区域
        
        Returns:
            QWidget: 左侧面板部件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # ----- 控制区域 -----
        control_group = QGroupBox("新闻采集控制")
        control_layout = QVBoxLayout(control_group)
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索新闻...")
        self.search_input.textChanged.connect(self.filter_news)
        search_layout.addWidget(self.search_input)
        control_layout.addLayout(search_layout)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        # 刷新新闻按钮（采集->保存->展示闭环）
        self.refresh_btn = QPushButton("🔄 刷新新闻")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_news)
        button_layout.addWidget(self.refresh_btn)
        
        # 大盘行情看板按钮（替代原来的"获取最新新闻"）
        # 点击后弹出行情雷达对话框，不再执行新闻抓取
        self.market_btn = QPushButton("上证指数 --  🔄 点击进入雷达")
        self.market_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #283593);
                color: #ffffff;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #3f51b5;
                min-height: 34px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #283593, stop:1 #3949ab);
                border: 1px solid #5c6bc0;
            }
        """)
        self.market_btn.clicked.connect(self._open_market_radar)
        button_layout.addWidget(self.market_btn, stretch=1)  # 弹性占满
        
        # 小巧的新闻抓取按钮（保留原"获取最新新闻"的逻辑）
        self.fetch_btn_small = QPushButton("📥")
        self.fetch_btn_small.setToolTip("获取最新新闻（后台采集）")
        self.fetch_btn_small.setMaximumWidth(36)
        self.fetch_btn_small.setStyleSheet("""
            QPushButton {
                background-color: #1565C0;
                color: white;
                padding: 8px 4px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        self.fetch_btn_small.clicked.connect(self.fetch_news)
        button_layout.addWidget(self.fetch_btn_small)
        
        # AI分析选中按钮
        self.analyze_btn = QPushButton("🤖 AI分析选中新闻")
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        self.analyze_btn.clicked.connect(self.analyze_selected_news)
        self.analyze_btn.setEnabled(False)  # 初始禁用
        button_layout.addWidget(self.analyze_btn)
        
        control_layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        control_layout.addWidget(self.progress_bar)
        
        layout.addWidget(control_group)
        
        # ----- 新闻列表表格 -----
        list_group = QGroupBox("新闻列表")
        list_layout = QVBoxLayout(list_group)
        
        self.news_table = QTableWidget()
        self.news_table.setColumnCount(5)
        self.news_table.setHorizontalHeaderLabels([
            "ID", "发布时间", "标题", "来源", "AI评分"
        ])
        
        # 设置表格属性
        header = self.news_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 时间
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # 标题
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 来源
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 评分
        
        self.news_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.news_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.news_table.setAlternatingRowColors(True)
        self.news_table.verticalHeader().setVisible(False)
        self.news_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 连接选择事件
        self.news_table.itemSelectionChanged.connect(self.on_news_selected)
        
        list_layout.addWidget(self.news_table)
        layout.addWidget(list_group, stretch=1)
        
        return panel
    
    def create_right_panel(self) -> QWidget:
        """
        创建右侧面板：详情和AI评估区域
        
        Returns:
            QWidget: 右侧面板部件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # ----- 新闻详情区域 -----
        detail_group = QGroupBox("新闻详情")
        detail_layout = QVBoxLayout(detail_group)
        
        # 标题标签
        self.detail_title = QLabel("请选择一条新闻")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.detail_title.setFont(title_font)
        self.detail_title.setWordWrap(True)
        self.detail_title.setAlignment(Qt.AlignCenter)
        self.detail_title.setStyleSheet("""
            QLabel {
                background: transparent;
                padding: 8px 4px 4px 4px;
            }
        """)
        detail_layout.addWidget(self.detail_title)
        
        # 元信息标签（放在内容区域下方右下角）
        self.detail_meta = QLabel("")
        meta_font = QFont()
        meta_font.setPointSize(10)
        self.detail_meta.setFont(meta_font)
        self.detail_meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.detail_meta.setStyleSheet("""
            QLabel {
                color: #888888;
                background: transparent;
                padding: 4px 8px 2px 0;
            }
        """)
        # 暂不添加到布局，将在 detail_content 之后添加
        
        # 内容浏览器控件（支持HTML渲染和图片显示）
        self.detail_content = QWebEngineView()
        self.detail_content.setMinimumHeight(200)
        # 网页加载完成后，自动净化内容（提取正文+注入暗黑样式）
        self.detail_content.loadFinished.connect(self._on_webpage_loaded)
        detail_layout.addWidget(self.detail_content, stretch=1)  # stretch=1 让浏览器占满剩余空间

        # 元信息（发布时间+来源）放在内容下方右下角
        detail_layout.addWidget(self.detail_meta)
        
        # 原文链接（可点击）
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("原文链接:"))
        self.detail_url = QLabel("-")
        self.detail_url.setStyleSheet("""
            QLabel {
                color: #2196F3;
                text-decoration: underline;
            }
            QLabel:hover {
                color: #1976D2;
            }
        """)
        self.detail_url.setCursor(Qt.PointingHandCursor)
        self.detail_url.mousePressEvent = self._on_url_clicked
        url_layout.addWidget(self.detail_url, stretch=1)
        url_layout.addStretch()
        detail_layout.addLayout(url_layout)
        
        layout.addWidget(detail_group, stretch=3)
        
        # ----- AI评估结果区域 -----
        ai_group = QGroupBox("AI 评估结果")
        ai_layout = QVBoxLayout(ai_group)
        
        # AI模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("AI模型:"))
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.addItems(["DeepSeek", "Mini", "Gemini"])
        model_layout.addWidget(self.ai_model_combo)
        model_layout.addStretch()
        ai_layout.addLayout(model_layout)
        
        # AI评分显示
        score_layout = QHBoxLayout()
        score_layout.addWidget(QLabel("利好/利空评分:"))
        self.ai_score_label = QLabel("未分析")
        score_font = QFont()
        score_font.setPointSize(24)
        score_font.setBold(True)
        self.ai_score_label.setFont(score_font)
        self.ai_score_label.setStyleSheet("color: #999;")
        score_layout.addWidget(self.ai_score_label)
        score_layout.addStretch()
        ai_layout.addLayout(score_layout)
        
        # AI分析理由
        ai_layout.addWidget(QLabel("分析理由:"))
        self.ai_reason = QTextEdit()
        self.ai_reason.setReadOnly(True)
        self.ai_reason.setPlaceholderText("AI分析结果将显示在这里...")
        self.ai_reason.setMaximumHeight(150)
        ai_layout.addWidget(self.ai_reason)
        
        # 相关股票
        ai_layout.addWidget(QLabel("涉及股票:"))
        self.ai_stocks = QLabel("-")
        self.ai_stocks.setStyleSheet("color: #2196F3;")
        ai_layout.addWidget(self.ai_stocks)
        
        layout.addWidget(ai_group)
        
        return panel
    
    def refresh_news(self):
        """
        刷新新闻（完整闭环：采集 -> 保存 -> 展示）
        点击按钮后执行：
        1. 从财联社和东方财富采集最新新闻（在工作线程）
        2. 保存到数据库（在主线程，避免SQLite线程问题）
        3. 刷新UI列表显示
        """
        self.refresh_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(10)
        self.statusBar().showMessage("正在采集新闻...")
        
        # 创建工作线程仅执行采集（不操作数据库）
        self.refresh_worker = NewsRefreshWorker(self.scraper)
        self.refresh_worker.data_fetched.connect(self.on_refresh_data_fetched)
        self.refresh_worker.error_occurred.connect(self.on_refresh_error)
        self.refresh_worker.progress_updated.connect(self.progress_bar.setValue)
        self.refresh_worker.finished.connect(self.on_refresh_finished)
        self.refresh_worker.start()
    
    def on_refresh_data_fetched(self, news_list: list):
        """
        采集完成回调（在主线程执行数据库保存）
        
        Args:
            news_list: 采集到的新闻列表
        """
        self.statusBar().showMessage("正在保存到数据库...")
        self.progress_bar.setValue(85)
        
        try:
            # 在主线程执行数据库保存（避免SQLite线程问题）
            stats = self.db.save_news(news_list)
            
            # 刷新UI列表
            self.load_news_from_db()
            
            # 显示提示
            msg = f"刷新完成：共采集 {stats['total']} 条，新增 {stats['inserted']} 条，重复 {stats['duplicated']} 条"
            self.statusBar().showMessage(msg)
            
            # 弹出提示框
            QMessageBox.information(
                self, 
                "刷新完成", 
                f"新闻采集完成！\n\n"
                f"• 采集总数：{stats['total']} 条\n"
                f"• 新增入库：{stats['inserted']} 条\n"
                f"• 重复跳过：{stats['duplicated']} 条"
            )
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存到数据库时发生错误：\n{str(e)}")
            self.statusBar().showMessage("保存失败")
    
    def on_refresh_error(self, error_msg: str):
        """
        刷新失败回调
        
        Args:
            error_msg: 错误信息
        """
        QMessageBox.critical(self, "刷新失败", f"新闻刷新时发生错误：\n{error_msg}")
        self.statusBar().showMessage("刷新失败")
    
    def on_refresh_finished(self):
        """刷新线程结束回调"""
        self.refresh_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.refresh_worker = None
    
    def fetch_news(self):
        """获取最新新闻（仅采集，不自动保存）"""
        self.fetch_btn_small.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("正在获取新闻...")
        
        # 创建工作线程
        self.fetch_worker = NewsFetchWorker(self.scraper)
        self.fetch_worker.news_fetched.connect(self.on_news_fetched)
        self.fetch_worker.error_occurred.connect(self.on_fetch_error)
        self.fetch_worker.progress_updated.connect(self.progress_bar.setValue)
        self.fetch_worker.finished.connect(self.on_fetch_finished)
        self.fetch_worker.start()
    
    def on_news_fetched(self, news_list: list):
        """
        新闻获取完成回调
        
        Args:
            news_list: 获取到的新闻列表
        """
        # 保存到数据库（自动查重）
        added_count = 0
        for news in news_list:
            if self.db.insert_news(news):
                added_count += 1
        
        # 刷新列表
        self.load_news_from_db()
        
        # 显示提示
        self.statusBar().showMessage(
            f"获取完成：共 {len(news_list)} 条新闻，新增 {added_count} 条"
        )
    
    def on_fetch_error(self, error_msg: str):
        """
        新闻获取错误回调
        
        Args:
            error_msg: 错误信息
        """
        QMessageBox.critical(self, "获取失败", f"获取新闻时发生错误：\n{error_msg}")
        self.statusBar().showMessage("获取失败")
    
    def on_fetch_finished(self):
        """新闻获取线程结束回调"""
        self.fetch_btn_small.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.fetch_worker = None

    # ----------------------------------------------------------
    # 大盘行情看板按钮相关
    # ----------------------------------------------------------
    def _open_market_radar(self):
        """
        打开市场雷达对话框
        点击大盘行情按钮时触发，弹出 MarketRadarDialog
        """
        dialog = MarketRadarDialog(self)
        dialog.exec()
    
    def _update_market_btn_text(self):
        """
        每10秒触发：后台刷新大盘行情并更新按钮文本
        使用 AkShare 异步获取上证指数实时涨跌幅
        """
        # 启动工作线程获取指数数据（不阻塞UI）
        self._index_worker = IndexButtonWorker()
        self._index_worker.index_ready.connect(self._on_index_btn_data)
        self._index_worker.error_occurred.connect(self._on_index_btn_error)
        self._index_worker.finished.connect(self._cleanup_index_btn_worker)
        self._index_worker.start()
    
    def _on_index_btn_data(self, sh_text: str):
        """
        指数数据回调：更新按钮显示的文本
        
        Args:
            sh_text: 格式化后的上证指数文本，如 "上证指数 +1.23%"
        """
        self._market_btn_text = f"{sh_text}  🔄 点击进入雷达"
        self.market_btn.setText(self._market_btn_text)
    
    def _on_index_btn_error(self, _error_msg: str):
        """指数获取失败时显示默认文本"""
        self.market_btn.setText("上证指数 --  🔄 点击进入雷达")
    
    def _cleanup_index_btn_worker(self):
        self._index_worker = None
    
    def load_news_from_db(self):
        """从数据库加载新闻到列表（最多显示最近200条，避免卡顿）"""
        news_list = self.db.get_all_news(limit=200)
        self.populate_news_table(news_list)
    
    def populate_news_table(self, news_list: list):
        """
        填充新闻列表表格
        
        Args:
            news_list: 新闻数据列表
        """
        self.news_table.setRowCount(len(news_list))
        
        for row, news in enumerate(news_list):
            # ID
            id_item = QTableWidgetItem(str(news.get("id", "")))
            id_item.setData(Qt.UserRole, news)  # 存储完整数据
            self.news_table.setItem(row, 0, id_item)
            
            # 发布时间
            time_str = news.get("publish_time", "")
            if time_str:
                try:
                    dt = QDateTime.fromString(time_str, "yyyy-MM-dd hh:mm:ss")
                    time_str = dt.toString("MM-dd hh:mm")
                except:
                    pass
            self.news_table.setItem(row, 1, QTableWidgetItem(time_str))
            
            # 标题
            title_item = QTableWidgetItem(news.get("title", ""))
            self.news_table.setItem(row, 2, title_item)
            
            # 来源
            self.news_table.setItem(row, 3, QTableWidgetItem(news.get("source", "")))
            
            # AI评分
            score = news.get("ai_score")
            score_text = "-" if score is None else f"{score:+.1f}"
            score_item = QTableWidgetItem(score_text)
            
            # 根据评分设置颜色
            if score is not None:
                if score > 0:
                    score_item.setForeground(QBrush(QColor("#4CAF50")))  # 绿色-利好
                elif score < 0:
                    score_item.setForeground(QBrush(QColor("#F44336")))  # 红色-利空
                else:
                    score_item.setForeground(QBrush(QColor("#999999")))  # 灰色-中性
            
            self.news_table.setItem(row, 4, score_item)
    
    def on_news_selected(self):
        """新闻选择改变时的回调"""
        selected_items = self.news_table.selectedItems()
        if not selected_items:
            return
        
        # 获取选中行的数据
        row = selected_items[0].row()
        id_item = self.news_table.item(row, 0)
        news_data = id_item.data(Qt.UserRole)
        
        if news_data:
            self.current_news = news_data
            self.display_news_detail(news_data)
            self.analyze_btn.setEnabled(True)
    
    def display_news_detail(self, news: dict):
        """
        显示新闻详情（自动尝试抓取全文）
        
        Args:
            news: 新闻数据字典
        """
        # 保存当前新闻数据，用于链接点击
        self.current_news = news
        
        # 标题
        self.detail_title.setText(news.get("title", "无标题"))
        
        # 元信息
        meta_text = f"发布时间: {news.get('publish_time', '-')} | 来源: {news.get('source', '-')}"
        self.detail_meta.setText(meta_text)
        
        # 内容：先显示已有内容，然后异步抓取全文
        content = news.get("content", "暂无内容")
        url = news.get("url", "")
        
        # 判断内容是否可能被截断（短于200字且有URL）
        if len(content) < 200 and url:
            # 先显示摘要，然后后台加载原文网页
            placeholder_html = self._build_placeholder_html(content, url)
            self.detail_content.setHtml(placeholder_html)
            # 启动后台线程抓取全文
            self._fetch_full_content_worker = FullContentFetchWorker(self.scraper, url, content)
            self._fetch_full_content_worker.content_ready.connect(self._on_full_content_ready)
            self._fetch_full_content_worker.start()
        elif url:
            # 有URL，直接加载原文网页（完美显示图片和排版）
            self.detail_content.load(QUrl(url))
        else:
            # 无URL，显示纯文本
            plain_html = self._build_plain_html(content)
            self.detail_content.setHtml(plain_html)
        
        # 原文链接
        if url:
            display_url = url[:60] + "..." if len(url) > 60 else url
            self.detail_url.setText(display_url)
            self.detail_url.setToolTip(f"点击打开: {url}")
        else:
            self.detail_url.setText("无链接")
            self.detail_url.setToolTip("")
        
        # AI评估结果
        ai_score = news.get("ai_score")
        if ai_score is not None:
            self.ai_score_label.setText(f"{ai_score:+.1f}")
            if ai_score > 0:
                self.ai_score_label.setStyleSheet("color: #4CAF50;")
            elif ai_score < 0:
                self.ai_score_label.setStyleSheet("color: #F44336;")
            else:
                self.ai_score_label.setStyleSheet("color: #999999;")
        else:
            self.ai_score_label.setText("未分析")
            self.ai_score_label.setStyleSheet("color: #999;")
        
        self.ai_reason.setText(news.get("ai_analysis", "暂无AI分析结果"))
        self.ai_stocks.setText(news.get("related_stocks", "-"))
    
    def _on_full_content_ready(self, result: dict):
        """
        全文抓取完成回调 — 直接加载原文网页到QWebEngineView
        
        Args:
            result: {'content': 完整内容, 'success': 是否成功}
        """
        url = self.current_news.get('url', '') if self.current_news else ''
        if url:
            # 直接加载原文网页（完美显示图片和排版）
            self.detail_content.load(QUrl(url))
        else:
            # 无URL，显示抓取到的文本内容
            content = result.get('content') or result.get('original', '暂无内容')
            plain_html = self._build_plain_html(content)
            self.detail_content.setHtml(plain_html)
    
    def _on_url_clicked(self, event):
        """
        点击链接时打开浏览器
        
        Args:
            event: 鼠标事件
        """
        if self.current_news:
            url = self.current_news.get("url", "")
            if url:
                # 使用系统默认浏览器打开链接
                QDesktopServices.openUrl(QUrl(url))
    
    def _build_placeholder_html(self, content: str, url: str) -> str:
        """构建加载中的占位HTML"""
        import html as html_mod
        safe_content = html_mod.escape(content)
        return f'''
        <html><body style="font-family: Microsoft YaHei, sans-serif; padding:20px; color:#333;">
        <p style="font-size:14px; line-height:1.8;">{safe_content}</p>
        <p style="color:#888; margin-top:20px;">⏳ 正在加载完整内容...</p>
        </body></html>
        '''
    
    def _build_plain_html(self, content: str) -> str:
        """构建纯文本内容的HTML"""
        import html as html_mod
        safe_content = html_mod.escape(content)
        # 将换行转为段落
        paragraphs = safe_content.split('\n')
        paras_html = ''.join(f'<p style="font-size:14px; line-height:1.8; margin:6px 0;">{p}</p>' for p in paragraphs if p.strip())
        return f'''
        <html><body style="font-family: Microsoft YaHei, sans-serif; padding:12px; color:#333;">
        {paras_html}
        </body></html>
        '''
    
    def _on_webpage_loaded(self, ok: bool):
        """
        网页加载完成回调
        注入JavaScript提取正文内容，并应用暗黑科技风CSS样式
        
        Args:
            ok: 网页是否加载成功
        """
        if not ok:
            return
        
        # 注入净化脚本：提取正文 + 注入暗黑CSS
        cleanup_js = """
        (function() {
            // ============================================================
            // 1. 定义暗黑科技风CSS样式
            // ============================================================
            var darkCSS = `
                /* 全局重置 */
                * { margin: 0; padding: 0; box-sizing: border-box; }
                
                /* 页面背景与文字 */
                body {
                    background-color: #1a1a2e !important;
                    color: #e0e0e0 !important;
                    font-family: "Microsoft YaHei", "SimSun", "PingFang SC", sans-serif !important;
                    font-size: 16px !important;
                    line-height: 1.8 !important;
                    padding: 15px !important;
                    overflow-x: hidden !important;
                }
                
                /* 段落排版 */
                p {
                    margin: 10px 0 !important;
                    text-indent: 0 !important;
                    font-size: 16px !important;
                    line-height: 1.8 !important;
                    color: #e0e0e0 !important;
                }
                
                /* 标题：居中 + 紧凑间距 */
                h1, h2, h3, h4, h5, h6 {
                    color: #ffffff !important;
                    font-weight: bold !important;
                }
                h1 {
                    font-size: 22px !important;
                    text-align: center !important;
                    margin-top: 10px !important;
                    margin-bottom: 5px !important;
                }
                h2 {
                    font-size: 20px !important;
                    margin: 15px 0 8px 0 !important;
                }
                h3 {
                    font-size: 18px !important;
                    margin: 12px 0 6px 0 !important;
                }
                
                /* 图片：居中、自适应宽度 */
                img {
                    max-width: 100% !important;
                    height: auto !important;
                    display: block !important;
                    margin: 16px auto !important;
                    border-radius: 4px !important;
                }
                
                /* 链接 */
                a {
                    color: #64b5f6 !important;
                    text-decoration: none !important;
                }
                a:hover {
                    color: #90caf9 !important;
                    text-decoration: underline !important;
                }
                
                /* 表格 */
                table {
                    border-collapse: collapse !important;
                    width: 100% !important;
                    margin: 16px 0 !important;
                    font-size: 14px !important;
                }
                th, td {
                    border: 1px solid #333355 !important;
                    padding: 8px 12px !important;
                    color: #e0e0e0 !important;
                }
                th {
                    background-color: #252545 !important;
                    color: #ffffff !important;
                    font-weight: bold !important;
                }
                
                /* 列表 */
                ul, ol {
                    padding-left: 24px !important;
                    margin: 10px 0 !important;
                }
                li {
                    margin: 6px 0 !important;
                    color: #e0e0e0 !important;
                }
                
                /* 引用 */
                blockquote {
                    border-left: 3px solid #4a4a8a !important;
                    padding: 10px 16px !important;
                    margin: 16px 0 !important;
                    background-color: #252545 !important;
                    color: #c0c0c0 !important;
                    border-radius: 0 4px 4px 0 !important;
                }
                
                /* 正文容器：去除多余padding，释放空间 */
                .b-new-content, .txtinfos, .article-content,
                #Main_Content_Box, .cons-wrapper, #custom-page-content,
                .content, #ContentBody {
                    padding: 0 !important;
                    margin: 0 !important;
                }
                
                /* 来源信息：居中 + 紧凑 */
                .em_media, .source, .editor, .time, .pub-time,
                [class*="source"], [class*="time"], [class*="date"],
                [class*="Info"], [class*="author"] {
                    color: #888888 !important;
                    font-size: 13px !important;
                    text-align: center !important;
                    margin-top: 5px !important;
                    margin-bottom: 15px !important;
                    padding: 0 !important;
                    border-top: none !important;
                }
                
                /* 隐藏不需要的元素 */
                .ad, .advertisement, .sidebar, .nav, .header, .footer,
                .comment, .share, .related, .recommend, .breadcrumb,
                [class*="ad-"], [id*="ad-"], [class*="sidebar"],
                script, style, noscript, iframe {
                    display: none !important;
                }
                
                /* 滚动条美化 */
                ::-webkit-scrollbar { width: 8px; }
                ::-webkit-scrollbar-track { background: #1a1a2e; }
                ::-webkit-scrollbar-thumb { background: #4a4a8a; border-radius: 4px; }
                ::-webkit-scrollbar-thumb:hover { background: #6a6aaa; }
            `;
            
            // ============================================================
            // 2. 注入CSS样式
            // ============================================================
            var styleEl = document.createElement('style');
            styleEl.type = 'text/css';
            styleEl.textContent = darkCSS;
            document.head.appendChild(styleEl);
            
            // ============================================================
            // 3. 提取正文内容（支持多个主流财经网站）
            // ============================================================
            var contentSelectors = [
                '#ContentBody',           // 东方财富
                '.b-new-content',         // 东方财富（旧版）
                '.txtinfos',              // 东方财富（备用）
                '.article-content',       // 财新网/中证网
                '#Main_Content_Box',      // 财新网
                '.cons-wrapper',          // 财新网
                '#custom-page-content',   // 证券时报
                '.article',               // 通用
                'article',                // HTML5标准
                '.content',               // 通用
                '#ContentBody',           // 经济参考报
            ];
            
            var contentElement = null;
            for (var i = 0; i < contentSelectors.length; i++) {
                var el = document.querySelector(contentSelectors[i]);
                if (el && el.innerHTML.trim().length > 200) {
                    contentElement = el;
                    break;
                }
            }
            
            // ============================================================
            // 4. 如果找到正文，用它替换整个页面
            // ============================================================
            if (contentElement) {
                // 保留样式标签
                var styles = document.querySelectorAll('style');
                var styleHTML = '';
                for (var j = 0; j < styles.length; j++) {
                    styleHTML += styles[j].outerHTML;
                }
                
                // 用正文替换body
                document.body.innerHTML = contentElement.innerHTML;
                
                // 重新注入我们的暗黑CSS（确保优先级最高）
                var newStyle = document.createElement('style');
                newStyle.type = 'text/css';
                newStyle.textContent = darkCSS;
                document.head.appendChild(newStyle);
                
                // 滚动到顶部
                window.scrollTo(0, 0);
            }
            
            // ============================================================
            // 5. 如果没有找到正文，仅注入CSS（保持原网页，美化样式）
            // ============================================================
            
        })();
        """
        
        # 执行JS脚本
        self.detail_content.page().runJavaScript(cleanup_js)
    
    def analyze_selected_news(self):
        """对选中的新闻进行AI分析"""
        if not self.current_news:
            return
        
        self.analyze_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("正在进行AI分析...")
        
        # 获取新闻内容
        content = self.current_news.get("content", "")
        if not content:
            content = self.current_news.get("title", "")
        
        # 创建工作线程
        self.analyze_worker = AIAnalyzeWorker(self.analyzer, content)
        self.analyze_worker.analysis_completed.connect(self.on_analysis_completed)
        self.analyze_worker.error_occurred.connect(self.on_analysis_error)
        self.analyze_worker.progress_updated.connect(self.progress_bar.setValue)
        self.analyze_worker.finished.connect(self.on_analysis_finished)
        self.analyze_worker.start()
    
    def on_analysis_completed(self, result: dict):
        """
        AI分析完成回调
        
        Args:
            result: 分析结果字典
        """
        if self.current_news:
            news_id = self.current_news.get("id")
            
            # 更新数据库
            self.db.update_ai_analysis(
                news_id=news_id,
                score=result.get("score"),
                analysis=result.get("analysis"),
                stocks=result.get("stocks")
            )
            
            # 更新当前数据
            self.current_news["ai_score"] = result.get("score")
            self.current_news["ai_analysis"] = result.get("analysis")
            self.current_news["related_stocks"] = result.get("stocks")
            
            # 刷新显示
            self.display_news_detail(self.current_news)
            self.load_news_from_db()  # 刷新列表中的评分
            
            self.statusBar().showMessage("AI分析完成")
    
    def on_analysis_error(self, error_msg: str):
        """
        AI分析错误回调
        
        Args:
            error_msg: 错误信息
        """
        QMessageBox.critical(self, "分析失败", f"AI分析时发生错误：\n{error_msg}")
        self.statusBar().showMessage("分析失败")
    
    def on_analysis_finished(self):
        """AI分析线程结束回调"""
        self.analyze_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.analyze_worker = None
    
    def filter_news(self):
        """根据搜索关键词过滤新闻"""
        keyword = self.search_input.text().strip()
        if keyword:
            news_list = self.db.search_news(keyword)
        else:
            news_list = self.db.get_all_news()
        self.populate_news_table(news_list)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止大盘定时器
        self.market_timer.stop()
        
        # 停止所有工作线程
        if self.fetch_worker and self.fetch_worker.isRunning():
            self.fetch_worker.stop()
        if self.analyze_worker and self.analyze_worker.isRunning():
            self.analyze_worker.stop()
        if hasattr(self, 'refresh_worker') and self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.stop()
        if hasattr(self, '_index_worker') and self._index_worker and self._index_worker.isRunning():
            self._index_worker.stop()
        
        # 关闭数据库连接
        self.db.close()
        
        event.accept()
