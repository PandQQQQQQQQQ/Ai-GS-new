"""
AI评估模块
调用 DeepSeek、Mini、Gemini 等AI接口对新闻进行利好/利空评分
评分范围：-5（重大利空）到 +5（重大利好）
"""

import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum


class AIScoreLevel(Enum):
    """AI评分等级枚举"""
    STRONG_NEGATIVE = (-5, -4, "重大利空", "#D32F2F")
    MODERATE_NEGATIVE = (-4, -2, "中度利空", "#F44336")
    WEAK_NEGATIVE = (-2, 0, "轻度利空", "#FF9800")
    NEUTRAL = (0, 0, "中性", "#9E9E9E")
    WEAK_POSITIVE = (0, 2, "轻度利好", "#8BC34A")
    MODERATE_POSITIVE = (2, 4, "中度利好", "#4CAF50")
    STRONG_POSITIVE = (4, 5, "重大利好", "#2E7D32")
    
    def __init__(self, min_val: float, max_val: float, label: str, color: str):
        self.min_val = min_val
        self.max_val = max_val
        self.label = label
        self.color = color
    
    @classmethod
    def from_score(cls, score: float) -> "AIScoreLevel":
        """根据分数获取等级"""
        for level in cls:
            if level.min_val <= score <= level.max_val:
                return level
        return cls.NEUTRAL


@dataclass
class AnalysisResult:
    """AI分析结果数据类"""
    score: float  # 评分 -5 到 +5
    analysis: str  # 分析说明
    stocks: str  # 涉及股票代码
    confidence: float = 0.0  # 置信度 0-1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "score": self.score,
            "analysis": self.analysis,
            "stocks": self.stocks,
            "confidence": self.confidence
        }


class AIAnalyzer:
    """
    AI新闻分析器类
    支持多种AI模型（DeepSeek、Mini、Gemini等）
    """
    
    # AI分析提示词模板
    ANALYSIS_PROMPT = """你是一位专业的A股财经分析师，请对以下上市公司新闻进行分析。

【新闻内容】
{content}

请从以下维度进行分析：
1. 利好/利空评分（-5到+5分）：
   - +5分：重大利好（如业绩暴增、重大合同、技术突破）
   - +3到+4分：中度利好（如业绩增长、获得订单、行业利好）
   - +1到+2分：轻度利好（如业务拓展、合作签约）
   - 0分：中性（如常规公告、人事变动）
   - -1到-2分：轻度利空（如业绩略降、小股东减持）
   - -3到-4分：中度利空（如业绩大幅下滑、高管离职）
   - -5分：重大利空（如财务造假、重大诉讼、退市风险）

2. 分析理由：简要说明评分依据

3. 涉及股票：列出新闻中提到的股票代码（如：000001, 600000）

请以JSON格式返回结果：
{{
    "score": 评分数字,
    "analysis": "分析理由",
    "stocks": "股票代码，多个用逗号分隔",
    "confidence": 置信度0-1
}}
"""
    
    def __init__(self, model: str = "deepseek"):
        """
        初始化AI分析器
        
        Args:
            model: 使用的AI模型，可选：deepseek, mini, gemini
        """
        self.model = model.lower()
        self.api_keys = {
            "deepseek": None,  # 从环境变量或配置文件读取
            "mini": None,
            "gemini": None
        }
        
        # 检查各AI库的可用性
        self._check_dependencies()
    
    def _check_dependencies(self):
        """检查AI依赖库是否安装"""
        self.dependencies = {
            "openai": False,  # DeepSeek使用OpenAI兼容接口
            "google.generativeai": False,  # Gemini
            "requests": False  # 通用HTTP请求
        }
        
        try:
            import openai
            self.dependencies["openai"] = True
        except ImportError:
            pass
        
        try:
            import google.generativeai as genai
            self.dependencies["google.generativeai"] = True
        except ImportError:
            pass
        
        try:
            import requests
            self.dependencies["requests"] = True
        except ImportError:
            pass
    
    def set_api_key(self, model: str, api_key: str):
        """
        设置API密钥
        
        Args:
            model: 模型名称
            api_key: API密钥
        """
        self.api_keys[model.lower()] = api_key
    
    def analyze_news(self, content: str) -> Dict[str, Any]:
        """
        分析新闻内容
        
        Args:
            content: 新闻内容
            
        Returns:
            Dict: 包含score、analysis、stocks的分析结果
        """
        if not content or not content.strip():
            return {
                "score": 0,
                "analysis": "新闻内容为空，无法分析",
                "stocks": "",
                "confidence": 0
            }
        
        # 根据配置的模型选择分析方式
        if self.model == "deepseek":
            return self._analyze_with_deepseek(content)
        elif self.model == "mini":
            return self._analyze_with_mini(content)
        elif self.model == "gemini":
            return self._analyze_with_gemini(content)
        else:
            # 默认使用模拟分析（用于演示）
            return self._analyze_mock(content)
    
    def _analyze_with_deepseek(self, content: str) -> Dict[str, Any]:
        """
        使用 DeepSeek API 分析新闻
        
        Args:
            content: 新闻内容
            
        Returns:
            Dict: 分析结果
        """
        # 检查依赖
        if not self.dependencies["openai"]:
            print("警告: OpenAI库未安装，使用模拟分析")
            return self._analyze_mock(content)
        
        try:
            import openai
            
            # 设置API密钥和基础URL
            api_key = self.api_keys.get("deepseek") or "your-deepseek-api-key"
            
            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            
            # 构建提示词
            prompt = self.ANALYSIS_PROMPT.format(content=content)
            
            # 调用API
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一位专业的A股财经分析师"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            # 解析响应
            result_text = response.choices[0].message.content
            return self._parse_ai_response(result_text)
            
        except Exception as e:
            print(f"DeepSeek API调用失败: {e}")
            return self._analyze_mock(content)
    
    def _analyze_with_mini(self, content: str) -> Dict[str, Any]:
        """
        使用 Mini API 分析新闻
        
        Args:
            content: 新闻内容
            
        Returns:
            Dict: 分析结果
        """
        # Mini模型通常使用OpenAI兼容接口
        if not self.dependencies["openai"]:
            print("警告: OpenAI库未安装，使用模拟分析")
            return self._analyze_mock(content)
        
        try:
            import openai
            
            api_key = self.api_keys.get("mini") or "your-mini-api-key"
            
            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.mini.chat"  # 请替换为实际的Mini API地址
            )
            
            prompt = self.ANALYSIS_PROMPT.format(content=content)
            
            response = client.chat.completions.create(
                model="mini-chat",
                messages=[
                    {"role": "system", "content": "你是一位专业的A股财经分析师"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            result_text = response.choices[0].message.content
            return self._parse_ai_response(result_text)
            
        except Exception as e:
            print(f"Mini API调用失败: {e}")
            return self._analyze_mock(content)
    
    def _analyze_with_gemini(self, content: str) -> Dict[str, Any]:
        """
        使用 Google Gemini API 分析新闻
        
        Args:
            content: 新闻内容
            
        Returns:
            Dict: 分析结果
        """
        if not self.dependencies["google.generativeai"]:
            print("警告: Google Generative AI库未安装，使用模拟分析")
            return self._analyze_mock(content)
        
        try:
            import google.generativeai as genai
            
            api_key = self.api_keys.get("gemini") or "your-gemini-api-key"
            genai.configure(api_key=api_key)
            
            model = genai.GenerativeModel('gemini-pro')
            
            prompt = self.ANALYSIS_PROMPT.format(content=content)
            
            response = model.generate_content(prompt)
            result_text = response.text
            
            return self._parse_ai_response(result_text)
            
        except Exception as e:
            print(f"Gemini API调用失败: {e}")
            return self._analyze_mock(content)
    
    def _parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """
        解析AI返回的响应文本
        
        Args:
            response_text: AI返回的文本
            
        Returns:
            Dict: 解析后的结果
        """
        try:
            # 尝试提取JSON部分
            # 先查找JSON代码块
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接查找JSON对象
                json_match = re.search(r'\{[\s\S]*"score"[\s\S]*\}', response_text)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response_text
            
            # 解析JSON
            result = json.loads(json_str)
            
            # 确保必要字段存在
            score = float(result.get("score", 0))
            # 限制在-5到+5范围内
            score = max(-5, min(5, score))
            
            return {
                "score": score,
                "analysis": result.get("analysis", "暂无分析"),
                "stocks": result.get("stocks", ""),
                "confidence": float(result.get("confidence", 0.8))
            }
            
        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")
            # 尝试从文本中提取信息
            return self._extract_from_text(response_text)
        except Exception as e:
            print(f"解析AI响应失败: {e}")
            return {
                "score": 0,
                "analysis": f"解析失败: {str(e)}\n原始响应: {response_text[:200]}",
                "stocks": "",
                "confidence": 0
            }
    
    def _extract_from_text(self, text: str) -> Dict[str, Any]:
        """
        从非JSON格式的文本中提取信息
        
        Args:
            text: 文本内容
            
        Returns:
            Dict: 提取的结果
        """
        # 尝试提取分数
        score_match = re.search(r'评分[:：]\s*([+-]?\d+\.?\d*)', text)
        score = float(score_match.group(1)) if score_match else 0
        score = max(-5, min(5, score))
        
        # 尝试提取股票代码（6位数字）
        stocks_match = re.findall(r'\b\d{6}\b', text)
        stocks = ", ".join(stocks_match) if stocks_match else ""
        
        return {
            "score": score,
            "analysis": text[:500],  # 截取前500字符作为分析
            "stocks": stocks,
            "confidence": 0.5
        }
    
    def _analyze_mock(self, content: str) -> Dict[str, Any]:
        """
        模拟AI分析（用于演示和测试）
        基于关键词进行简单的情感分析
        
        Args:
            content: 新闻内容
            
        Returns:
            Dict: 模拟的分析结果
        """
        content_lower = content.lower()
        
        # 定义利好/利空关键词
        positive_keywords = {
            "增长": 2, "上涨": 2, "盈利": 2, "利润": 2, "业绩": 2,
            "突破": 3, "创新高": 3, "超预期": 3, "利好": 3,
            "回购": 2, "增持": 2, "分红": 2, "订单": 2,
            "合作": 1, "签约": 1, "获批": 2, "认证": 1,
            "技术突破": 4, "市场份额": 2, "领先": 2, "龙头": 2,
            "净利润": 2, "营收": 1, "增长": 2, "同比": 1
        }
        
        negative_keywords = {
            "下降": -2, "下跌": -2, "亏损": -3, "亏损": -3,
            "下滑": -2, "不及预期": -3, "利空": -3,
            "减持": -2, "解禁": -1, "诉讼": -3, "处罚": -3,
            "违规": -3, "调查": -3, "退市": -5, "ST": -4,
            "债务": -2, "违约": -4, "裁员": -2, "停产": -3,
            "召回": -2, "事故": -3, "风险": -2, "警示": -2
        }
        
        # 计算得分
        score = 0
        matched_keywords = []
        
        for keyword, value in positive_keywords.items():
            if keyword in content:
                score += value
                matched_keywords.append(f"+{value}:{keyword}")
        
        for keyword, value in negative_keywords.items():
            if keyword in content:
                score += value
                matched_keywords.append(f"{value}:{keyword}")
        
        # 限制在-5到+5范围内
        score = max(-5, min(5, score))
        
        # 生成分析说明
        if score > 0:
            analysis = f"【模拟分析】该新闻整体偏向利好。检测到以下积极因素：{', '.join(matched_keywords[:5])}。建议关注相关股票表现。"
        elif score < 0:
            analysis = f"【模拟分析】该新闻整体偏向利空。检测到以下消极因素：{', '.join(matched_keywords[:5])}。建议注意风险。"
        else:
            analysis = "【模拟分析】该新闻整体偏向中性，未检测到明显的利好或利空因素。"
        
        # 提取股票代码
        stocks_match = re.findall(r'\b\d{6}\b', content)
        stocks = ", ".join(set(stocks_match)) if stocks_match else ""
        
        # 如果没有提取到股票代码，尝试从公司名称推断
        if not stocks:
            stock_mapping = {
                "茅台": "600519",
                "宁德时代": "300750",
                "比亚迪": "002594",
                "腾讯": "00700",
                "阿里巴巴": "09988",
                "招商银行": "600036",
                "平安": "601318",
                "五粮液": "000858",
                "中芯": "688981",
                "隆基": "601012",
                "美的": "000333",
                "恒瑞": "600276",
                "药明": "603259",
                "迈瑞": "300760"
            }
            
            found_stocks = []
            for name, code in stock_mapping.items():
                if name in content:
                    found_stocks.append(code)
            
            stocks = ", ".join(found_stocks)
        
        return {
            "score": float(score),
            "analysis": analysis,
            "stocks": stocks,
            "confidence": 0.6
        }
    
    def batch_analyze(
        self, 
        news_list: List[Dict[str, Any]], 
        progress_callback=None
    ) -> List[Dict[str, Any]]:
        """
        批量分析新闻
        
        Args:
            news_list: 新闻列表
            progress_callback: 进度回调函数
            
        Returns:
            List[Dict]: 分析结果列表
        """
        results = []
        total = len(news_list)
        
        for i, news in enumerate(news_list):
            content = news.get("content", "") or news.get("title", "")
            result = self.analyze_news(content)
            results.append({
                "news_id": news.get("id"),
                **result
            })
            
            if progress_callback:
                progress_callback(int((i + 1) / total * 100))
        
        return results
    
    def get_score_level(self, score: float) -> AIScoreLevel:
        """
        获取评分等级
        
        Args:
            score: 评分值
            
        Returns:
            AIScoreLevel: 评分等级
        """
        return AIScoreLevel.from_score(score)


# 便捷函数
def analyze_news(content: str, model: str = "mock") -> Dict[str, Any]:
    """
    便捷函数：分析单条新闻
    
    Args:
        content: 新闻内容
        model: AI模型名称
        
    Returns:
        Dict: 分析结果
    """
    analyzer = AIAnalyzer(model=model)
    return analyzer.analyze_news(content)


def get_score_description(score: float) -> str:
    """
    获取评分描述
    
    Args:
        score: 评分值
        
    Returns:
        str: 评分描述
    """
    level = AIScoreLevel.from_score(score)
    return f"{level.label} ({score:+.1f})"
