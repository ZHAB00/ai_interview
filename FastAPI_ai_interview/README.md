# AI 面试官 — 后端服务

基于 FastAPI 的 AI 模拟面试练习平台后端，支持多阶段面试、实时语音交互、代码评审、多维评分和报告生成。

## 技术栈

| 层面 | 技术 |
|------|------|
| 框架 | FastAPI (Python 3.12+) |
| 数据库 | MySQL 8.0 + Redis 7 |
| LLM | DeepSeek API (OpenAI 兼容) |
| 向量库 | FAISS + sentence-transformers |
| 异步任务 | Celery + Redis |
| 音频 | 阿里云 STT/TTS (可扩展 Provider) |

## 快速启动

### 1. 环境配置

```bash
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY 等必要配置
```

### 2. Docker 一键启动

```bash
docker compose up -d
```

启动服务：
- FastAPI: http://localhost:8000
- Celery Worker: 后台异步任务
- Flower 监控: http://localhost:5555
- MySQL: localhost:3306
- Redis: localhost:6379

### 3. 本地开发启动

```bash
pip install -r requirements.txt

# 初始化数据库
alembic upgrade head

# 预置题库
python -m app.main

# 启动 API 服务
uvicorn app.main:app --reload --port 8000

# 启动 Celery Worker (另一终端)
celery -A app.services.celery_app worker --loglevel=info
```

## API 概览

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `POST /api/auth/register` | 手机号注册 |
| 认证 | `POST /api/auth/login` | 登录获取 JWT |
| 简历 | `POST /api/resumes/upload` | 上传并解析简历 |
| 简历 | `GET /api/resumes/{id}` | 查看简历详情 |
| 面试 | `POST /api/interviews` | 创建面试，获取 WS Token |
| 面试 | `GET /api/interviews/history` | 面试历史列表 |
| 面试 | `GET /api/interviews/{id}/report` | 获取面试报告 |
| 反馈 | `POST /api/feedback/{id}` | 提交评分反馈 |
| 管理 | `POST /api/admin/questions` | 创建题目 |
| 管理 | `POST /api/admin/questions/batch` | 批量导入题目 |
| 管理 | `POST /api/admin/documents` | 上传知识库文档 |
| 管理 | `POST /api/admin/documents/{id}/reprocess` | 重新处理文档 |
| 管理 | `PUT /api/admin/users/{id}/disable` | 禁用/启用用户 |
| WebSocket | `/ws/interview/{id}?token=` | 实时面试通道 |

完整接口文档见 `项目说明文件/接口文档/接口文档v1.0.md`。

## 项目结构

```
backend/
├── app/
│   ├── api/v1/         # REST API 路由
│   ├── core/           # 配置、安全、日志、中间件
│   ├── models/         # SQLAlchemy ORM 模型
│   ├── schemas/        # Pydantic 请求/响应
│   ├── services/       # 业务逻辑层
│   ├── agents/         # AI Agent (面试官/评分/报告/代码评审)
│   ├── ws/             # WebSocket + 音频处理
│   └── main.py         # 应用入口
├── tests/              # 测试用例
├── alembic/            # 数据库迁移
├── docker-compose.yml
└── Dockerfile
```

## 面试流程

```
用户注册 → 上传简历 → 创建面试 → WebSocket 连接
    → 初筛 → HR面 → 技术面(含编程题) → 终面
    → 报告生成(五维度评分 + 简历扣分 + 错误解析)
```

## 评分维度

| 维度 | 说明 | 量表 |
|------|------|------|
| 技术深度 | 技术原理、底层机制理解 | 60/70-85/90-100 |
| 技术广度 | 知识面宽度 | 同上 |
| 工程化思维 | 架构、可扩展性、代码质量 | 同上 |
| 沟通逻辑 | 表达清晰度、结构化思维 | 同上 |
| 项目经验匹配度 | 回答与岗位匹配程度 | 同上 |

## 环境变量

完整配置项见 `.env.example`。关键变量：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key (必需) |
| `DATABASE_URL` | MySQL 连接串 (自动计算) |
| `REDIS_URL` | Redis 连接串 (自动计算) |
| `PASS_THRESHOLD` | 及格线，默认 60 |
| `INTERVIEW_MAX_DURATION` | 面试最大时长 (秒)，默认 2700 |
| `ALIYUN_ACCESS_KEY_ID` / `ALIYUN_ACCESS_KEY_SECRET` | 阿里云 AccessKey 凭证 |
| `ALIYUN_NLS_APPKEY` | 阿里云 NLS 项目 Appkey |
| `SEARCH_API_KEY` | 联网搜索 API Key (可选) |

## 运行测试

```bash
pytest tests/ -v
```
