"""
数据库模块
SQLite数据库操作逻辑，包含新闻表的创建、查重、查询等功能
"""

import sqlite3
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path


class Database:
    """
    SQLite数据库管理类
    负责新闻数据的持久化存储和查询
    """
    
    def __init__(self, db_path: str = "data/news.db"):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，默认为 data/news.db
        """
        # 确保数据目录存在
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 建立数据库连接
        self.conn = sqlite3.connect(str(self.db_path))
        # 设置行工厂，使查询结果可以通过列名访问
        self.conn.row_factory = sqlite3.Row
        
        # 创建表结构
        self._create_tables()
    
    def _create_tables(self):
        """
        创建数据库表结构
        包含新闻表，存储新闻的基本信息和AI分析结果
        """
        cursor = self.conn.cursor()
        
        # 创建新闻表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                -- 新闻唯一标识，用于查重（基于标题和内容的哈希）
                news_hash TEXT UNIQUE NOT NULL,
                -- 新闻标题
                title TEXT NOT NULL,
                -- 新闻内容（摘要或全文）
                content TEXT,
                -- 新闻来源（如：新浪财经、东方财富等）
                source TEXT,
                -- 发布时间
                publish_time DATETIME,
                -- 原始链接
                url TEXT,
                -- AI评分（-5到+5，负值为利空，正值为利好）
                ai_score REAL,
                -- AI分析详细说明
                ai_analysis TEXT,
                -- 涉及的相关股票代码，逗号分隔
                related_stocks TEXT,
                -- 数据创建时间
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                -- 数据更新时间
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引以加速查询
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_hash ON news(news_hash)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_publish_time ON news(publish_time DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_score ON news(ai_score)
        """)
        
        self.conn.commit()
    
    def _generate_hash(self, title: str, content: str = "") -> str:
        """
        生成新闻的唯一哈希值，用于查重
        
        Args:
            title: 新闻标题
            content: 新闻内容
            
        Returns:
            str: MD5哈希值
        """
        # 使用标题+内容生成哈希，确保相同新闻不会被重复插入
        text = f"{title.strip()}|{content.strip()}"
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def is_news_exists(self, title: str, content: str = "") -> bool:
        """
        检查新闻是否已存在（基于哈希查重）
        
        Args:
            title: 新闻标题
            content: 新闻内容
            
        Returns:
            bool: 如果新闻已存在返回True，否则返回False
        """
        news_hash = self._generate_hash(title, content)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM news WHERE news_hash = ? LIMIT 1",
            (news_hash,)
        )
        return cursor.fetchone() is not None
    
    def insert_news(self, news_data: Dict[str, Any]) -> bool:
        """
        插入单条新闻数据
        如果新闻已存在（基于哈希查重），则跳过插入
        
        Args:
            news_data: 新闻数据字典，包含以下字段：
                - title: 标题（必填）
                - content: 内容
                - source: 来源
                - publish_time: 发布时间
                - url: 原始链接
                
        Returns:
            bool: 插入成功返回True，已存在或失败返回False
        """
        title = news_data.get("title", "").strip()
        if not title:
            return False
        
        content = news_data.get("content", "").strip()
        
        # 查重检查
        if self.is_news_exists(title, content):
            return False
        
        news_hash = self._generate_hash(title, content)
        
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO news (
                    news_hash, title, content, source, 
                    publish_time, url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                news_hash,
                title,
                content,
                news_data.get("source", ""),
                news_data.get("publish_time"),
                news_data.get("url", ""),
                datetime.now(),
                datetime.now()
            ))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # 唯一约束冲突（哈希重复）
            return False
        except Exception as e:
            print(f"插入新闻失败: {e}")
            return False
    
    def insert_news_batch(self, news_list: List[Dict[str, Any]]) -> int:
        """
        批量插入新闻数据
        
        Args:
            news_list: 新闻数据字典列表
            
        Returns:
            int: 成功插入的新闻数量
        """
        inserted_count = 0
        for news in news_list:
            if self.insert_news(news):
                inserted_count += 1
        return inserted_count
    
    def save_news(self, news_list: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        保存新闻列表到数据库（按标题严格去重）
        不同来源的同一条新闻（标题相同）只保留一条
        
        Args:
            news_list: 新闻数据字典列表，每个字典应包含：
                - title: 标题
                - content: 内容
                - source: 来源
                - publish_time: 发布时间
                - url: 链接（可选）
                
        Returns:
            Dict[str, int]: 包含统计信息的字典
                - total: 总新闻数
                - inserted: 成功插入数
                - duplicated: 重复跳过数
        """
        stats = {"total": len(news_list), "inserted": 0, "duplicated": 0}
        
        for news in news_list:
            title = news.get("title", "").strip()
            if not title:
                stats["duplicated"] += 1
                continue
            
            # 仅根据标题生成唯一标识（跨来源去重）
            news_hash = hashlib.md5(title.encode('utf-8')).hexdigest()
            
            # 检查是否已存在（按标题查重）
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM news WHERE news_hash = ? LIMIT 1",
                (news_hash,)
            )
            if cursor.fetchone() is not None:
                stats["duplicated"] += 1
                continue
            
            # 插入新数据
            try:
                cursor.execute("""
                    INSERT INTO news (
                        news_hash, title, content, source, 
                        publish_time, url, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    news_hash,
                    title,
                    news.get("content", ""),
                    news.get("source", ""),
                    news.get("publish_time", ""),
                    news.get("url", ""),
                    datetime.now(),
                    datetime.now()
                ))
                self.conn.commit()
                stats["inserted"] += 1
            except Exception as e:
                print(f"保存新闻失败: {e}")
                stats["duplicated"] += 1
        
        return stats
    
    def get_all_news(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        获取所有新闻，按发布时间倒序排列
        
        Args:
            limit: 返回的最大记录数，默认1000条
            
        Returns:
            List[Dict]: 新闻数据列表
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                id, title, content, source, publish_time, url,
                ai_score, ai_analysis, related_stocks, created_at
            FROM news
            ORDER BY publish_time DESC, created_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_news_by_id(self, news_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取单条新闻
        
        Args:
            news_id: 新闻ID
            
        Returns:
            Dict: 新闻数据字典，不存在则返回None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                id, title, content, source, publish_time, url,
                ai_score, ai_analysis, related_stocks, created_at
            FROM news
            WHERE id = ?
        """, (news_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def search_news(self, keyword: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        根据关键词搜索新闻（标题或内容）
        
        Args:
            keyword: 搜索关键词
            limit: 返回的最大记录数
            
        Returns:
            List[Dict]: 匹配的新闻列表
        """
        cursor = self.conn.cursor()
        search_pattern = f"%{keyword}%"
        cursor.execute("""
            SELECT 
                id, title, content, source, publish_time, url,
                ai_score, ai_analysis, related_stocks, created_at
            FROM news
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY publish_time DESC
            LIMIT ?
        """, (search_pattern, search_pattern, limit))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def update_ai_analysis(
        self, 
        news_id: int, 
        score: float, 
        analysis: str, 
        stocks: str = ""
    ) -> bool:
        """
        更新新闻的AI分析结果
        
        Args:
            news_id: 新闻ID
            score: AI评分（-5到+5）
            analysis: AI分析说明
            stocks: 涉及的相关股票代码
            
        Returns:
            bool: 更新成功返回True
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                UPDATE news
                SET ai_score = ?,
                    ai_analysis = ?,
                    related_stocks = ?,
                    updated_at = ?
                WHERE id = ?
            """, (score, analysis, stocks, datetime.now(), news_id))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"更新AI分析结果失败: {e}")
            return False
    
    def get_news_by_score_range(
        self, 
        min_score: float, 
        max_score: float, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        根据AI评分范围获取新闻
        
        Args:
            min_score: 最低评分
            max_score: 最高评分
            limit: 返回的最大记录数
            
        Returns:
            List[Dict]: 匹配的新闻列表
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                id, title, content, source, publish_time, url,
                ai_score, ai_analysis, related_stocks, created_at
            FROM news
            WHERE ai_score >= ? AND ai_score <= ?
            ORDER BY ai_score DESC, publish_time DESC
            LIMIT ?
        """, (min_score, max_score, limit))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_unanalyzed_news(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取未进行AI分析的新闻
        
        Args:
            limit: 返回的最大记录数
            
        Returns:
            List[Dict]: 未分析的新闻列表
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                id, title, content, source, publish_time, url,
                ai_score, ai_analysis, related_stocks, created_at
            FROM news
            WHERE ai_score IS NULL
            ORDER BY publish_time DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def delete_old_news(self, days: int = 30) -> int:
        """
        删除指定天数之前的新闻数据
        
        Args:
            days: 保留最近多少天的数据
            
        Returns:
            int: 删除的记录数
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM news
            WHERE created_at < datetime('now', '-{} days')
        """.format(days))
        self.conn.commit()
        return cursor.rowcount
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            Dict: 包含新闻总数、已分析数等统计信息
        """
        cursor = self.conn.cursor()
        
        # 总新闻数
        cursor.execute("SELECT COUNT(*) FROM news")
        total_count = cursor.fetchone()[0]
        
        # 已分析的新闻数
        cursor.execute("SELECT COUNT(*) FROM news WHERE ai_score IS NOT NULL")
        analyzed_count = cursor.fetchone()[0]
        
        # 利好新闻数（评分>0）
        cursor.execute("SELECT COUNT(*) FROM news WHERE ai_score > 0")
        positive_count = cursor.fetchone()[0]
        
        # 利空新闻数（评分<0）
        cursor.execute("SELECT COUNT(*) FROM news WHERE ai_score < 0")
        negative_count = cursor.fetchone()[0]
        
        # 今日新增
        cursor.execute("""
            SELECT COUNT(*) FROM news 
            WHERE date(created_at) = date('now')
        """)
        today_count = cursor.fetchone()[0]
        
        return {
            "total": total_count,
            "analyzed": analyzed_count,
            "positive": positive_count,
            "negative": negative_count,
            "today": today_count
        }
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
