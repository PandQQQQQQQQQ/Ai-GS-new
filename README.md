# A股上市公司新闻自动化收集与AI评估软件

基于 PySide6 和 SQLite 的桌面应用，用于自动采集 A 股相关财经新闻并进行 AI 利好/利空评估。

## 功能特性

- 📰 **新闻采集**：从财新网、东方财富等数据源获取最新财经新闻
- 🗄️ **本地存储**：使用 SQLite 数据库存储，支持去重
- 🤖 **AI 评估**：调用 AI 接口对新闻进行利好/利空评分（-5 到 +5）
- 🖥️ **图形界面**：PySide6 构建的现代化界面，左右分栏布局
- 🔗 **原文链接**：支持点击打开新闻原文

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- PySide6 >= 6.5.0
- akshare >= 1.12.0
- pandas >= 2.0.0
- requests >= 2.31.0
- openai >= 1.0.0

## 运行方式

### 方式一：直接运行
```bash
python main.py
```

### 方式二：使用批处理（Windows）
双击运行 `run.bat`

## 使用说明

1. 点击 **"🔄 刷新新闻"** 按钮采集最新新闻
2. 点击列表中的新闻查看详情
3. 点击 **"🤖 AI分析选中新闻"** 进行 AI 评估
4. 点击原文链接可在浏览器中打开新闻页面

## 项目结构

```
.
├── main.py                 # 程序入口
├── requirements.txt        # 依赖列表
├── run.bat                 # Windows 启动脚本
├── ui/
│   └── main_window.py      # 主界面
├── db/
│   └── database.py         # 数据库操作
├── scraper/
│   └── news_scraper.py     # 新闻采集
└── ai/
    └── analyzer.py         # AI 评估
```

## 数据源

- 财新网（stock_news_main_cx）
- 东方财富（stock_news_em）

## 注意事项

- 首次运行会自动创建 SQLite 数据库（data/news.db）
- AI 评估功能需要配置 API 密钥（在 ai/analyzer.py 中设置）
- 默认使用模拟 AI 分析（基于关键词），可切换至 DeepSeek/Mini/Gemini

## License

MIT
