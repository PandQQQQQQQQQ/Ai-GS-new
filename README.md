# A股上市公司新闻自动化收集与AI评估软件 v0.0.4

基于 PySide6 和 SQLite 的桌面应用，用于自动采集 A 股相关财经新闻并进行 AI 利好/利空评估。

## 功能特性

- 📰 **多源并发采集**：4大数据源并发抓取（东方财富、财新网、上期所快讯、央视新闻）
- 📊 **按标题严格去重**：不同来源的同一条新闻只保留一条
- 🌐 **内嵌浏览器展示**：使用 QWebEngineView 加载原文，完美显示图片和排版
- 🎨 **暗黑科技风界面**：自动提取正文 + 注入暗黑CSS，去除广告和导航栏
- 📝 **全文自动抓取**：短内容新闻自动从原文网页获取完整内容
- 🗄️ **本地存储**：SQLite 数据库存储，UI 限制显示最近200条避免卡顿
- 🤖 **AI 评估**：调用 AI 接口对新闻进行利好/利空评分（-5 到 +5）
- 🖥️ **现代化界面**：PySide6 构建的专业金融终端风格界面

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- PySide6 >= 6.5.0（含 QtWebEngine）
- akshare >= 1.12.0
- pandas >= 2.0.0
- requests >= 2.31.0
- beautifulsoup4 >= 4.12.0
- openai >= 1.0.0

## 运行方式

### 方式一：直接运行
```bash
python main.py
```

### 方式二：使用批处理（Windows）
双击运行 `run.bat`

## 使用说明

1. 点击 **"🔄 刷新新闻"** 按钮并发采集4个数据源的最新新闻
2. 点击列表中的新闻，右侧内嵌浏览器自动加载原文（暗黑风格）
3. 点击 **"🤖 AI分析选中新闻"** 进行 AI 评估
4. 点击原文链接可在外部浏览器中打开

## 项目结构

```
.
├── main.py                 # 程序入口
├── requirements.txt        # 依赖列表
├── run.bat                 # Windows 启动脚本
├── ui/
│   └── main_window.py      # 主界面（QWebEngineView + 暗黑CSS注入）
├── db/
│   └── database.py         # 数据库操作（按标题去重）
├── scraper/
│   └── news_scraper.py     # 多源并发采集 + 全文抓取
└── ai/
    └── analyzer.py         # AI 评估
```

## 数据源

| 数据源 | AkShare 接口 | 说明 |
|--------|-------------|------|
| 东方财富 | stock_news_em | 主力数据源，支持5个关键词搜索 |
| 财新网 | stock_news_main_cx | 补充数据源 |
| 上期所快讯 | futures_news_shmet | 实时短讯 |
| 央视新闻 | news_cctv | 权威宏观新闻 |

## 版本历史

### v0.0.4
- 优化新闻详情布局：标题居中、长标题自动换行完整显示
- 发布时间和来源移至详情区域右下角
- QWebEngineView 详情区域高度加大，内容空间最大化
- CSS 注入样式优化：正文容器去除冗余 padding/margin

### v0.0.3
- 新增 QWebEngineView 内嵌浏览器，完美显示原文图片和排版
- 新增 JS 内容净化：自动提取正文 + 注入暗黑科技风 CSS
- 新增多源并发采集（4个数据源，ThreadPoolExecutor）
- 新增按标题严格去重（跨来源）
- 新增全文自动抓取（短内容新闻从原文网页获取完整内容）
- UI 限制显示最近200条，避免大数据量卡顿

### v0.0.2
- 初版：财新网 + 东方财富双数据源采集
- 基础 UI 界面

## 注意事项

- 首次运行会自动创建 SQLite 数据库（data/news.db）
- AI 评估功能需要配置 API 密钥（在 ai/analyzer.py 中设置）
- 默认使用模拟 AI 分析（基于关键词），可切换至 DeepSeek/Mini/Gemini
- 内嵌浏览器需要 PySide6 的 QtWebEngine 组件

## License

MIT
