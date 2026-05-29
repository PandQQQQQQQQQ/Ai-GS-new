"""
新闻采集模块
使用 AkShare 库并发获取多个数据源的A股相关财经新闻
支持的数据源：
  1. 东方财富新闻 (stock_news_em) - 主力数据源，支持关键词搜索
  2. 财新网新闻 (stock_news_main_cx) - 补充数据源
  3. 上期所快讯 (futures_news_shmet) - 实时快讯
  4. 央视新闻 (news_cctv) - 权威宏观新闻
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed


class NewsScraper:
    """
    新闻采集器类
    负责从多个数据源并发获取A股相关财经新闻
    """

    def __init__(self):
        """初始化新闻采集器"""
        self.akshare_available = self._check_akshare()

    def _check_akshare(self) -> bool:
        """检查 AkShare 库是否可用"""
        try:
            import akshare as ak
            return True
        except ImportError:
            print("警告: AkShare 库未安装，将使用模拟数据")
            return False

    # ============================================================
    # 核心接口：并发抓取所有数据源
    # ============================================================

    def fetch_all_sources(self, limit_per_source: int = 50) -> List[Dict[str, Any]]:
        """
        并发抓取所有数据源的新闻，合并去重后返回

        Args:
            limit_per_source: 每个数据源最多获取的新闻条数

        Returns:
            List[Dict]: 标准化新闻列表
                {'title': 标题, 'content': 正文, 'source': 来源, 'publish_time': 时间, 'url': 链接}
        """
        if not self.akshare_available:
            return self._get_mock_news()

        # 定义所有数据源抓取任务
        tasks = {
            "东方财富": self._fetch_eastmoney,
            "财新网": self._fetch_caixin,
            "上期所快讯": self._fetch_shmet,
            "央视新闻": self._fetch_cctv,
        }

        all_news = []

        # 使用线程池并发抓取
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_name = {
                executor.submit(func, limit_per_source): name
                for name, func in tasks.items()
            }

            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    news_list = future.result(timeout=30)
                    all_news.extend(news_list)
                    print(f"[采集完成] {name}: {len(news_list)} 条")
                except Exception as e:
                    print(f"[采集失败] {name}: {e}")

        # 按标题去重（保留先出现的）
        seen_titles = set()
        unique_news = []
        for news in all_news:
            title = news.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)

        print(f"[汇总] 共采集 {len(all_news)} 条，去重后 {len(unique_news)} 条")
        return unique_news

    def fetch_latest_news(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        兼容旧接口：获取最新新闻

        Args:
            limit: 返回的最大新闻条数

        Returns:
            List[Dict]: 新闻数据列表
        """
        news = self.fetch_all_sources(limit_per_source=limit)
        return news[:limit]

    # ============================================================
    # 数据源1：东方财富新闻（主力数据源）
    # ============================================================

    def _fetch_eastmoney(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取东方财富新闻
        使用多个关键词搜索，扩大覆盖面

        Args:
            limit: 每个关键词最多获取的新闻条数

        Returns:
            List[Dict]: 标准化新闻列表
        """
        news_list = []
        keywords = ["全部", "A股", "上市公司", "科创板", "创业板"]

        per_keyword = max(10, limit // len(keywords))

        try:
            import akshare as ak

            for keyword in keywords:
                try:
                    df = ak.stock_news_em(symbol=keyword)
                    if df is not None and not df.empty:
                        for _, row in df.head(per_keyword).iterrows():
                            news = self._parse_eastmoney_row(row)
                            if news:
                                news_list.append(news)
                except Exception as e:
                    print(f"东方财富({keyword})获取失败: {e}")

        except Exception as e:
            print(f"东方财富获取失败: {e}")

        return news_list

    def _parse_eastmoney_row(self, row: Any) -> Optional[Dict[str, Any]]:
        """解析东方财富新闻行"""
        try:
            row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)

            title = str(row_dict.get('新闻标题', ''))
            if not title or title == 'nan':
                return None

            content = str(row_dict.get('新闻内容', ''))
            if not content or content == 'nan':
                content = title

            publish_time = str(row_dict.get('发布时间', ''))
            publish_time = self._format_datetime(publish_time)

            url = str(row_dict.get('新闻链接', ''))
            source = str(row_dict.get('文章来源', ''))
            if not source or source == 'nan':
                source = "东方财富"

            return {
                "title": title.strip(),
                "content": content.strip(),
                "source": source.strip(),
                "publish_time": publish_time,
                "url": url.strip() if url != 'nan' else ""
            }
        except Exception as e:
            print(f"解析东方财富新闻失败: {e}")
        return None

    # ============================================================
    # 数据源2：财新网新闻
    # ============================================================

    def _fetch_caixin(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取财新网新闻"""
        news_list = []
        try:
            import akshare as ak
            df = ak.stock_news_main_cx()
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    news = self._parse_caixin_row(row)
                    if news:
                        news_list.append(news)
        except Exception as e:
            print(f"财新网获取失败: {e}")
        return news_list

    def _parse_caixin_row(self, row: Any) -> Optional[Dict[str, Any]]:
        """解析财新网新闻行"""
        try:
            row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)

            tag = str(row_dict.get('tag', ''))
            if not tag or tag == 'nan':
                return None

            summary = str(row_dict.get('summary', ''))
            url = str(row_dict.get('url', ''))

            title = tag
            content = summary if summary and summary != 'nan' else tag

            # 从URL提取日期，并尝试从页面获取具体时间
            publish_time = self._extract_date_from_url(url)

            return {
                "title": title.strip(),
                "content": content.strip(),
                "source": "财新网",
                "publish_time": publish_time,
                "url": url.strip() if url != 'nan' else ""
            }
        except Exception as e:
            print(f"解析财新网新闻失败: {e}")
        return None

    # ============================================================
    # 数据源3：上期所快讯（实时短讯）
    # ============================================================

    def _fetch_shmet(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取上期所/有色金属快讯"""
        news_list = []
        try:
            import akshare as ak
            df = ak.futures_news_shmet()
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    news = self._parse_shmet_row(row)
                    if news:
                        news_list.append(news)
        except Exception as e:
            print(f"上期所快讯获取失败: {e}")
        return news_list

    def _parse_shmet_row(self, row: Any) -> Optional[Dict[str, Any]]:
        """解析上期所快讯行"""
        try:
            row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)

            content = str(row_dict.get('内容', ''))
            if not content or content == 'nan' or len(content) < 10:
                return None

            # 从内容提取标题（取前50字）
            title = content[:50] + "..." if len(content) > 50 else content

            # 提取发布时间
            raw_time = str(row_dict.get('发布时间', ''))
            publish_time = self._format_datetime(raw_time)

            return {
                "title": title.strip(),
                "content": content.strip(),
                "source": "上期所快讯",
                "publish_time": publish_time,
                "url": ""
            }
        except Exception as e:
            print(f"解析上期所快讯失败: {e}")
        return None

    # ============================================================
    # 数据源4：央视新闻（权威宏观）
    # ============================================================

    def _fetch_cctv(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取央视新闻"""
        news_list = []
        try:
            import akshare as ak
            df = ak.news_cctv()
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    news = self._parse_cctv_row(row)
                    if news:
                        news_list.append(news)
        except Exception as e:
            print(f"央视新闻获取失败: {e}")
        return news_list

    def _parse_cctv_row(self, row: Any) -> Optional[Dict[str, Any]]:
        """解析央视新闻行"""
        try:
            row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)

            title = str(row_dict.get('title', ''))
            if not title or title == 'nan':
                return None

            content = str(row_dict.get('content', ''))
            if not content or content == 'nan':
                content = title

            # 央视新闻日期格式：20240424
            raw_date = str(row_dict.get('date', ''))
            publish_time = self._format_datetime(raw_date)

            return {
                "title": title.strip(),
                "content": content.strip(),
                "source": "央视新闻",
                "publish_time": publish_time,
                "url": ""
            }
        except Exception as e:
            print(f"解析央视新闻失败: {e}")
        return None

    # ============================================================
    # 工具方法
    # ============================================================

    def _format_datetime(self, time_str: str) -> str:
        """
        格式化日期时间字符串，支持多种格式

        Args:
            time_str: 原始时间字符串

        Returns:
            str: 格式化后的时间字符串 (YYYY-MM-DD HH:MM:SS)
        """
        if not time_str or time_str == 'nan':
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 去掉时区信息（如 +08:00）
        time_str = re.sub(r'[+-]\d{2}:\d{2}$', '', time_str).strip()

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y%m%d",
            "%m-%d %H:%M",
            "%H:%M:%S",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _extract_date_from_url(self, url: str) -> str:
        """
        从URL中提取日期，并尝试从网页获取具体时间

        Args:
            url: 新闻链接

        Returns:
            str: 格式化的日期时间字符串
        """
        if not url or url == 'nan':
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 从URL中匹配日期
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', url)
        if date_match:
            date_str = date_match.group(1)
            # 尝试从网页获取具体时间
            specific_time = self._fetch_publish_time_from_page(url)
            if specific_time:
                return specific_time
            return f"{date_str} 00:00:00"

        date_match = re.search(r'(\d{4})(\d{2})(\d{2})', url)
        if date_match:
            year, month, day = date_match.groups()
            return f"{year}-{month}-{day} 00:00:00"

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _fetch_publish_time_from_page(self, url: str) -> Optional[str]:
        """
        从新闻页面提取发布时间（针对财新网等无时间字段的接口）

        Args:
            url: 新闻链接

        Returns:
            str: 格式化的日期时间字符串，失败返回None
        """
        try:
            import requests

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=8)
            response.encoding = 'utf-8'

            text = response.text

            # 财新网页面时间格式：2026年05月29日 19:13 或 2026-05-29 19:13
            patterns = [
                r'(\d{4}年\d{2}月\d{2}日\s*\d{2}:\d{2})',
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',
            ]

            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    time_str = match.group(1)
                    if '年' in time_str:
                        time_str = time_str.replace('年', '-').replace('月', '-').replace('日', '')
                    try:
                        dt = datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M")
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass

        except Exception:
            pass

        return None

    # ============================================================
    # 模拟数据（AkShare不可用时使用）
    # ============================================================

    def _get_mock_news(self) -> List[Dict[str, Any]]:
        """获取模拟新闻数据"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        mock_news = [
            {"title": "宁德时代发布新一代电池技术，能量密度提升30%", "content": "宁德时代今日发布全新一代动力电池技术，能量密度较上一代产品提升30%，续航里程突破1000公里。", "source": "证券时报", "publish_time": current_time, "url": ""},
            {"title": "贵州茅台：上半年净利润同比增长15.8%", "content": "贵州茅台发布半年度报告，实现营业收入819.31亿元，同比增长17.76%。", "source": "上海证券报", "publish_time": current_time, "url": ""},
            {"title": "比亚迪7月销量再创新高，同比增长超60%", "content": "比亚迪公布7月销量数据，当月新能源汽车销量达34.24万辆，同比增长超过60%。", "source": "中国证券报", "publish_time": current_time, "url": ""},
            {"title": "中芯国际：二季度营收环比增长8.6%", "content": "中芯国际发布二季度财报，营收环比增长8.6%，超出市场预期。", "source": "财新网", "publish_time": current_time, "url": ""},
            {"title": "腾讯控股：回购股份金额达100亿港元", "content": "腾讯控股公告，公司近期累计回购股份金额达100亿港元。", "source": "港交所公告", "publish_time": current_time, "url": ""},
            {"title": "隆基绿能：受行业周期影响，预计三季度业绩承压", "content": "隆基绿能发布业绩预告，受光伏行业周期性调整影响，预计三季度净利润同比下降。", "source": "证券时报", "publish_time": current_time, "url": ""},
            {"title": "招商银行：零售业务持续稳健增长", "content": "招商银行发布经营数据，零售业务AUM突破13万亿元。", "source": "上海证券报", "publish_time": current_time, "url": ""},
            {"title": "药明康德：新增多项CDMO订单", "content": "药明康德公告，公司近期新增多项CDMO服务订单，订单金额创季度新高。", "source": "中国证券报", "publish_time": current_time, "url": ""},
            {"title": "美的集团：智能家居业务增速超20%", "content": "美的集团披露，上半年智能家居业务营收同比增长超20%。", "source": "财新网", "publish_time": current_time, "url": ""},
            {"title": "恒瑞医药：创新药收入占比突破50%", "content": "恒瑞医药发布半年报，创新药销售收入占比首次突破50%。", "source": "证券时报", "publish_time": current_time, "url": ""},
        ]

        return mock_news


# 便捷函数
def fetch_latest_news(limit: int = 50) -> List[Dict[str, Any]]:
    """便捷函数：获取最新新闻"""
    scraper = NewsScraper()
    return scraper.fetch_latest_news(limit)
