# AI Agent 项目开发统一规范

版本：v1.0  
用途：作为本项目的全局开发规范，可提供给团队成员或 AI 编程助手，用于统一项目结构、Agent 接口、输入输出格式和代码风格。

---

## 1. 项目概述

本项目是一个多智能体系统，整体结构为：

```text
Main Agent + 多个 Sub Agent
```

系统采用动态调度架构，不采用固定死流程。

Main Agent 根据以下信息判断需要调用哪些 Sub Agent：

- 用户需求
- 任务类型
- 当前上下文
- 前面 Agent 的执行结果

基本流程：

```text
User Input
    ↓
Main Agent
    ↓
选择需要调用的 Sub Agent
    ↓
Sub Agent 执行任务
    ↓
Main Agent 汇总结果
    ↓
Final Output
```

---

## 2. 项目目录结构

项目必须遵守以下结构：

```text
AI-Agent-Project/

├── main.py

├── agents/
│   ├── main_agent.py
│   ├── info_collect_agent.py
│   ├── info_extract_agent.py
│   ├── recommendation_agent.py
│   └── material_agent.py

├── config/
│   └── config.yaml

├── data/
│   ├── raw/
│   ├── processed/
│   ├── output/
│   └── temp/

├── logs/

├── tests/

├── requirements.txt

└── README.md
```

规则：

- 不允许随意修改 Agent 文件名。
- 不允许在项目根目录随意创建无关文件。
- 临时文件必须保存到 `data/temp/`。
- 原始数据保存到 `data/raw/`。
- 中间结果保存到 `data/processed/`。
- 最终结果保存到 `data/output/`。
- 日志文件保存到 `logs/`。
- 测试文件保存到 `tests/`。

---

## 3. Agent 架构

### 3.1 Main Agent

文件：

```text
agents/main_agent.py
```

类名：

```python
MainAgent
```

职责：

- 接收用户输入。
- 理解用户需求。
- 判断任务类型。
- 选择需要调用的 Sub Agent。
- 控制执行流程。
- 汇总多个 Agent 的结果。
- 生成最终输出。

Main Agent 的核心作用是：

```text
需求理解
+
Agent 调度
+
结果整合
```

Main Agent 不应该把所有业务逻辑都写在自己内部。

---

### 3.2 Sub Agents

#### Information Collection Agent

文件：

```text
agents/info_collect_agent.py
```

类名：

```python
InfoCollectAgent
```

作用：

负责采集原始信息。

信息来源可以包括：

- 网页
- 本地知识库
- 用户上传文件
- 外部 API

---

#### Information Extraction Agent

文件：

```text
agents/info_extract_agent.py
```

类名：

```python
InfoExtractAgent
```

作用：

负责把非结构化信息转换成结构化数据。

例如提取：

- 项目名称
- 截止时间
- 报名时间
- 申报要求
- 主办方
- 来源链接
- 项目摘要

---

#### Recommendation Agent

文件：

```text
agents/recommendation_agent.py
```

类名：

```python
RecommendationAgent
```

作用：

负责根据用户需求和用户背景进行项目匹配与推荐。

主要任务：

- 分析用户与项目的匹配程度
- 计算推荐分数
- 给出推荐等级
- 说明推荐理由
- 提示潜在风险

---

#### Material Assistant Agent

文件：

```text
agents/material_agent.py
```

类名：

```python
MaterialAgent
```

作用：

负责辅助生成申报或参赛相关材料。

例如：

- 申请理由
- 项目简介
- 团队分工
- 准备清单
- 时间计划
- 申报建议

---

## 4. Agent 通信协议

所有 Agent 之间必须使用统一的 Python dict / JSON 格式通信。

每个 Agent 必须实现：

```python
def run(input_data: dict) -> dict:
    pass
```

规则：

- `run()` 是 Agent 的唯一外部调用入口。
- Main Agent 只能通过 `run()` 调用 Sub Agent。
- Sub Agent 不应该让 Main Agent 直接调用内部函数。
- 所有 Agent 的输入必须是 dict。
- 所有 Agent 的输出必须是 dict。
- 不允许直接返回字符串、列表、DataFrame 或其他非标准结构。

---

## 5. 统一输入格式

所有 Agent 的输入必须遵守以下外层结构：

```json
{
  "task_id": "",
  "user_input": "",
  "task_type": "",
  "user_profile": {},
  "context": {},
  "input_data": {},
  "history": [],
  "required_output": "markdown",
  "metadata": {}
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `task_id` | 当前任务编号，用于日志、追踪和结果保存 |
| `user_input` | 用户最原始的输入内容 |
| `task_type` | 任务类型，由 Main Agent 判断 |
| `user_profile` | 用户背景信息，用于推荐和材料生成 |
| `context` | 上下文信息，用于保存其他 Agent 的中间结果 |
| `input_data` | 当前 Agent 真正需要处理的数据 |
| `history` | 当前任务已经执行过的 Agent 记录 |
| `required_output` | 用户希望的输出格式 |
| `metadata` | 语言、时间、来源等辅助信息 |

---

## 6. 统一输出格式

所有 Agent 的输出必须遵守以下外层结构：

```json
{
  "task_id": "",
  "agent_name": "",
  "status": "",
  "data": {},
  "message": "",
  "error": null,
  "next_action": null,
  "metadata": {}
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `task_id` | 必须和输入中的 `task_id` 保持一致 |
| `agent_name` | 当前执行的 Agent 名称 |
| `status` | 当前 Agent 执行状态 |
| `data` | 当前 Agent 的核心输出数据 |
| `message` | 对执行结果的简短说明 |
| `error` | 错误信息，成功时为 `null` |
| `next_action` | 给 Main Agent 的下一步建议 |
| `metadata` | 执行时间、耗时、版本等辅助信息 |

---

## 7. 状态规范

`status` 只能使用以下值：

```text
success
failed
partial
need_input
skipped
```

含义：

| 状态 | 说明 |
|---|---|
| `success` | 执行成功 |
| `failed` | 执行失败 |
| `partial` | 部分成功 |
| `need_input` | 需要用户补充信息 |
| `skipped` | 当前 Agent 未执行 |

成功时：

```json
{
  "status": "success",
  "error": null
}
```

失败时：

```json
{
  "status": "failed",
  "error": {
    "error_type": "",
    "error_message": "",
    "suggestion": ""
  }
}
```

需要用户补充信息时：

```json
{
  "status": "need_input",
  "next_action": "ask_user",
  "message": "请补充必要信息。"
}
```

规则：

- Agent 执行失败时，不允许让整个程序直接崩溃。
- 必须返回标准错误格式。
- 由 Main Agent 根据 `status` 决定下一步操作。

---

## 8. Agent 内部代码结构

每个 Agent 必须采用统一结构：

```python
class ExampleAgent:

    def __init__(self, config):
        self.config = config

    def run(self, input_data: dict) -> dict:
        pass

    def validate_input(self, input_data: dict):
        pass

    def process(self, input_data: dict) -> dict:
        pass
```

说明：

- `__init__()`：接收配置。
- `run()`：统一外部入口，负责调用校验、业务逻辑和错误处理。
- `validate_input()`：检查输入格式是否合法。
- `process()`：实现当前 Agent 的核心业务逻辑。

规则：

- `run()` 是唯一对外接口。
- 内部函数可以根据需要增加，但不能改变 `run()` 接口。
- 所有异常必须在 Agent 内部捕获，并返回统一错误格式。
- 一个 Agent 出错不能导致整个系统崩溃。

---

## 9. 代码命名规范

类名使用大驼峰命名法：

```text
PascalCase
```

示例：

```python
InfoCollectAgent
RecommendationAgent
```

函数和变量使用小写英文加下划线：

```text
snake_case
```

示例：

```python
extract_information()
task_id
agent_result
structured_items
```

固定文件名和类名对应关系：

| 文件 | 类名 |
|---|---|
| `main_agent.py` | `MainAgent` |
| `info_collect_agent.py` | `InfoCollectAgent` |
| `info_extract_agent.py` | `InfoExtractAgent` |
| `recommendation_agent.py` | `RecommendationAgent` |
| `material_agent.py` | `MaterialAgent` |

---

## 10. 禁止写法

禁止直接在代码中写死以下内容：

```python
api_key = "xxxx"
path = "C:/xxx/project"
model_name = "xxx"
return "success"
```

禁止：

- 写死 API Key。
- 写死绝对路径。
- 直接返回字符串作为结果。
- 直接返回列表作为结果。
- 修改统一输入输出结构。
- 修改 Agent 文件名。
- 修改 `run(input_data: dict) -> dict` 接口。
- 在 Sub Agent 中直接决定最终用户输出。

推荐：

```python
return {
    "task_id": input_data.get("task_id", ""),
    "agent_name": "info_collect_agent",
    "status": "success",
    "data": result_data,
    "message": "Agent executed successfully.",
    "error": None,
    "next_action": None,
    "metadata": {}
}
```

---

## 11. 配置文件规范

所有可调整参数必须放入：

```text
config/config.yaml
```

配置内容包括：

- 项目信息
- 模型配置
- API 配置
- 文件路径
- Agent 参数
- 搜索参数
- 输出格式
- 日志设置

示例：

```yaml
project:
  name: "AI-Agent-Project"
  version: "1.0"

model:
  provider: ""
  name: ""
  temperature: 0.7
  max_tokens: 2048

api:
  key: ""
  base_url: ""

agent:
  timeout: 60
  max_retry: 3

search:
  max_results: 10
  default_source:
    - web
    - knowledge_base

storage:
  raw_data_path: "./data/raw"
  processed_data_path: "./data/processed"
  output_path: "./data/output"
  temp_path: "./data/temp"
  log_path: "./logs"

output:
  default_format: "markdown"

logging:
  level: "INFO"
```

规则：

- 代码中不允许写死重要参数。
- 文件路径必须从 `config.yaml` 读取。
- 敏感信息不要提交到公开仓库。
- 如果需要示例配置，可以创建 `config.example.yaml`。

---

## 12. Agent 专属数据规则

所有 Agent 的外层输入输出结构必须保持一致。

不同 Agent 只能自定义：

```text
input_data
+
data
```

也就是说：

```text
统一通信层：
task_id
user_input
status
message
error
metadata

Agent 业务层：
input_data
data
```

不得为了某个 Agent 单独修改整体输入输出格式。

---

### 12.1 InfoCollectAgent

输入中的 `input_data` 建议格式：

```json
{
  "keywords": [],
  "sources": [],
  "max_results": 10,
  "time_range": "",
  "language": "zh-CN"
}
```

输出中的 `data` 建议格式：

```json
{
  "raw_items": [
    {
      "title": "",
      "url": "",
      "source": "",
      "raw_text": "",
      "publish_date": "",
      "collected_at": ""
    }
  ]
}
```

---

### 12.2 InfoExtractAgent

输入中的 `input_data` 建议格式：

```json
{
  "raw_items": [],
  "extract_fields": []
}
```

输出中的 `data` 建议格式：

```json
{
  "structured_items": [
    {
      "title": "",
      "type": "",
      "deadline": "",
      "registration_time": "",
      "requirements": [],
      "reward": "",
      "target_students": [],
      "organizer": "",
      "source_url": "",
      "summary": ""
    }
  ]
}
```

---

### 12.3 RecommendationAgent

输入中的 `input_data` 建议格式：

```json
{
  "structured_items": [],
  "user_profile": {},
  "recommendation_rules": {}
}
```

输出中的 `data` 建议格式：

```json
{
  "recommendations": [
    {
      "title": "",
      "match_score": 0,
      "recommend_level": "",
      "reason": "",
      "risk": "",
      "suggested_action": ""
    }
  ]
}
```

---

### 12.4 MaterialAgent

输入中的 `input_data` 建议格式：

```json
{
  "project_info": {},
  "user_profile": {},
  "material_type": "",
  "requirements": {},
  "style": "formal"
}
```

输出中的 `data` 建议格式：

```json
{
  "material_type": "",
  "content": "",
  "checklist": [],
  "suggestions": []
}
```

---

## 13. 文件命名与保存规范

文件命名规则：

- 使用小写英文。
- 使用下划线。
- 不使用中文文件名。
- 不使用空格。
- 文件名需要能体现用途。

推荐：

```text
competition_raw_task_001.json
recommendation_result_task_002.md
application_material_task_003_v1.md
```

不推荐：

```text
新建文件.py
最终版.py
测试.py
aaa.py
result.json
```

保存规则：

| 文件类型 | 保存位置 |
|---|---|
| 原始数据 | `data/raw/` |
| 中间结果 | `data/processed/` |
| 最终输出 | `data/output/` |
| 临时文件 | `data/temp/` |
| 日志文件 | `logs/` |
| 测试文件 | `tests/` |

---

## 14. AI 辅助开发规范

本项目允许使用 AI 编程助手。

但是成员使用 AI 生成代码时，必须把本规范文件提供给 AI。

AI 生成代码必须遵守：

- 当前项目目录结构。
- Agent 文件名。
- Agent 类名。
- `run(input_data: dict) -> dict` 接口。
- 统一输入格式。
- 统一输出格式。
- 错误处理格式。
- 配置文件规范。
- 文件保存规范。

禁止让 AI 自行改变：

- 项目架构。
- Agent 数量。
- Agent 文件名。
- 通信协议。
- 输入输出格式。
- 主要目录结构。

推荐提示词：

```text
请根据本项目 PROJECT_SPEC.md 规范实现当前 Agent。
不要修改项目结构。
不要修改 Agent 文件名和类名。
必须实现 run(input_data: dict) -> dict。
输入输出必须符合统一格式。
出错时必须返回 status = failed，而不是让程序崩溃。
不要写死 API Key、绝对路径或模型参数。
```

---

## 15. Agent 完成标准

一个 Agent 只有满足以下条件，才算完成：

```text
✓ 对应文件存在

✓ 对应类名正确

✓ 实现 __init__()

✓ 实现 run(input_data: dict) -> dict

✓ 实现 validate_input()

✓ 实现 process()

✓ 输入格式符合统一规范

✓ 输出格式符合统一规范

✓ 错误处理符合统一规范

✓ 可以独立运行简单测试

✓ 可以被 Main Agent 调用
```

---

## 16. 最终检查清单

项目开发过程中，需要检查：

```text
[ ] 项目目录结构是否正确
[ ] 五个 Agent 文件是否存在
[ ] Agent 类名是否正确
[ ] 所有 Agent 是否实现 run()
[ ] 所有 Agent 是否返回统一输出格式
[ ] status 是否只使用规定值
[ ] error 是否使用统一格式
[ ] 是否没有写死 API Key
[ ] 是否没有写死绝对路径
[ ] 是否使用 config.yaml 管理配置
[ ] 输出文件是否保存到 data/output/
[ ] 临时文件是否保存到 data/temp/
[ ] Main Agent 是否按需调度 Sub Agent
[ ] Main Agent 是否负责最终结果整合
[ ] Sub Agent 是否不直接决定最终输出
```

---

## 17. 最终规则

本文件是项目的全局开发规范。

所有团队成员和 AI 编程助手在以下情况下必须遵守本文件：

- 设计 Agent 架构
- 编写 Agent 代码
- 修改已有模块
- 新增功能函数
- 整合多个 Agent
- 调整输入输出格式

任何对以下内容的修改，都必须先更新本规范文件：

- 项目目录结构
- Agent 文件名
- Agent 类名
- 通信协议
- 输入输出格式
- Agent 调度方式
