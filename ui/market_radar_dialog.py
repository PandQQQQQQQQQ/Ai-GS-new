"""
大盘与搜股雷达对话框 (MarketRadarDialog)
提供：
1. 3秒高频大盘指数看板（上证/深证/创业板）
2. 实时个股搜索（支持代码/名称/拼音首字母）
3. 自选股观测区（3秒异步刷新）
4. 数据持久化：自选股和A股缓存保存到本地
"""

import re
import os
import json
from typing import List, Dict, Optional, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QScrollArea,
    QWidget, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPalette


# ============================================================
# 缓存文件路径
# ============================================================
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CACHE_FILE = os.path.join(CACHE_DIR, 'market_cache.json')


def _ensure_cache_dir():
    """确保缓存目录存在"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def _save_cache(all_stocks: list, watchlist: list, pinyin_cache: dict):
    """
    保存缓存数据到本地文件
    
    Args:
        all_stocks: 全量A股行情数据
        watchlist: 自选股列表
        pinyin_cache: 拼音索引缓存
    """
    try:
        _ensure_cache_dir()
        data = {
            'all_stocks': all_stocks,
            'watchlist': watchlist,
            'pinyin_cache': pinyin_cache,
        }
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Debug] 缓存已保存: {len(all_stocks)} 只A股, {len(watchlist)} 只自选股")
    except Exception as e:
        print(f"[Debug] 保存缓存失败: {e}")


def _load_cache() -> tuple:
    """
    从本地文件加载缓存数据
    
    Returns:
        (all_stocks, watchlist, pinyin_cache) 元组
    """
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            all_stocks = data.get('all_stocks', [])
            watchlist = data.get('watchlist', [])
            pinyin_cache = data.get('pinyin_cache', {})
            print(f"[Debug] 缓存已加载: {len(all_stocks)} 只A股, {len(watchlist)} 只自选股")
            return all_stocks, watchlist, pinyin_cache
    except Exception as e:
        print(f"[Debug] 加载缓存失败: {e}")
    return [], [], {}


# ============================================================
# 【全局】禁用代理函数
# ============================================================
def _disable_proxy_globally():
    """
    禁用代理：环境变量清理 + trust_env=False
    """
    import os
    proxy_keys = [
        'http_proxy', 'https_proxy', 'all_proxy',
        'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
    ]
    for key in proxy_keys:
        if key in os.environ:
            del os.environ[key]
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'
    try:
        import requests
        requests.Session.trust_env = False
    except Exception:
        pass


# ============================================================
# 【核心】通过新浪财经接口获取行情数据
# 东财 clist/get 接口在某些网络环境下不可用（Schannel SSL兼容问题）
# 新浪 hqs.sinajs.cn 接口稳定可用，支持批量查询
# ============================================================
def _sina_fetch_quotes(codes: list) -> list:
    """
    通过新浪财经接口批量获取股票实时行情
    
    Args:
        codes: 股票代码列表，如 ['sh000001', 'sz399001', 'sh600519']
    
    Returns:
        字典列表，每个字典包含 代码/名称/最新价/涨跌幅/成交额/最高/最低 等
    """
    import requests
    import warnings
    warnings.filterwarnings('ignore')
    
    # 新浪接口每次最多约50只，超过则分批
    batch_size = 50
    all_records = []
    
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        code_str = ','.join(batch)
        url = f'https://hq.sinajs.cn/list={code_str}'
        
        try:
            resp = requests.get(url, timeout=10, verify=False,
                                headers={'Referer': 'https://finance.sina.com.cn/'})
            
            if resp.status_code != 200:
                continue
            
            for line in resp.text.strip().split('\n'):
                if not line.strip() or '=' not in line:
                    continue
                
                try:
                    # 解析格式: var hq_str_sh600519="贵州茅台,今开,昨收,当前价,最高,最低,...";
                    data_str = line.split('"')[1]
                    if not data_str:
                        continue
                    
                    parts = data_str.split(',')
                    if len(parts) < 10:
                        continue
                    
                    # 提取代码（从变量名中）
                    code_full = line.split('=')[0].strip().replace('var hq_str_', '')
                    
                    name = parts[0]           # 名称
                    open_price = float(parts[1]) if parts[1] else 0   # 今开
                    prev_close = float(parts[2]) if parts[2] else 0  # 昨收
                    current = float(parts[3]) if parts[3] else 0     # 最新价
                    high = float(parts[4]) if parts[4] else 0       # 最高
                    low = float(parts[5]) if parts[5] else 0         # 最低
                    
                    # 计算涨跌幅
                    if prev_close > 0:
                        change_pct = (current - prev_close) / prev_close * 100
                    else:
                        change_pct = 0
                    
                    # 成交额（新浪字段9，单位可能是元）
                    volume = float(parts[8]) if len(parts) > 8 and parts[8] else 0
                    
                    # 提取纯数字代码（去掉 sh/sz 前缀）
                    pure_code = code_full[2:] if len(code_full) > 2 else code_full
                    
                    all_records.append({
                        '代码': pure_code,
                        '名称': name,
                        '最新价': current,
                        '涨跌幅': round(change_pct, 2),
                        '涨跌额': round(current - prev_close, 2) if prev_close > 0 else 0,
                        '今开': open_price,
                        '昨收': prev_close,
                        '最高': high,
                        '最低': low,
                        '成交额': volume,
                    })
                except (ValueError, IndexError):
                    continue
        
        except Exception as e:
            print(f"[Debug] 新浪批量请求异常: {e}")
    
    return all_records


def _fetch_index_data() -> list:
    """
    获取三大指数行情（上证/深证/创业板）
    通过新浪财经接口
    """
    codes = ['sh000001', 'sz399001', 'sz399006']
    return _sina_fetch_quotes(codes)


def _fetch_stock_data_via_sina() -> list:
    """
    通过新浪财经接口获取全量A股行情
    第一步：分页获取全部A股代码列表（每页100条）
    第二步：分批通过新浪行情接口获取实时数据
    """
    import requests
    import warnings
    warnings.filterwarnings('ignore')
    
    all_codes = []
    
    # ========== 第一步：分页获取全部A股代码 ==========
    try:
        base_url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
        page = 1
        max_pages = 60  # 最多60页（6000只），防止无限循环
        
        while page <= max_pages:
            url = f'{base_url}?page={page}&num=100&sort=code&asc=1&node=hs_a&symbol=&_s_r_a=page'
            resp = requests.get(url, timeout=10, verify=False,
                                headers={'Referer': 'https://finance.sina.com.cn/'})
            
            if resp.status_code != 200 or not resp.text.strip():
                break
            
            import json
            data = json.loads(resp.text)
            
            if not data:
                break
            
            for item in data:
                code = item.get('code', '')
                if code:
                    prefix = 'sh' if code.startswith('6') else 'sz'
                    all_codes.append(f'{prefix}{code}')
            
            # 如果本页不足100条，说明已经是最后一页
            if len(data) < 100:
                break
            
            page += 1
        
        print(f"[Debug] 从新浪分页获取到 {len(all_codes)} 只A股代码 ({page}页)")
        
    except Exception as e:
        print(f"[Debug] 新浪列表接口失败: {e}")
    
    if not all_codes:
        return []
    
    # ========== 第二步：分批通过新浪行情接口获取实时数据 ==========
    print(f"[Debug] 开始分批获取 {len(all_codes)} 只股票行情...")
    all_records = _sina_fetch_quotes(all_codes)
    print(f"[Debug] 新浪接口获取到 {len(all_records)} 条行情数据")
    
    return all_records


def _sina_search_stock(query: str) -> list:
    """
    通过新浪搜索接口实时搜索股票
    支持代码、名称、拼音首字母
    
    Args:
        query: 搜索关键词
    
    Returns:
        匹配的股票列表，每项包含 代码/名称/市场前缀
    """
    import requests
    import warnings
    warnings.filterwarnings('ignore')
    
    try:
        url = f'https://suggest3.sinajs.cn/suggest/type=11,12&key={query}'
        resp = requests.get(url, timeout=5, verify=False,
                            headers={'Referer': 'https://finance.sina.com.cn/'})
        
        if resp.status_code != 200 or not resp.text.strip():
            return []
        
        # 解析格式: var suggestvalue="sh600519,11,600519,sh600519,贵州茅台,,...";
        data_str = resp.text.split('"')[1]
        if not data_str:
            return []
        
        results = []
        items = data_str.split(';')
        for item in items:
            if not item.strip():
                continue
            parts = item.split(',')
            if len(parts) >= 5:
                code_full = parts[0]   # sh600519
                market_type = parts[1]  # 11=沪A, 12=深A
                code = parts[2]        # 600519
                name = parts[4]        # 贵州茅台
                results.append({
                    'code_full': code_full,
                    'code': code,
                    'name': name,
                    'market': market_type,
                })
        
        return results
        
    except Exception as e:
        print(f"[Debug] 新浪搜索异常: {e}")
        return []


# ============================================================
# 工作线程：异步获取全量A股行情（通过curl绕过代理）
# ============================================================
class StockSpotWorker(QThread):
    """
    异步获取全量A股实时行情数据
    通过新浪财经接口获取（东财 clist/get 不可用时）
    """
    data_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._is_running = True

    def run(self):
        _disable_proxy_globally()
        
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            if not self._is_running:
                return
            try:
                import time
                import random
                time.sleep(random.uniform(0.2, 0.5))
                
                print(f"[Debug] StockSpotWorker: 新浪接口请求全量A股 (第{attempt}次)...")
                records = _fetch_stock_data_via_sina()
                
                print(f"[Debug] StockSpotWorker: 获取到 {len(records)} 条数据")
                if self._is_running:
                    self.data_ready.emit(records)
                return
                
            except Exception as e:
                print(f"[Debug] StockSpotWorker 第{attempt}次异常: {type(e).__name__}: {e}")
                if attempt < max_retries and self._is_running:
                    import time
                    time.sleep(3)
                else:
                    if self._is_running:
                        self.error_occurred.emit(str(e))

    def stop(self):
        self._is_running = False
        self.wait()


# ============================================================
# 工作线程：异步获取大盘指数行情（通过curl绕过代理）
# ============================================================
class IndexSpotWorker(QThread):
    """
    异步获取大盘指数实时行情
    通过新浪财经接口获取
    """
    index_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._is_running = True

    def run(self):
        _disable_proxy_globally()
        
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            if not self._is_running:
                return
            try:
                import time
                import random
                time.sleep(random.uniform(0.1, 0.3))
                
                print(f"[Debug] IndexSpotWorker: 新浪接口请求指数数据 (第{attempt}次)...")
                records = _fetch_index_data()
                
                print(f"[Debug] IndexSpotWorker: 获取到 {len(records)} 条指数数据")
                if self._is_running:
                    self.index_ready.emit(records)
                return
                
            except Exception as e:
                print(f"[Debug] IndexSpotWorker 第{attempt}次异常: {type(e).__name__}: {e}")
                if attempt < max_retries and self._is_running:
                    import time
                    time.sleep(3)
                else:
                    if self._is_running:
                        self.error_occurred.emit(str(e))

    def stop(self):
        self._is_running = False
        self.wait()


# ============================================================
# 工具函数：生成中文名称的拼音首字母简拼
# ============================================================
def make_pinyin_initials(chinese_name: str) -> str:
    """
    使用 pypinyin 将中文名转换为纯小写拼音首字母简拼
    例如："贵州茅台" → "gzmt", "宁德时代" → "ndsd"
    如果 pypinyin 未安装，返回空字符串
    """
    try:
        from pypinyin import pinyin, Style
        # 取每个汉字的首字母，全小写拼接
        initials = pinyin(chinese_name, style=Style.FIRST_LETTER)
        return ''.join(item[0] for item in initials).lower()
    except ImportError:
        return ''


# ============================================================
# 大盘指数卡片控件：单个指数看板
# ============================================================
class IndexCard(QFrame):
    """
    大盘指数卡片
    显示指数名称、最新值、涨跌幅
    自动变色：红涨绿跌
    """

    # 三个核心指数的代码映射
    INDEX_MAP = {
        "上证指数": "000001",
        "深证成指": "399001",
        "创业板指": "399006",
    }

    def __init__(self, index_name: str, parent=None):
        super().__init__(parent)
        self.index_name = index_name
        self._init_ui()

    def _init_ui(self):
        # 卡片基础样式（暗黑科技风）
        self.setStyleSheet("""
            IndexCard {
                background-color: #1e1e2f;
                border-radius: 8px;
                border: 2px solid #2a2a40;
                padding: 12px;
            }
        """)
        self.setMinimumSize(200, 130)
        self.setMaximumHeight(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # 指数名称
        self.name_label = QLabel(self.index_name)
        name_font = QFont()
        name_font.setPointSize(13)
        name_font.setBold(True)
        self.name_label.setFont(name_font)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(self.name_label)

        # 最新指数值（大号数字）
        self.value_label = QLabel("--")
        val_font = QFont()
        val_font.setPointSize(24)
        val_font.setBold(True)
        self.value_label.setFont(val_font)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(self.value_label)

        # 涨跌幅
        self.change_label = QLabel("--")
        chg_font = QFont()
        chg_font.setPointSize(14)
        chg_font.setBold(True)
        self.change_label.setFont(chg_font)
        self.change_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.change_label)

    def update_data(self, price: float, change_pct: float):
        """
        更新卡片数据，自动变色
        
        Args:
            price: 最新指数值
            change_pct: 涨跌幅（百分比，如 1.23 表示 +1.23%）
        """
        # 格式化数值
        if self.index_name == "上证指数":
            value_text = f"{price:.2f}"
        else:
            value_text = f"{price:.2f}"

        self.value_label.setText(value_text)

        # 根据涨跌幅决定颜色
        if change_pct > 0:
            # 上涨 → 红色
            color = "#FF4444"
            border_color = "#FF4444"
            change_text = f"+{change_pct:.2f}%"
        elif change_pct < 0:
            # 下跌 → 绿色
            color = "#00C853"
            border_color = "#00C853"
            change_text = f"{change_pct:.2f}%"
        else:
            # 持平 → 灰色
            color = "#888888"
            border_color = "#555555"
            change_text = "0.00%"

        self.value_label.setStyleSheet(f"color: {color};")
        self.change_label.setText(change_text)
        self.change_label.setStyleSheet(f"color: {color};")

        # 卡片边框同步变色
        self.setStyleSheet(f"""
            IndexCard {{
                background-color: #1e1e2f;
                border-radius: 8px;
                border: 2px solid {border_color};
                padding: 12px;
            }}
        """)


# ============================================================
# 个股观测卡片：自选股列表中的单个条目
# ============================================================
class StockCard(QFrame):
    """
    个股监测卡片
    显示：股票名称、代码、最新价、涨跌幅、成交额、最高/最低价
    """

    def __init__(self, stock_code: str, stock_name: str, parent=None):
        super().__init__(parent)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            StockCard {
                background-color: #1e1e2f;
                border-radius: 6px;
                border: 1px solid #2a2a40;
                padding: 8px;
            }
            StockCard:hover {
                border: 1px solid #4a4a8a;
            }
        """)
        self.setMinimumSize(180, 120)
        self.setMaximumSize(220, 140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        # 第一行：名称 + 代码
        header_layout = QHBoxLayout()
        self.name_label = QLabel(self.stock_name)
        nf = QFont()
        nf.setPointSize(11)
        nf.setBold(True)
        self.name_label.setFont(nf)
        self.name_label.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(self.name_label)

        self.code_label = QLabel(self.stock_code)
        cf = QFont()
        cf.setPointSize(9)
        self.code_label.setFont(cf)
        self.code_label.setStyleSheet("color: #888888;")
        header_layout.addWidget(self.code_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 第二行：最新价 + 涨跌幅
        price_layout = QHBoxLayout()
        self.price_label = QLabel("--")
        pf = QFont()
        pf.setPointSize(16)
        pf.setBold(True)
        self.price_label.setFont(pf)
        self.price_label.setStyleSheet("color: #e0e0e0;")
        price_layout.addWidget(self.price_label)

        self.change_label = QLabel("--")
        price_layout.addWidget(self.change_label)
        price_layout.addStretch()
        layout.addLayout(price_layout)

        # 第三行：成交额 / 最高 / 最低
        detail_label = QLabel("--")
        df = QFont()
        df.setPointSize(9)
        detail_label.setFont(df)
        detail_label.setStyleSheet("color: #777777;")
        self.detail_label = detail_label
        layout.addWidget(detail_label)

    def update_data(self, price: float, change_pct: float,
                    volume: float = 0, high: float = 0, low: float = 0):
        """
        更新卡片行情数据
        
        Args:
            price: 最新价
            change_pct: 涨跌幅
            volume: 成交额（元）
            high: 最高价
            low: 最低价
        """
        self.price_label.setText(f"{price:.2f}")

        # 涨跌幅颜色
        if change_pct > 0:
            color = "#FF4444"
            prefix = "+"
        elif change_pct < 0:
            color = "#00C853"
            prefix = ""
        else:
            color = "#888888"
            prefix = ""

        self.change_label.setText(f"{prefix}{change_pct:.2f}%")
        self.change_label.setStyleSheet(f"color: {color}; font-size: 13px;")

        # 成交额格式化（元 → 亿）
        vol_str = f"{volume / 1e8:.2f}亿" if volume > 0 else "--"
        detail = f"成交额: {vol_str}    最高: {high:.2f}    最低: {low:.2f}"
        self.detail_label.setText(detail)


# ============================================================
# 大盘行情与搜股对话框 (MarketRadarDialog)
# ============================================================
class MarketRadarDialog(QDialog):
    """
    市场雷达对话框
    - 3秒高频刷新三大指数
    - 实时搜索个股（支持代码/名称/拼音）
    - 自选股监测区
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📡 市场雷达 · 大盘与搜股")
        self.setMinimumSize(900, 700)
        self.resize(1000, 750)

        # ---------- 数据缓存 ----------
        self.all_stocks: List[Dict] = []          # 全量A股行情快照
        self.pinyin_cache: Dict[str, str] = {}    # 股票名称 → 拼音首字母简拼
        self.watchlist: List[Dict] = []            # 自选股列表 [{code, name}]

        # 工作线程引用
        self.stock_worker: Optional[StockSpotWorker] = None
        self.index_worker: Optional[IndexSpotWorker] = None

        # 是否首次加载（用于初始化拼音索引）
        self._first_load = True

        # ---------- 构建UI ----------
        self._init_ui()

        # ---------- 加载本地缓存 ----------
        cached_stocks, cached_watchlist, cached_pinyin = _load_cache()
        if cached_stocks:
            self.all_stocks = cached_stocks
            self._first_load = False  # 已有缓存，不再是首次加载
            print(f"[Debug] 已加载本地A股缓存: {len(self.all_stocks)} 条")
        if cached_watchlist:
            self.watchlist = cached_watchlist
            # 重建自选股UI
            self._rebuild_watchlist_ui()
            print(f"[Debug] 已加载本地自选股: {len(self.watchlist)} 只")
        if cached_pinyin:
            self.pinyin_cache = cached_pinyin
            print(f"[Debug] 已加载拼音索引: {len(self.pinyin_cache)} 条")

        # ---------- 启动定时刷新 ----------
        # 指数刷新：5秒一次
        self.index_timer = QTimer(self)
        self.index_timer.timeout.connect(self._trigger_index_fetch)
        
        # 全量A股刷新：15秒一次（重量请求）
        self.stock_timer = QTimer(self)
        self.stock_timer.timeout.connect(self._trigger_stock_fetch)
        
        # 立即首次刷新
        self._trigger_index_fetch()
        self._trigger_stock_fetch()
        
        # 启动定时器
        self.index_timer.start(5000)   # 指数每5秒
        self.stock_timer.start(15000)  # 全量每15秒

        # 应用全局暗黑主题
        self._apply_dark_theme()

    # ----------------------------------------------------------
    # UI 构建
    # ----------------------------------------------------------
    def _apply_dark_theme(self):
        """为对话框应用暗黑科技风皮肤"""
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLineEdit {
                background-color: #1e1e2f;
                color: #e0e0e0;
                border: 1px solid #3a3a5a;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #5a5a8a;
            }
            QPushButton {
                background-color: #2a2a4a;
                color: #e0e0e0;
                border: 1px solid #3a3a5a;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a3a6a;
                border: 1px solid #5a5a8a;
            }
            QPushButton:pressed {
                background-color: #1a1a3a;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #1a1a2e;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #4a4a8a;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def _init_ui(self):
        """构建对话框主布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ---------- 顶部标题 ----------
        title_label = QLabel("📡 市场雷达")
        tf = QFont()
        tf.setPointSize(18)
        tf.setBold(True)
        title_label.setFont(tf)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #ffffff; margin-bottom: 6px;")
        main_layout.addWidget(title_label)

        # ---------- 1. 三大指数看板 ----------
        indices_layout = QHBoxLayout()
        indices_layout.setSpacing(12)

        self.index_sh = IndexCard("上证指数")
        self.index_sz = IndexCard("深证成指")
        self.index_cy = IndexCard("创业板指")

        indices_layout.addWidget(self.index_sh)
        indices_layout.addWidget(self.index_sz)
        indices_layout.addWidget(self.index_cy)
        main_layout.addLayout(indices_layout)

        # ---------- 2. 搜索栏 ----------
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "输入股票代码 / 名称 / 拼音首字母 (如：600519 / 茅台 / gzmt) ..."
        )
        self.search_input.setMinimumHeight(36)
        self.search_input.returnPressed.connect(self._on_search)  # 回车触发
        search_layout.addWidget(self.search_input, stretch=1)

        self.search_btn = QPushButton("🔍 监测个股")
        self.search_btn.setMinimumHeight(36)
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF6B35;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #E85D2C;
            }
        """)
        self.search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_btn)

        main_layout.addLayout(search_layout)

        # ---------- 3. 搜索结果提示区 ----------
        self.search_result_label = QLabel("")
        self.search_result_label.setStyleSheet("color: #888888; font-size: 12px;")
        main_layout.addWidget(self.search_result_label)

        # ---------- 4. 自选股观测区 ----------
        watch_label = QLabel("📊 自选股观测区 (每3秒自动刷新)")
        wf = QFont()
        wf.setPointSize(13)
        wf.setBold(True)
        watch_label.setFont(wf)
        watch_label.setStyleSheet("color: #bbbbbb; margin-top: 4px;")
        main_layout.addWidget(watch_label)

        # 滚动区域，放置个股卡片
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(200)

        self.watchlist_container = QWidget()
        self.watchlist_layout = QHBoxLayout(self.watchlist_container)
        self.watchlist_layout.setContentsMargins(4, 4, 4, 4)
        self.watchlist_layout.setSpacing(10)
        self.watchlist_layout.addStretch()  # 默认右对齐

        self.scroll_area.setWidget(self.watchlist_container)
        main_layout.addWidget(self.scroll_area, stretch=1)

    # ----------------------------------------------------------
    # 数据获取触发（由定时器调用）
    # ----------------------------------------------------------
    def _trigger_index_fetch(self):
        """触发大盘指数数据获取（每10秒）"""
        print(f"[Debug] _trigger_index_fetch: 触发指数刷新...")
        if not self.index_worker or not self.index_worker.isRunning():
            print(f"[Debug] _trigger_index_fetch: 启动 IndexSpotWorker")
            self.index_worker = IndexSpotWorker()
            self.index_worker.index_ready.connect(self._on_index_data)
            self.index_worker.error_occurred.connect(self._on_fetch_error)
            self.index_worker.finished.connect(self._cleanup_index_worker)
            self.index_worker.start()
        else:
            print(f"[Debug] _trigger_index_fetch: IndexSpotWorker 仍在运行，跳过")

    def _trigger_stock_fetch(self):
        """触发全量A股数据获取（每30秒）"""
        print(f"[Debug] _trigger_stock_fetch: 触发全量A股刷新...")
        if not self.stock_worker or not self.stock_worker.isRunning():
            print(f"[Debug] _trigger_stock_fetch: 启动 StockSpotWorker")
            self.stock_worker = StockSpotWorker()
            self.stock_worker.data_ready.connect(self._on_stock_data)
            self.stock_worker.error_occurred.connect(self._on_fetch_error)
            self.stock_worker.finished.connect(self._cleanup_stock_worker)
            self.stock_worker.start()
        else:
            print(f"[Debug] _trigger_stock_fetch: StockSpotWorker 仍在运行，跳过")

    # ----------------------------------------------------------
    # 大盘指数数据回调
    # ----------------------------------------------------------
    def _on_index_data(self, records: List[Dict]):
        """
        大盘指数数据到达回调
        从全量指数中筛选出三大核心指数
        """
        print(f"[Debug] _on_index_data: 接收到 {len(records)} 条指数数据")
        
        # 要监控的指数代码列表
        target_codes = ["000001", "399001", "399006"]
        # 映射到对应的卡片对象
        card_map = {
            "000001": self.index_sh,   # 上证指数
            "399001": self.index_sz,   # 深证成指
            "399006": self.index_cy,   # 创业板指
        }

        found_count = 0
        for rec in records:
            code = str(rec.get("代码", ""))
            if code in target_codes and code in card_map:
                try:
                    price = float(rec.get("最新价", 0))
                    change_pct = float(rec.get("涨跌幅", 0))
                    print(f"[Debug] _on_index_data: 更新 {code} - 价格={price}, 涨跌幅={change_pct}%")
                    card_map[code].update_data(price, change_pct)
                    found_count += 1
                except (ValueError, TypeError) as e:
                    print(f"[Debug] _on_index_data: 解析 {code} 数据失败: {e}")
        
        print(f"[Debug] _on_index_data: 成功更新 {found_count}/3 个指数")

    # ----------------------------------------------------------
    # 全量A股数据回调（用于拼音索引构建 + 自选股刷新）
    # ----------------------------------------------------------
    def _on_stock_data(self, records: List[Dict]):
        """
        全量A股行情数据到达回调
        1. 首次加载时构建拼音首字母索引缓存
        2. 更新已监测的自选股卡片数据
        """
        print(f"[Debug] _on_stock_data: 接收到 {len(records)} 条数据")
        
        # 只有当新数据不为空时才更新缓存（防止接口限流返回空数据覆盖已有缓存）
        if records and len(records) > 0:
            self.all_stocks = records
            print(f"[Debug] _on_stock_data: all_stocks 已更新，长度={len(self.all_stocks)}")
        else:
            print(f"[Debug] _on_stock_data: 数据为空，保留已有缓存 (长度={len(self.all_stocks)})")

        # 首次加载且有数据：构建拼音索引
        if self._first_load and records and len(records) > 0:
            print(f"[Debug] _on_stock_data: 首次加载，构建拼音索引...")
            self._build_pinyin_index(records)
            self._first_load = False
            print(f"[Debug] _on_stock_data: 拼音索引构建完成，共 {len(self.pinyin_cache)} 条")

        # 更新自选股卡片（使用当前缓存的数据）
        if self.all_stocks:
            self._refresh_watchlist_cards(self.all_stocks)

    def _build_pinyin_index(self, records: List[Dict]):
        """
        遍历全量A股数据，为每个股票的中文名称生成拼音首字母简拼缓存
        
        例如：records 中包含 "贵州茅台" → self.pinyin_cache["贵州茅台"] = "gzmt"
        """
        self.pinyin_cache.clear()
        for rec in records:
            name = str(rec.get("名称", ""))
            if name and name != "nan":
                pinyin_str = make_pinyin_initials(name)
                if pinyin_str:
                    self.pinyin_cache[name] = pinyin_str

    # ----------------------------------------------------------
    # 搜索匹配逻辑（支持代码/名称/拼音首字母）
    # ----------------------------------------------------------
    def _on_search(self):
        """
        搜索按钮 / 回车触发
        从全量数据中匹配输入内容，匹配成功则加入自选股
        """
        query = self.search_input.text().strip()
        if not query:
            return

        print(f"[Debug] _on_search: 用户输入='{query}'")

        # 检查数据是否已加载（None / 空列表 双重防护）
        if not self.all_stocks or len(self.all_stocks) == 0:
            # 显示正在重连
            self.search_result_label.setText(
                "🔄 正在重新连接服务器，请稍候..."
            )
            self.search_result_label.setStyleSheet("color: #FFA726; font-size: 13px;")
            print(f"[Debug] _on_search: 数据未就绪，触发重新抓取")
            
            # 静默触发一次全量数据抓取
            self._trigger_stock_fetch()
            return
        
        # 重置提示区样式为正常
        self.search_result_label.setStyleSheet("color: #888888; font-size: 12px;")
        print(f"[Debug] _on_search: all_stocks 长度={len(self.all_stocks)}, _first_load={self._first_load}")

        # 将查询转为小写（拼音匹配不区分大小写）
        query_lower = query.lower()

        matched_stocks = []
        for rec in self.all_stocks:
            # 统一格式化股票代码：转字符串，去除小数点，补齐6位
            raw_code = rec.get("代码", "")
            code = str(raw_code).split('.')[0].strip()  # 处理 "600519.0" 或 "600519" 的情况
            if code.isdigit():
                code = code.zfill(6)  # 补齐6位，如 "1" -> "000001"
            
            name = str(rec.get("名称", "")).strip()

            # 空值跳过
            if not code or not name or name == "nan" or name == "None":
                continue

            # --- 多模式匹配 ---
            # 1) 股票代码匹配（精确前缀匹配，支持输入 600 匹配所有 600xxx）
            if code.startswith(query):
                print(f"[Debug] _on_search: 代码匹配成功 - {code} {name}")
                matched_stocks.append(rec)
                continue

            # 2) 中文名称包含匹配
            if query in name:
                print(f"[Debug] _on_search: 名称匹配成功 - {code} {name}")
                matched_stocks.append(rec)
                continue

            # 3) 拼音首字母匹配（绝对匹配或前缀包含）
            pinyin_str = self.pinyin_cache.get(name, "")
            if pinyin_str:
                if pinyin_str == query_lower or pinyin_str.startswith(query_lower):
                    print(f"[Debug] _on_search: 拼音匹配成功 - {code} {name} ({pinyin_str})")
                    matched_stocks.append(rec)
                    continue

        print(f"[Debug] _on_search: 共匹配到 {len(matched_stocks)} 只股票")

        if not matched_stocks:
            # 本地缓存未找到 → 尝试新浪搜索接口实时查询
            print(f"[Debug] _on_search: 本地未找到，尝试新浪搜索接口...")
            sina_results = _sina_search_stock(query)
            
            if sina_results:
                print(f"[Debug] _on_search: 新浪搜索返回 {len(sina_results)} 条结果")
                # 用新浪行情接口获取匹配股票的实时数据
                sina_codes = [r['code_full'] for r in sina_results]
                sina_quotes = _sina_fetch_quotes(sina_codes)
                
                if sina_quotes:
                    matched_stocks = sina_quotes
                    print(f"[Debug] _on_search: 新浪行情获取到 {len(sina_quotes)} 条数据")
                else:
                    # 行情获取失败，用搜索结果的基本信息创建卡片
                    for r in sina_results:
                        matched_stocks.append({
                            '代码': r['code'],
                            '名称': r['name'],
                            '最新价': 0,
                            '涨跌幅': 0,
                            '涨跌额': 0,
                            '今开': 0,
                            '昨收': 0,
                            '最高': 0,
                            '最低': 0,
                            '成交额': 0,
                        })
            
            if not matched_stocks:
                self.search_result_label.setText(
                    f"⚠️ 未找到匹配 '{query}' 的股票，请更换关键词"
                )
                return

        # 将匹配到的股票加入自选股
        added_count = 0
        for rec in matched_stocks:
            code = str(rec.get("代码", ""))
            name = str(rec.get("名称", ""))
            # 去重
            if not any(w["code"] == code for w in self.watchlist):
                self.watchlist.append({"code": code, "name": name})
                added_count += 1

        # 刷新自选股显示
        self._rebuild_watchlist_ui()

        msg = f"✅ 找到 {len(matched_stocks)} 只，已添加 {added_count} 只到自选股"
        if added_count < len(matched_stocks):
            msg += f"（{len(matched_stocks) - added_count} 只已在列表中）"
        self.search_result_label.setText(msg)

        # 清空搜索框
        self.search_input.clear()

    # ----------------------------------------------------------
    # 自选股UI管理
    # ----------------------------------------------------------
    def _rebuild_watchlist_ui(self):
        """根据 watchlist 重建自选股卡片UI"""
        # 清除现有卡片（保留末尾 stretch）
        while self.watchlist_layout.count() > 1:
            item = self.watchlist_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 为每个自选股创建卡片（插入到 stretch 之前）
        for stock in self.watchlist:
            card = StockCard(stock["code"], stock["name"])
            # 添加删除按钮：双击移除
            card.mouseDoubleClickEvent = lambda e, c=stock: self._remove_from_watchlist(c)
            self.watchlist_layout.insertWidget(
                self.watchlist_layout.count() - 1, card
            )

    def _refresh_watchlist_cards(self, records: List[Dict]):
        """
        用最新行情数据刷新自选股卡片

        Args:
            records: 全量A股行情数据
        """
        # 建立代码→数据的快速索引（统一格式化代码）
        data_map = {}
        for rec in records:
            raw_code = rec.get("代码", "")
            code = str(raw_code).split('.')[0].strip()
            if code.isdigit():
                code = code.zfill(6)
            data_map[code] = rec

        # 遍历滚动区中的所有卡片，更新数据
        updated_count = 0
        for i in range(self.watchlist_layout.count()):
            item = self.watchlist_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if isinstance(card, StockCard):
                    # 统一格式化卡片中的代码
                    card_code = str(card.stock_code).split('.')[0].strip()
                    if card_code.isdigit():
                        card_code = card_code.zfill(6)
                    
                    rec = data_map.get(card_code)
                    if rec:
                        try:
                            price = float(rec.get("最新价", 0))
                            change_pct = float(rec.get("涨跌幅", 0))
                            volume = float(rec.get("成交额", 0))
                            high = float(rec.get("最高", 0))
                            low = float(rec.get("最低", 0))
                            card.update_data(price, change_pct, volume, high, low)
                            updated_count += 1
                        except (ValueError, TypeError) as e:
                            print(f"[Debug] _refresh_watchlist_cards: 更新 {card_code} 失败: {e}")
        
        if updated_count > 0:
            print(f"[Debug] _refresh_watchlist_cards: 成功更新 {updated_count} 只自选股")

    def _remove_from_watchlist(self, stock: Dict):
        """
        从自选股中移除指定股票

        Args:
            stock: {"code": "...", "name": "..."}
        """
        self.watchlist = [
            w for w in self.watchlist if w["code"] != stock["code"]
        ]
        self._rebuild_watchlist_ui()
        self.search_result_label.setText(
            f"🗑️ 已移除 {stock['name']} ({stock['code']})"
        )

    # ----------------------------------------------------------
    # 错误处理与资源清理
    # ----------------------------------------------------------
    def _on_fetch_error(self, error_msg: str):
        """数据获取错误 — 在看板上显示具体错误原因"""
        print(f"[Debug] _on_fetch_error: {error_msg}")
        
        # 判断是否为代理相关错误
        error_lower = error_msg.lower()
        if 'proxy' in error_lower:
            hint = "⚠️ 网络直连受阻，请检查梯子是否干扰了本地连接"
        elif 'timeout' in error_lower:
            hint = "⚠️ 请求超时，网络可能不稳定"
        elif 'connection' in error_lower:
            hint = "⚠️ 网络连接失败，请检查网络"
        else:
            hint = f"⚠️ 数据获取异常: {error_msg[:80]}"
        
        # 更新搜索结果提示区显示错误
        self.search_result_label.setText(hint)
        self.search_result_label.setStyleSheet("color: #FF4444; font-size: 13px;")

    def _cleanup_index_worker(self):
        self.index_worker = None

    def _cleanup_stock_worker(self):
        self.stock_worker = None

    def closeEvent(self, event):
        """
        对话框关闭时保存数据并清理定时器和线程
        """
        # 保存缓存数据到本地文件
        if self.all_stocks or self.watchlist:
            _save_cache(self.all_stocks, self.watchlist, self.pinyin_cache)
            print(f"[Debug] closeEvent: 已保存缓存数据 (A股={len(self.all_stocks)}, 自选股={len(self.watchlist)})")

        # 停止定时器
        self.index_timer.stop()
        self.stock_timer.stop()

        # 停止并清理工作线程
        if self.index_worker and self.index_worker.isRunning():
            self.index_worker.stop()
        if self.stock_worker and self.stock_worker.isRunning():
            self.stock_worker.stop()

        event.accept()
