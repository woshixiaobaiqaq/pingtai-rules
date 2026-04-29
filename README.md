# platform-content-audit

基于 FastAPI + PostgreSQL + pgvector 的多平台内容审查服务，支持抖音、小红书、视频号三类平台的规则导入、风险审查、命中解释、三档改写与全文修订输出。项目同时提供浏览器可直接访问的网页工作台。

## 功能范围

- 输入一段文章内容，输出各平台风险等级。
- 返回具体命中的风险句子、命中原因、规则 ID、规则标题、规则原文引用。
- 使用「词典/正则初筛 + tag filter + keyword + vector similarity」召回候选规则。
- 判定阶段只允许使用候选规则，不允许编造规则。
- 输出三档改写建议：`safe`、`balanced`、`conversion`。
- 输出平台级全文修订版。

## 技术栈

- Python 3.11 或 3.12
- FastAPI
- PostgreSQL
- pgvector
- SQLAlchemy 2.0
- Alembic
- Pydantic v2

## 项目结构

```text
platform-content-audit/
├── alembic/
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   └── web/
├── data/
│   └── rule_library/
│       ├── manifest.json
│       ├── douyin/
│       │   ├── catalog.json
│       │   └── rules.json
│       ├── xiaohongshu/
│       └── video_channel/
├── tests/
├── .env.example
├── alembic.ini
├── docker-compose.yml
└── pyproject.toml
```

## 核心流程

1. 文本清洗与分句，保留原文位置索引。
2. 通过内置词典和正则生成 candidate tags。
3. 通过 `tag filter + keyword + vector similarity` 召回候选规则。
4. 在候选规则集合内完成规则绑定判定。
5. 聚合结构化 JSON 审查报告。
6. 生成 `safe`、`balanced`、`conversion` 三档改写和全文修订版。

## 数据模型

- `rules`: 规则主表，存平台、标题、规则原文、关键词、正则等。
- `rule_tags`: 规则标签表，用于 tag filter 召回。
- `rule_embeddings`: 规则向量表，用于 pgvector 相似度召回。
- `audit_tasks`: 审查任务表，存原文、清洗结果、分句映射和任务状态。
- `audit_results`: 平台维度的审查结果表，存命中句子、命中规则、改写结果与结构化报告。

## 本地运行

### 1. 启动 PostgreSQL + pgvector

```bash
cd /Users/m/亿一的AI小助理/open-codex/platform-content-audit
docker compose up -d
```

### 2. 创建 Python 3.11/3.12 环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

默认数据库连接：

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/platform_content_audit
```

### 4. 执行数据库迁移

```bash
alembic upgrade head
```

### 5. 启动服务

```bash
uvicorn app.main:app --reload
```

服务启动后访问：

- Web 工作台: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## 网页端使用

启动服务后，直接打开首页即可使用 Web 端。

1. 在网页输入待审查文章内容。
2. 选择目标平台。
3. 点击“开始审查”。
4. 页面会展示：
   各平台风险等级、命中句子、匹配规则、命中原因、三档改写建议、全文修订版。
5. 右侧面板会同步展示原始结构化 JSON，可直接复制。

## 导入规则

规则库已改为按平台拆分存放。当前已完成抖音真实分类规则本地化，小红书和视频号目录已预留。

导入抖音规则库：

```bash
curl -X POST "http://127.0.0.1:8000/api/rules/import" \
  -H "Content-Type: application/json" \
  --data @data/rule_library/douyin/rules.json
```

也可以直接提交 JSON：

```json
{
  "rules": [
    {
      "platform": "douyin",
      "rule_id": "DY-CAT-008",
      "title": "诱导互动",
      "content": "禁止通过欺骗、强迫、道德绑架等方式诱导点赞、评论、关注和完整观看。",
      "severity": "high",
      "tags": ["interaction_manipulation"],
      "keywords": ["扣1", "评论666", "点赞关注"],
      "regex_patterns": ["评论区.*扣1"]
    }
  ]
}
```

## 审查接口

```bash
curl -X POST "http://127.0.0.1:8000/api/audit" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "这个方法保证你7天回本，评论区留言领取资料。",
    "platforms": ["抖音", "小红书", "视频号"],
    "persist": true
  }'
```

返回结构示意：

```json
{
  "report": {
    "task": {
      "id": "uuid",
      "status": "completed"
    },
    "original_content": "string",
    "cleaned_content": "string",
    "sentence_segments": [],
    "platform_results": [
      {
        "platform": "douyin",
        "risk_level": "high",
        "candidate_tags": [],
        "hit_sentences": [],
        "matched_rules": [],
        "rewrite_options": {
          "safe": "string",
          "balanced": "string",
          "conversion": "string"
        },
        "revised_text": "string"
      }
    ]
  }
}
```

## 测试

```bash
pytest
```

当前测试覆盖：

- 首页网页可访问
- 文本清洗与分句位置映射
- 词典/正则初筛
- 抖音本地规则库文件结构与字段完整性
- API 返回结构化 JSON

## GitHub 与部署

项目已补充 Render 部署配置文件：

- `render.yaml`
- `.gitignore`

当前部署策略：

- 以 `file` 模式直接读取本地规则库，不强依赖 PostgreSQL
- 启动命令：`uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- 适合先把 Web 工作台和规则命中能力快速上线

建议上线流程：

1. 将项目目录初始化为独立 Git 仓库并推送到 GitHub。
2. 在 Render 中创建 Blueprint，直接读取仓库根目录的 `render.yaml`。
3. 若后续需要切换到数据库模式，再补 PostgreSQL / pgvector 服务。

说明：

- `data/source_archives/` 和 `output/` 中的大体积本地归档、Excel 导出已通过 `.gitignore` 排除，不会进入 GitHub。
- 运行所需的平台规则库仍保留在 `data/rule_library/` 中，会随仓库一起推送。

## 说明

- 当前默认向量服务使用本地哈希嵌入，便于离线开发和测试。
- `app/services/llm_judge.py` 已预留规则绑定提示词构造逻辑，默认执行路径仍严格限制在候选规则内。
- 如果需要接入真实 LLM，可在 `RuleBoundJudgeService` 上层增加外部模型调用，但输入必须继续只传候选规则集合。
- 抖音规则库依据 2026 年 3 月 11 日本地化的规则解读页面整理，当前以一级分类为测试粒度，每条规则都附带 `commerce_id`、分类说明和代表性示例。
