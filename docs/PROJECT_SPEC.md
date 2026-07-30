# AI Agent Project Development Specification

Version: v1.0

## 1. Project Overview

This project is a Multi-Agent system based on:

Main Agent + Multiple Sub Agents

The system uses dynamic orchestration. The workflow is not fixed.

Main Agent decides which Sub Agent(s) should be called according to:
- User requirements
- Task type
- Current context
- Previous results

Basic flow:

User Input
    ↓
Main Agent
    ↓
Select Required Agent(s)
    ↓
Sub Agent Execution
    ↓
Main Agent Integration
    ↓
Final Output


## 2. Project Structure

```
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

Rules:
- Do not change Agent filenames.
- Final outputs must be stored in data/output/.
- Temporary files must be stored in data/temp/.
- Configurations must be stored in config/.


## 3. Agent Architecture

### Main Agent

File:
agents/main_agent.py

Class:
MainAgent

Responsibilities:
- Receive user requests.
- Understand task requirements.
- Determine task type.
- Select required Sub Agents.
- Control execution process.
- Integrate final results.

Main Agent is responsible for:
Input Understanding + Agent Scheduling + Result Integration


### Sub Agents

InfoCollectAgent:
- Collect raw information from web sources, knowledge base, files, or APIs.

InfoExtractAgent:
- Convert unstructured information into structured data.

RecommendationAgent:
- Match projects with user requirements and provide scores and reasons.

MaterialAgent:
- Generate application-related materials such as project introduction, reasons, plans, and checklists.


## 4. Agent Communication Protocol

All Agents must communicate using Python dict / JSON format.

Every Agent must implement:

```python
def run(input_data: dict) -> dict:
    pass
```

Rules:
- run() is the only external interface.
- Main Agent can only call Sub Agents through run().
- All inputs must be dict.
- All outputs must be dict.


## 5. Standard Input Format

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

Required fields:
- task_id
- user_input
- task_type
- user_profile
- context
- input_data
- history
- required_output
- metadata


## 6. Standard Output Format

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

Status values:

- success
- failed
- partial
- need_input
- skipped


Rules:
- Failed execution must return error information.
- Agent failure must not crash the whole system.


## 7. Agent Code Structure

Every Agent should follow:

```python
class ExampleAgent:

    def __init__(self, config):
        self.config = config

    def run(self, input_data):
        pass

    def validate_input(self, input_data):
        pass

    def process(self, input_data):
        pass
```

Rules:
- run() is the only external interface.
- Use modular functions.
- Handle exceptions internally.
- Return standard output format.


## 8. Code Style

Class names:

PascalCase

Example:
InfoCollectAgent


Functions and variables:

snake_case

Example:
extract_information()
task_id
agent_result


Forbidden:
- Hard-coded API keys.
- Hard-coded absolute paths.
- Returning raw strings or lists instead of standard output format.


## 9. Configuration Rules

All configurable parameters must be stored in:

config/config.yaml

Including:
- Model settings
- API settings
- File paths
- Agent parameters
- Output settings

Do not hard-code:
- API keys
- Model names
- Important parameters
- File paths


## 10. Agent Specific Data Rules

The global communication format cannot be changed.

Each Agent can only customize:

input_data

and

data

The communication layer remains:

- task_id
- status
- message
- error
- metadata


## 11. File Naming Rules

Use:
- lowercase English
- underscores
- meaningful names

Examples:

competition_raw_task_001.json

recommendation_result_task_001.md

Do not use:

- Chinese filenames
- Spaces
- Random names


Storage:

raw data:
data/raw/

processed data:
data/processed/

final output:
data/output/

temporary files:
data/temp/


## 12. AI Assisted Development Rules

When using AI coding assistants:

This specification must be provided to the AI.

AI-generated code must:
- Follow project structure.
- Keep Agent filenames unchanged.
- Keep class names unchanged.
- Keep run() interface unchanged.
- Follow input/output protocols.
- Use configuration files.
- Avoid unnecessary architecture changes.


Recommended instruction:

"Generate code according to PROJECT_SPEC.md. Do not modify project architecture. Follow the defined Agent interface and communication protocol."


## 13. Agent Completion Criteria

An Agent is complete only when:

- Correct file created.
- Correct class implemented.
- run() implemented.
- Input/output format follows specification.
- Error handling implemented.
- Can run independently.
- Can be called by Main Agent.


## 14. Final Rule

This document is the global development specification.

All developers and AI assistants must follow this document when:

- Designing Agents.
- Writing code.
- Modifying modules.
- Adding new functions.
- Integrating multiple Agents.

Any modification to:
- Project structure
- Agent architecture
- Communication protocol
- Input/output format

must update this document first.
