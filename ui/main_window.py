"""
主窗口模块
使用 PySide6 构建现代化的主界面
布局：左侧新闻列表，右侧详情和AI评估结果
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QLabel, QPushButton, QGroupBox, QProgressBar,
    QMessageBox, QAbstractItemView, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal, QDateTime, QUrl
from PySide6.QtGui import QFont, QColor, QBrush, QDesktopServices

from db.database import Database
from scraper.news_scraper import NewsScraper
from ai.analyzer import AIAnalyzer


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
            news_list = self.scraper.fetch_latest_news(limit=50)
            
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
        
        # 初始化UI
        self.init_ui()
        
        # 加载已有新闻
        self.load_news_from_db()
    
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
        
        # 获取新闻按钮
        self.fetch_btn = QPushButton("📥 获取最新新闻")
        self.fetch_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        self.fetch_btn.clicked.connect(self.fetch_news)
        button_layout.addWidget(self.fetch_btn)
        
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
        detail_layout.addWidget(self.detail_title)
        
        # 元信息标签
        self.detail_meta = QLabel("")
        meta_font = QFont()
        meta_font.setPointSize(10)
        self.detail_meta.setFont(meta_font)
        self.detail_meta.setStyleSheet("color: #666;")
        detail_layout.addWidget(self.detail_meta)
        
        # 内容文本框
        self.detail_content = QTextEdit()
        self.detail_content.setReadOnly(True)
        self.detail_content.setPlaceholderText("新闻内容将显示在这里...")
        detail_layout.addWidget(self.detail_content)
        
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
        
        layout.addWidget(detail_group, stretch=1)
        
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
        self.fetch_btn.setEnabled(False)
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
        self.fetch_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.fetch_worker = None
    
    def load_news_from_db(self):
        """从数据库加载新闻到列表"""
        news_list = self.db.get_all_news()
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
        显示新闻详情
        
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
        
        # 内容
        self.detail_content.setText(news.get("content", "暂无内容"))
        
        # 原文链接
        url = news.get("url", "")
        if url:
            # 显示短链接文本，但保存完整URL
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
            # 设置颜色
            if ai_score > 0:
                self.ai_score_label.setStyleSheet("color: #4CAF50;")  # 绿色
            elif ai_score < 0:
                self.ai_score_label.setStyleSheet("color: #F44336;")  # 红色
            else:
                self.ai_score_label.setStyleSheet("color: #999999;")  # 灰色
        else:
            self.ai_score_label.setText("未分析")
            self.ai_score_label.setStyleSheet("color: #999;")
        
        self.ai_reason.setText(news.get("ai_analysis", "暂无AI分析结果"))
        self.ai_stocks.setText(news.get("related_stocks", "-"))
    
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
        # 停止所有工作线程
        if self.fetch_worker and self.fetch_worker.isRunning():
            self.fetch_worker.stop()
        if self.analyze_worker and self.analyze_worker.isRunning():
            self.analyze_worker.stop()
        if hasattr(self, 'refresh_worker') and self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.stop()
        
        # 关闭数据库连接
        self.db.close()
        
        event.accept()
