<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img src="https://img.shields.io/badge/Vue3-4FC08D?logo=vuedotjs&logoColor=white">
  <img src="https://img.shields.io/badge/DeepSeek-4D6BFE?logo=openai&logoColor=white">
  <img src="https://img.shields.io/badge/DashScope-FF6A00?logo=alibabacloud&logoColor=white">
  <img src="https://img.shields.io/badge/license-MIT-green">
</p>

<h1 align="center">AI面试官 / AI Interviewer</h1>

<p align="center"><strong>AI-powered mock interview platform with real-time voice, live scoring, and detailed reports.</strong></p>

<p align="center">English | <a href="#中文">中文</a></p>

<p align="center">
  <a href="https://www.aiview.pandahead.top"><strong>Live Demo</strong></a> ·
  <a href="#screenshots"><strong>Screenshots</strong></a> ·
  <a href="项目文档.md"><strong>Docs</strong></a> ·
  <a href="部署指南.md"><strong>Deploy Guide</strong></a>
</p>

---

## Screenshots

<!-- TODO: Replace with actual screenshots -->

| Interview | Report | Dashboard |
|-----------|--------|------------|
| ![Interview](https://via.placeholder.com/400x240/2B3A67/fff?text=Interview+Room) | ![Report](https://via.placeholder.com/400x240/4A7C59/fff?text=Radar+Report) | ![Dashboard](https://via.placeholder.com/400x240/C27A3D/fff?text=Dashboard) |

---

## Features

- **Voice Interview** — Push-to-talk + STT/TTS, 15-min sessions with real-time AI conversation
- **4-stage Pipeline** — Screening → HR → Technical → Final, each with different question strategies
- **Live Coding** — Monaco Editor + AI code review (correctness, performance, readability, security)
- **Multi-dimension Scoring** — 5-axis evaluation (technical depth, breadth, engineering thinking, communication, position match)
- **Detailed Reports** — ECharts radar chart + error breakdown (fact errors / depth issues) with suggestions
- **Resume Parsing** — PDF/DOCX/Image OCR with position match analysis
- **Knowledge Base** — Upload docs → vectorize (FAISS) → RAG-enhanced interview questions
- **Admin Panel** — Question bank CRUD, document management, user management, invite codes

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.12+) |
| Frontend | Vue 3 + Vite + Element Plus |
| Database | MySQL 8.0 + Redis 7 |
| LLM | DeepSeek API |
| Voice | DashScope Qwen (ASR-Realtime / TTS) |
| Embeddings | sentence-transformers (BAAI/bge-small-zh-v1.5) + FAISS |
| Browser VAD | onnxruntime-web + Silero VAD |
| Deployment | Docker Compose + Nginx + Let's Encrypt |

---

## Quick Start

### Docker (Recommended)

```bash
cd FastAPI_ai_interview
cp .env.example .env   # Edit .env with your API keys
docker compose up -d
docker compose exec backend alembic upgrade head
```

### Local Dev

**Backend:**
```bash
cd FastAPI_ai_interview
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd vue_ai_interview
npm install
npm run dev
```

---

## API Overview

| Module | Endpoint | Description |
|--------|----------|-------------|
| Auth | `POST /api/auth/register` | Register (invite code + SMS + password) |
| Auth | `POST /api/auth/login` | Login, returns JWT pair |
| SMS | `POST /api/captcha/send` / `verify` | SMS verification codes |
| Resume | `POST /api/resumes/upload` | Upload & parse resume |
| Interview | `POST /api/interviews` | Create interview, returns ws_token |
| Interview | `GET /api/interviews/{id}/report` | Get interview report |
| Admin | `/api/admin/*` | Question bank / documents / users |
| Real-time | `WS /ws/interview/{id}?token=` | Live interview channel |

Full API spec in [项目文档.md](项目文档.md).

---

## Scoring Dimensions

| Dimension | Description |
|-----------|-------------|
| Technical Depth | Understanding of principles & fundamentals |
| Technical Breadth | Knowledge across domains |
| Engineering Thinking | Architecture, scalability, code quality |
| Communication | Clarity, structured expression |
| Position Match | Relevance to target role |

---

## Project Structure

```
AI_Interview/
├── FastAPI_ai_interview/    # Backend
│   ├── app/
│   │   ├── api/v1/          # REST routers
│   │   ├── core/            # Config, security, middleware
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── services/        # Business logic
│   │   ├── agents/          # LLM agents
│   │   └── ws/              # WebSocket + audio
│   ├── docker-compose.yml
│   └── .env.example
├── vue_ai_interview/        # Frontend
│   ├── src/views/           # Pages
│   ├── src/components/      # Components
│   └── src/composables/     # Composables
├── 项目文档.md               # Technical docs
├── 开发日志.md               # Dev log
├── 部署指南.md               # Deploy guide
└── README.md
```

---

<h2 id="中文">中文</h2>

## AI面试官

AI 驱动的模拟面试练习平台。支持语音实时交互、四阶段面试、编程题评审、五维度评分和报告生成。

**在线地址：** [https://www.aiview.pandahead.top](https://www.aiview.pandahead.top)

### 功能特性

- **语音面试** — 按住说话，实时 STT/TTS，与 AI 面试官自然对话
- **四阶段流程** — 初筛 → HR面 → 技术面 → 终面，每阶段有差异化出题策略和追问深度
- **在线编程** — Monaco Editor + AI 代码评审（正确性/性能/可读性/安全性四维评审）
- **五维度评分** — 技术深度/广度/工程化思维/沟通逻辑/岗位匹配度
- **详细报告** — ECharts 雷达图 + 错误解析（事实错误/深度不足）+ 逐题优化建议
- **简历解析** — 支持 PDF/DOCX/图片 OCR，岗位匹配度分析
- **知识库** — 上传文档 → FAISS 向量化 → RAG 增强出题
- **管理后台** — 题库 CRUD / 文档管理 / 用户管理 / 内测邀请码
- **安全加固** — 全栈安全审查，Token 吊销、文件认证下载、MIME 校验、Nginx TLS

### 技术栈

| 层面 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python 3.12+) |
| 前端框架 | Vue 3 + Vite + Element Plus |
| 数据库 | MySQL 8.0 + Redis 7 |
| 大模型 | DeepSeek API |
| 语音 | DashScope 千问 (Qwen-ASR-Realtime / Qwen-TTS) |
| 向量库 | FAISS + sentence-transformers (BAAI/bge-small-zh-v1.5) |
| 浏览器 VAD | onnxruntime-web + Silero VAD |
| 异步任务 | Celery + Redis |
| 部署 | Docker Compose + Nginx + Let's Encrypt |

### 快速启动

**Docker（推荐）：**
```bash
cd FastAPI_ai_interview
cp .env.example .env   # 编辑 .env 填入 API Key
docker compose up -d
docker compose exec backend alembic upgrade head
```

**本地开发：**
```bash
# 后端
cd FastAPI_ai_interview
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 前端
cd vue_ai_interview
npm install && npm run dev
```

### API 概览

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `POST /api/auth/register` | 注册（邀请码+短信+密码） |
| 认证 | `POST /api/auth/login` | 登录，返回 JWT 对 |
| 短信 | `POST /api/captcha/send` / `verify` | 短信验证码 |
| 简历 | `POST /api/resumes/upload` | 上传并解析简历 |
| 面试 | `POST /api/interviews` | 创建面试，返回 ws_token |
| 面试 | `GET /api/interviews/{id}/report` | 获取面试报告（含雷达图数据） |
| 管理 | `/api/admin/*` | 题库/文档/用户管理 |
| 实时 | `WS /ws/interview/{id}?token=` | 面试实时通信 |

### 评分维度

| 维度 | 说明 |
|------|------|
| 技术深度 | 技术原理、底层机制理解 |
| 技术广度 | 知识面宽度，跨领域能力 |
| 工程化思维 | 架构设计、可扩展性、代码质量 |
| 沟通逻辑 | 表达清晰度、结构化思维 |
| 岗位匹配度 | 回答与目标岗位的契合程度 |

### 项目结构

```
AI_Interview/
├── FastAPI_ai_interview/    # 后端
│   ├── app/
│   │   ├── api/v1/          # REST 路由
│   │   ├── core/            # 配置/安全/中间件
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── services/        # 业务逻辑
│   │   ├── agents/          # LLM Agent（面试官/评分/报告/代码评审）
│   │   └── ws/              # WebSocket + 音频处理
│   ├── docker-compose.yml
│   └── .env.example
├── vue_ai_interview/        # 前端
│   ├── src/views/           # 页面
│   ├── src/components/      # 组件
│   └── src/composables/     # 组合函数
├── 项目文档.md               # API/数据库/前端架构/设计风格
├── 开发日志.md               # 开发记录 + 联桥排查
├── 部署指南.md               # 部署步骤 + 踩坑录
└── README.md
```

### 文档

| 文档 | 内容 |
|------|------|
| [项目文档.md](项目文档.md) | API接口 / 数据库结构 / 前端架构 / 设计风格 |
| [开发日志.md](开发日志.md) | 全阶段开发记录 + 37轮联桥排查 |
| [部署指南.md](部署指南.md) | 服务器部署步骤 + 11个踩坑录 + 运维命令 |

---

## License

MIT
