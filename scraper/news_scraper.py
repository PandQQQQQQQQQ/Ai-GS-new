"""
新闻采集模块
使用 AkShare 库获取A股相关财经新闻
预留接口支持其他数据源扩展
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import re


class NewsScraper:
    """
    新闻采集器类
    负责从多个数据源获取A股相关财经新闻
    """
    
    def __init__(self):
        """初始化新闻采集器"""
        self.akshare_available = self._check_akshare()
    
    def _check_akshare(self) -> bool:
        """
        检查 AkShare 库是否可用
        
        Returns:
            bool: AkShare 可用返回True
        """
        try:
            import akshare as ak
            return True
        except ImportError:
            print("警告: AkShare 库未安装，将使用模拟数据")
            return False
    
    def fetch_latest_news(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取最新财经新闻
        
        Args:
            limit: 获取的新闻数量限制
            
        Returns:
            List[Dict]: 新闻数据列表，每条新闻包含：
                - title: 标题
                - content: 内容摘要
                - source: 来源
                - publish_time: 发布时间
                - url: 原文链接
        """
        news_list = []
        
        # 尝试从多个数据源获取新闻
        if self.akshare_available:
            # 使用 AkShare 获取新闻
            news_list.extend(self._fetch_from_akshare(limit))
        
        # 如果AkShare没有获取到数据，使用模拟数据（用于演示）
        if not news_list:
            news_list = self._get_mock_news()
        
        return news_list[:limit]
    
    def _fetch_from_akshare(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        使用 AkShare 获取财经新闻
        
        Args:
            limit: 获取的新闻数量
            
        Returns:
            List[Dict]: 新闻数据列表
        """
        news_list = []
        
        try:
            import akshare as ak
            
            # 计算每个数据源获取的数量（各取一半）
            per_source = limit // 2
            
            # 获取财新网新闻（stock_news_main_cx 接口）
            try:
                df = ak.stock_news_main_cx()
                if df is not None and not df.empty:
                    for _, row in df.head(per_source).iterrows():
                        news = self._parse_cls_news_row(row)
                        if news:
                            news_list.append(news)
            except Exception as e:
                print(f"获取财新网新闻失败: {e}")
            
            # 获取东方财富财经新闻
            try:
                df = ak.stock_news_em()
                if df is not None and not df.empty:
                    remaining = limit - len(news_list)
                    for _, row in df.head(remaining).iterrows():
                        news = self._parse_akshare_news_row(row)
                        if news:
                            news_list.append(news)
            except Exception as e:
                print(f"获取东方财富新闻失败: {e}")
                    
        except Exception as e:
            print(f"AkShare 获取新闻失败: {e}")
        
        return news_list
    
    def _parse_cls_news_row(self, row: Any) -> Optional[Dict[str, Any]]:
        """
        解析财新网新闻数据行（stock_news_main_cx 接口实际返回财新数据）
        
        Args:
            row: DataFrame 行数据（pandas Series）
            
        Returns:
            Dict: 标准化的新闻数据字典
        """
        try:
            # 将行转为字典
            if hasattr(row, 'to_dict'):
                row_dict = row.to_dict()
            elif isinstance(row, dict):
                row_dict = row
            else:
                row_dict = dict(row)
            
            # 字段：tag（标签/标题）, summary（摘要）, url（链接）
            tag = str(row_dict.get('tag', ''))
            summary = str(row_dict.get('summary', ''))
            url = str(row_dict.get('url', ''))
            
            if not tag or tag == 'nan':
                return None
            
            # 标题使用tag，内容使用summary
            title = tag
            content = summary if summary and summary != 'nan' else tag
            
            # 从URL中提取发布日期（格式：https://database.caixin.com/2026-05-29/...）
            publish_time = self._extract_date_from_url(url)
            
            return {
                "title": title.strip(),
                "content": content.strip(),
                "source": "财新网",  # 实际数据来源是财新网
                "publish_time": publish_time,
                "url": url.strip() if url != 'nan' else ""
            }
        except Exception as e:
            print(f"解析财新网新闻行失败: {e}")
        
        return None
    
    def _extract_date_from_url(self, url: str) -> str:
        """
        从URL中提取日期，并尝试从网页获取具体时间
        
        Args:
            url: 新闻链接
            
        Returns:
            str: 格式化的日期时间字符串
        """
        import re
        
        if not url or url == 'nan':
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 尝试从URL中匹配日期格式 YYYY-MM-DD
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', url)
        if date_match:
            date_str = date_match.group(1)
            # 尝试从网页获取具体时间
            specific_time = self._fetch_publish_time_from_page(url)
            if specific_time:
                return specific_time
            # 返回日期加上默认时间
            return f"{date_str} 00:00:00"
        
        # 尝试匹配其他日期格式 YYYYMMDD
        date_match = re.search(r'(\d{4})(\d{2})(\d{2})', url)
        if date_match:
            year, month, day = date_match.groups()
            return f"{year}-{month}-{day} 00:00:00"
        
        # 无法提取则使用当前时间
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _fetch_publish_time_from_page(self, url: str) -> Optional[str]:
        """
        从新闻页面提取发布时间
        
        Args:
            url: 新闻链接
            
        Returns:
            str: 格式化的日期时间字符串，提取失败返回None
        """
        try:
            import requests
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
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
                    # 解析时间
                    if '年' in time_str:
                        # 格式：2026年05月29日 19:13
                        time_str = time_str.replace('年', '-').replace('月', '-').replace('日', '')
                    # 转换为标准格式
                    try:
                        dt = datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M")
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass
            
        except Exception as e:
            print(f"从页面提取时间失败: {e}")
        
        return None
    
    def _parse_akshare_news_row(
        self, 
        row: Any, 
        source: str = "东方财富"
    ) -> Optional[Dict[str, Any]]:
        """
        解析 AkShare 返回的新闻数据行
        
        Args:
            row: DataFrame 行数据（pandas Series）
            source: 新闻来源
            
        Returns:
            Dict: 标准化的新闻数据字典
        """
        try:
            # 将行转为字典，统一用字典方式访问字段
            # 兼容 pandas Series 和普通 dict
            if hasattr(row, 'to_dict'):
                row_dict = row.to_dict()
            elif hasattr(row, '_asdict'):
                row_dict = row._asdict()
            elif isinstance(row, dict):
                row_dict = row
            else:
                row_dict = dict(row)
            
            # 字段名映射：按优先级排列（兼容东方财富、财联社等不同数据源）
            title = ""
            for col in ['新闻标题', 'title', 'Title', '标题', 'tag', 'summary']:
                if col in row_dict:
                    title = str(row_dict[col])
                    break
            
            content = ""
            for col in ['新闻内容', 'content', '内容', '摘要', 'summary', 'Content', 'tag']:
                if col in row_dict:
                    content = str(row_dict[col])
                    break
            
            if not content:
                content = title
            
            publish_time = ""
            for col in ['发布时间', 'datetime', '时间', 'Time', 'pub_time', 'date']:
                if col in row_dict:
                    publish_time = str(row_dict[col])
                    break
            
            url = ""
            for col in ['新闻链接', 'url', '链接', 'URL', 'link']:
                if col in row_dict:
                    url = str(row_dict[col])
                    break
            
            news_source = source
            for col in ['文章来源', 'source', '来源', 'Source']:
                if col in row_dict:
                    news_source = str(row_dict[col])
                    break
            
            # 格式化时间
            publish_time = self._format_datetime(publish_time)
            
            # 财联社数据源：tag作为标题，summary作为内容
            if 'tag' in row_dict and 'summary' in row_dict:
                title = str(row_dict['tag'])
                content = str(row_dict['summary'])
            
            if title and title != "nan":  # 标题不能为空
                return {
                    "title": title.strip(),
                    "content": content.strip() if content not in ("nan", title) else title.strip(),
                    "source": news_source.strip() if news_source not in ("nan", "") else source,
                    "publish_time": publish_time,
                    "url": url.strip() if url != "nan" else ""
                }
        except Exception as e:
            print(f"解析新闻行失败: {e}")
        
        return None
    
    def _format_datetime(self, time_str: str) -> str:
        """
        格式化日期时间字符串
        
        Args:
            time_str: 原始时间字符串
            
        Returns:
            str: 格式化后的时间字符串 (YYYY-MM-DD HH:MM:SS)
        """
        if not time_str or time_str == "nan":
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 尝试多种时间格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%m-%d %H:%M",
            "%H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str.strip(), fmt)
                # 如果年份缺失，使用当前年份
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        
        # 如果都无法解析，返回当前时间
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def fetch_news_by_stock(
        self, 
        stock_code: str, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取特定股票的相关新闻
        
        Args:
            stock_code: 股票代码（如：000001）
            limit: 获取的新闻数量
            
        Returns:
            List[Dict]: 新闻数据列表
        """
        news_list = []
        
        if self.akshare_available:
            try:
                import akshare as ak
                
                # 获取个股新闻
                df = ak.stock_news_em(symbol=stock_code)
                if df is not None and not df.empty:
                    for _, row in df.head(limit).iterrows():
                        news = self._parse_akshare_news_row(row)
                        if news:
                            news_list.append(news)
                            
            except Exception as e:
                print(f"获取股票 {stock_code} 新闻失败: {e}")
        
        return news_list
    
    def fetch_major_news(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        获取重大财经新闻/公告
        
        Args:
            limit: 获取的新闻数量
            
        Returns:
            List[Dict]: 新闻数据列表
        """
        news_list = []
        
        if self.akshare_available:
            try:
                import akshare as ak
                
                # 获取上市公司公告
                df = ak.stock_notice_report()
                if df is not None and not df.empty:
                    for _, row in df.head(limit).iterrows():
                        news = self._parse_notice_row(row)
                        if news:
                            news_list.append(news)
                            
            except Exception as e:
                print(f"获取重大新闻失败: {e}")
        
        return news_list
    
    def _parse_notice_row(self, row: Any) -> Optional[Dict[str, Any]]:
        """
        解析公告数据行
        
        Args:
            row: DataFrame 行数据
            
        Returns:
            Dict: 标准化的新闻数据
        """
        try:
            title = ""
            for col in ['title', '公告标题', 'Title']:
                if hasattr(row, 'get') and col in row:
                    title = str(row[col])
                    break
            
            content = ""
            for col in ['content', '内容', 'Content']:
                if hasattr(row, 'get') and col in row:
                    content = str(row[col])
                    break
            
            publish_time = ""
            for col in ['datetime', '公告时间', '时间', 'Time']:
                if hasattr(row, 'get') and col in row:
                    publish_time = str(row[col])
                    break
            
            code = ""
            for col in ['code', '股票代码', 'Code']:
                if hasattr(row, 'get') and col in row:
                    code = str(row[col])
                    break
            
            name = ""
            for col in ['name', '股票名称', 'Name']:
                if hasattr(row, 'get') and col in row:
                    name = str(row[col])
                    break
            
            if title:
                return {
                    "title": f"[{code} {name}] {title}" if code and name else title,
                    "content": content or title,
                    "source": "上市公司公告",
                    "publish_time": self._format_datetime(publish_time),
                    "url": ""
                }
        except Exception as e:
            print(f"解析公告行失败: {e}")
        
        return None
    
    def _get_mock_news(self) -> List[Dict[str, Any]]:
        """
        获取模拟新闻数据（用于演示和测试）
        
        Returns:
            List[Dict]: 模拟新闻数据列表
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        mock_news = [
            {
                "title": "宁德时代发布新一代电池技术，能量密度提升30%",
                "content": "宁德时代今日发布全新一代动力电池技术，能量密度较上一代产品提升30%，续航里程突破1000公里。该技术预计将于明年量产，已获得多家主流车企订单。",
                "source": "证券时报",
                "publish_time": current_time,
                "url": "https://example.com/news/1"
            },
            {
                "title": "贵州茅台：上半年净利润同比增长15.8%",
                "content": "贵州茅台发布2024年半年度报告，公司上半年实现营业收入819.31亿元，同比增长17.76%；净利润416.96亿元，同比增长15.88%。",
                "source": "上海证券报",
                "publish_time": current_time,
                "url": "https://example.com/news/2"
            },
            {
                "title": "比亚迪7月销量再创新高，同比增长超60%",
                "content": "比亚迪公布7月销量数据，当月新能源汽车销量达34.24万辆，同比增长超过60%，连续第五个月销量突破30万辆。",
                "source": "中国证券报",
                "publish_time": current_time,
                "url": "https://example.com/news/3"
            },
            {
                "title": "中芯国际：二季度营收环比增长8.6%",
                "content": "中芯国际发布二季度财报，营收环比增长8.6%，超出市场预期。公司表示，受益于AI芯片需求增长，先进制程产能利用率持续提升。",
                "source": "财新网",
                "publish_time": current_time,
                "url": "https://example.com/news/4"
            },
            {
                "title": "腾讯控股：回购股份金额达100亿港元",
                "content": "腾讯控股公告，公司近期累计回购股份金额达100亿港元，彰显管理层对公司长期发展的信心。",
                "source": "港交所公告",
                "publish_time": current_time,
                "url": "https://example.com/news/5"
            },
            {
                "title": "隆基绿能：受行业周期影响，预计三季度业绩承压",
                "content": "隆基绿能发布业绩预告，受光伏行业周期性调整影响，预计三季度净利润同比下降。公司表示将加快新技术产业化进程。",
                "source": "证券时报",
                "publish_time": current_time,
                "url": "https://example.com/news/6"
            },
            {
                "title": "招商银行：零售业务持续稳健增长",
                "content": "招商银行发布经营数据，零售业务AUM突破13万亿元，财富管理手续费收入保持行业领先。",
                "source": "上海证券报",
                "publish_time": current_time,
                "url": "https://example.com/news/7"
            },
            {
                "title": "药明康德：新增多项CDMO订单",
                "content": "药明康德公告，公司近期新增多项CDMO服务订单，涵盖小分子、多肽等多个领域，订单金额创季度新高。",
                "source": "中国证券报",
                "publish_time": current_time,
                "url": "https://example.com/news/8"
            },
            {
                "title": "美的集团：智能家居业务增速超20%",
                "content": "美的集团披露，上半年智能家居业务营收同比增长超20%，COLMO高端品牌增速领先，海外市场拓展顺利。",
                "source": "财新网",
                "publish_time": current_time,
                "url": "https://example.com/news/9"
            },
            {
                "title": "恒瑞医药：创新药收入占比突破50%",
                "content": "恒瑞医药发布半年报，创新药销售收入占比首次突破50%，标志着公司转型创新药企取得重要进展。",
                "source": "证券时报",
                "publish_time": current_time,
                "url": "https://example.com/news/10"
            }
        ]
        
        return mock_news


# 便捷函数，用于直接获取新闻
def fetch_latest_news(limit: int = 50) -> List[Dict[str, Any]]:
    """
    便捷函数：获取最新新闻
    
    Args:
        limit: 获取的新闻数量
        
    Returns:
        List[Dict]: 新闻数据列表
    """
    scraper = NewsScraper()
    return scraper.fetch_latest_news(limit)
