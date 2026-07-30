# 赛智通（SaiZhiTong）

赛智通是面向大学生科研与竞赛场景的多智能体对话助手。用户可以像使用 ChatGPT 一样描述自己的专业、年级、兴趣和参赛目标；系统会在信息不足时继续追问，随后完成竞赛信息采集、通知抽取、项目推荐、赛事详情解释和报名材料生成。

> 当前版本用于课程、竞赛和研究演示。竞赛信息、推荐结果与生成材料仅供辅助决策，正式报名或提交前请以赛事官网为准并人工复核。

当前生产环境采用 **React + GitHub Pages（前端）**、**FastAPI + Render（后端）**、
**Supabase（数据库）** 和 **GitHub Actions（异步刷新任务）**。Streamlit 和
Gradio 入口仍保留用于本地调试。

## 当前功能

- GPT 风格对话界面：React 前端提供连续对话、竞赛库和会话状态展示。
- 上下文信息收集：专业和年级明确后，可一次性补充竞赛方向、技能和级别偏好。
- 竞赛信息采集：支持赛氪、52竞赛、天池、和鲸和 DataFountain 等来源，也支持解析本地通知文件。
- 通知结构化抽取：提取名称、截止日期、主办方、参赛要求和原始网页等字段。
- 个性化推荐：综合用户画像、兴趣、截止日期和硬性条件进行筛选与排序。
- 赛事详情追问：用户可通过“详细介绍第二个”等自然语言继续了解刚才的推荐结果。
- 智能任务路由：根据当前对话状态区分信息补充、项目推荐、赛事详情和材料生成，避免重复推荐。
- Word 材料生成：生成可编辑的 `.docx` 初稿，支持竞赛报名个人简历及项目材料；文件名包含对应竞赛名称。
- 异步数据库刷新：网页按钮或每天北京时间 02:00 的定时任务在 GitHub Actions 中运行采集和抽取，不阻塞推荐对话。
- 降级运行：LLM 暂时不可用时，系统仍会尽量保留采集到的可信字段并使用规则完成基础流程。

## Agent 分工

```text
用户对话
   │
   ▼
MainAgent（理解意图、维护上下文、调度与整合结果）
   │
   ├── InfoCollectAgent       采集公开竞赛数据或解析本地文件
   ├── InfoExtractAgent       抽取结构化竞赛字段
   ├── RecommendationAgent    补全推荐所需画像并完成匹配排序
   └── MaterialAgent          生成可下载的 Word 报名材料
```

典型流程：

```text
竞赛推荐：信息补全 → 读取 Supabase 已处理数据 → 项目推荐
数据库刷新：InfoCollectAgent → 仅对新增/变化记录运行 InfoExtractAgent → Supabase
粘贴通知：通知抽取 → 详情展示或项目推荐
了解项目：读取本轮推荐上下文 → 返回简介、官网和待核实事项
生成材料：确认目标竞赛与材料类型 → MaterialAgent → Word 下载
```

无关问题不会被误判为竞赛任务。系统会说明当前能力范围，并引导用户回到竞赛推荐、通知分析或材料生成。

## 项目结构

```text
.
├── agents/
│   ├── main_agent.py              # 主调度与对话意图处理
│   ├── info_collect_agent.py      # 信息采集 Agent
│   ├── info_extract_agent.py      # 信息抽取 Agent
│   ├── recommendation_agent.py    # 项目推荐 Agent
│   ├── material_agent.py          # Word 材料生成 Agent
│   └── info_collect/              # 采集器、解析器和存储组件
├── config/
│   ├── config.yaml                # 非敏感运行配置
│   ├── extraction_prompt.yaml     # 信息抽取提示词
│   └── material_prompts.yaml      # 材料模板
├── data/                          # 运行数据与生成文件
├── docs/                          # 项目规范文档
├── tests/                         # 自动化测试
├── frontend/                      # React + TypeScript + Vite 生产前端
├── api.py                         # FastAPI 生产后端
├── scripts/refresh_competitions.py # GitHub Actions 刷新入口
├── streamlit_app.py               # 旧版 Streamlit 调试入口
├── app.py                         # 旧版 Gradio 调试入口
├── main.py                        # 命令行演示入口
├── render.yaml                    # Render 生产后端部署配置
├── requirements.txt               # 核心 Python 依赖
└── requirements-embedding.txt     # 可选本地 ONNX embedding 依赖
```

## 环境要求

- Python 3.11（推荐版本）
- pip
- Node.js 20 和 npm（React 前端）
- DeepSeek API Key（建议配置；未配置时部分能力进入降级模式）

安装依赖：

```powershell
pip install -r requirements.txt
```

Render 512MB 实例默认使用轻量 TF-IDF 候选粗排，不应启用本地 ONNX
embedding。内存充足的本地环境如需开启，可执行：

```powershell
pip install -r requirements-embedding.txt
$env:ENABLE_LOCAL_EMBEDDING="true"
```

Windows 下创建本地环境变量文件：

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat

# Supabase 云存储
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_secret_or_service_role_key
# 数据库密码，用于首次运行时自动建表
SUPABASE_DB_PASSWORD=your_database_password

# Render 触发 GitHub Actions 数据刷新
GITHUB_ACTIONS_TOKEN=your_fine_grained_github_token
REFRESH_IP_HASH_SALT=replace_with_a_random_secret
ENABLE_LOCAL_EMBEDDING=false
```

> 新版 Supabase 的 Publishable key 对应旧版 anon key；`sb_secret_...`
> Secret key 对应旧版 service-role key。Secret/service-role key 只能用于
> Render、GitHub Actions或本地后端，绝不能放入前端。
>
> 数据库密码在 Supabase Dashboard → Settings → Database → Connection string 中查看（替换 `[YOUR-PASSWORD]` 部分）。

不要把真实 API Key、数据库密码写入源码、README 或 Git 提交。`.env` 已被 Git 忽略。

## 本地运行

当前生产架构的本地启动方式：

```powershell
# 仓库根目录启动 FastAPI
uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# 另一个终端启动 React 前端
Set-Location frontend
npm install
$env:VITE_API_BASE_URL="http://localhost:8000"
npm run dev
```

推荐使用 Streamlit 对话界面：

```powershell
streamlit run streamlit_app.py
```

浏览器通常会自动打开 `http://localhost:8501`。如未自动打开，请手动访问该地址。

旧版 Gradio 调试界面仍可运行：

```powershell
python app.py
```

默认地址为 `http://127.0.0.1:7860`。

## 对话示例

```text
用户：我是计算机专业大三学生，想参加人工智能方向的国家级竞赛。
助手：你目前掌握哪些技能？例如 Python、算法、机器学习或团队协作。
用户：我会 Python 和机器学习，也有团队协作经验。
助手：根据已记录的信息，为你采集并推荐合适的竞赛……
用户：详细介绍第二个。
助手：返回该竞赛的简要概括、匹配原因、截止日期、官网链接和待核实事项。
用户：给第二个竞赛生成报名个人简历。
助手：确认目标和材料类型后生成 Word 文件，可在侧栏下载。
```

生成的文件示例：

```text
2026华智高校大学生人工智能大赛_竞赛报名个人简历.docx
```

## 自动化测试

运行完整测试：

```powershell
python -m pytest -q -p no:cacheprovider
```

测试覆盖四个子 Agent、MainAgent 调度、对话状态、意图纠正、推荐详情、材料选择、Word 文件生成以及 LLM 降级流程。

## 部署到 Streamlit Community Cloud

> 当前生产部署使用 GitHub Pages + Render。此章节保留用于旧版 Streamlit
> 调试入口。

1. 将功能分支通过 Pull Request 合并到 GitHub `main`。
2. 登录 [Streamlit Community Cloud](https://share.streamlit.io/)。
3. 选择本项目仓库、`main` 分支和入口文件 `streamlit_app.py`。
4. 在 App 的 **Settings → Secrets** 中配置：

   ```toml
   DEEPSEEK_API_KEY = "你的真实密钥"
   DEEPSEEK_MODEL = "deepseek-chat"
   SUPABASE_URL = "你的 Supabase 项目 URL"
   SUPABASE_ANON_KEY = "你的 Supabase 匿名密钥"
   SUPABASE_DB_PASSWORD = "你的数据库密码"
   ```

5. 保存后点击 Deploy 或 Reboot app。

后续合并到 `main` 的提交通常会触发自动重新部署。如果线上仍显示旧版，可在 Streamlit 管理页面执行 Reboot app。

## 数据与生成文件

- `data/raw`：JSON 模式下持久化的原始竞赛数据和日志。
- `data/processed`：结构化处理结果。
- `data/output`：MaterialAgent 生成的 `.docx` 文件。
- `data/temp`：运行期临时文件。

**Supabase 持久化存储**：配置 `SUPABASE_URL` + `SUPABASE_ANON_KEY` + `SUPABASE_DB_PASSWORD` 后，采集到的竞赛数据会写入云端 PostgreSQL 数据库。后续请求优先从数据库搜索已有数据，仅在数据不够或超过有效期（默认 24小时）时触发爬虫刷新。

### 竞赛库逻辑全量刷新

1. 在 Supabase SQL Editor 执行 `migration.sql`，创建刷新字段和
   `refresh_jobs` 表。
2. 在 GitHub Actions Secrets 配置 `SUPABASE_URL`、
   `SUPABASE_ANON_KEY`、`SUPABASE_SERVICE_ROLE_KEY` 和
   `DEEPSEEK_API_KEY`。
3. 在 Render 配置 `SUPABASE_URL`、`SUPABASE_ANON_KEY`、
   `SUPABASE_SERVICE_ROLE_KEY`、`DEEPSEEK_API_KEY` 和
   `GITHUB_ACTIONS_TOKEN`。
4. Fine-grained GitHub Token 必须允许访问当前仓库，并配置
   **Repository permissions → Actions → Read and write**。
5. 合并到 `main` 后，`Refresh Competition Database` 工作流支持网页
   手动触发，并在北京时间每天 02:00 自动运行。

刷新会重新扫描所有数据源，通过内容哈希区分新增、变化和未变化记录。
只有新增或原文变化的记录进入信息抽取；单个来源失败时保留该来源旧数据，
明确过期的竞赛会被删除。

刷新链路为：

```text
竞赛库按钮 → Render API → GitHub Actions → InfoCollectAgent
           → InfoExtractAgent → Supabase
```

GitHub Actions 只提供临时运行环境，实际采集和抽取仍由项目中的两个 Agent
执行。Render 与 GitHub Actions 必须连接同一个 `SUPABASE_URL`。

## Supabase 数据库表结构

配置好 Supabase 后，首次启动会自动通过直连 PostgreSQL 创建以下两张表和一个索引（如果有限制无法自动建表，可以手动操作，将migration.sql的语句复制到 SQL Editor后运行即可）：

**competitions** — 竞赛数据主表

| 列 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL | 主键 |
| title | TEXT | 竞赛标题 |
| url | TEXT | 竞赛页面链接 |
| source | TEXT | 数据来源（saikr / 52jingsai / ali_tianchi 等） |
| publish_date | TEXT | 发布日期 |
| description | TEXT | 竞赛描述 |
| organizer | TEXT | 主办方 |
| organizer_list / co_organizers / supporters | JSONB | 主办 / 协办 / 支持单位列表 |
| regist_start / regist_end | TEXT | 报名起止时间 |
| contest_start / contest_end | TEXT | 比赛起止时间 |
| category | TEXT | 分类 |
| level | TEXT | 级别 |
| attachments | JSONB | 附件列表 |
| raw_text | TEXT | 原始文本全文 |
| collected_at | TEXT | 采集时间（建有降序索引） |
| updated_at | TEXT | 最后更新时间 |
| **唯一约束** | | `(url, source)` — 同一来源同一链接不会重复存储 |

**crawl_logs** — 爬取日志表

| 列 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL | 主键 |
| task_id | TEXT | 任务 ID |
| source | TEXT | 数据来源 |
| pages_crawled | INTEGER | 爬取页数 |
| items_found / items_new / items_updated | INTEGER | 统计字段 |
| status | TEXT | running / completed / failed |
| error_message | TEXT | 异常信息 |
| started_at / finished_at | TEXT | 起止时间 |

**索引**

- `idx_competitions_collected_at` — `collected_at DESC`，加速按时间倒序搜索。

如果用户未配置数据库密码，终端会输出完整的建表 SQL，复制到 Supabase SQL Editor 中手动执行即可。

## 已知限制

- 公开网页的网络状态或页面结构变化可能影响采集结果。
- 赛事名称、日期、主办方和报名要求应以链接中的官方页面为准。
- 未配置或无法访问 DeepSeek API 时，复杂意图理解、摘要和通知抽取能力会下降。
- 推荐质量依赖用户画像完整度；信息不足时系统会继续追问。
- Word 材料是可编辑初稿，不保证直接满足所有学校或赛事的正式模板。
- 免费云平台可能休眠，首次访问和首次 Agent 调用可能较慢。
- Render 512MB 实例开启本地 ONNX embedding 可能造成内存超限，生产环境默认关闭。
- 未配置 Supabase 时竞赛数据仅在内存中使用，重启或重新部署后丢失。

## 安全与隐私

- 不要在公开部署中输入身份证号、银行卡号、密码等敏感信息。
- 不要将 API Key、`.env` 或本地隐私数据提交到 GitHub。
- 生成材料包含个人信息时，请下载后及时检查，并避免在共享设备上长期保留。
- 正式报名和提交前必须人工复核全部内容。

## 设计文档

- [项目规范（中文）](docs/PROJECT_SPEC_CN.md)
- [Project Specification](docs/PROJECT_SPEC.md)
