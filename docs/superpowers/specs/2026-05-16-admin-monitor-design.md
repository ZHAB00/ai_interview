# 管理员实时监控面板

**日期**: 2026-05-16
**范围**: 后端 API + 前端 AdminMonitor 页面，桌面端 + 手机端

## 目标

管理员能看到所有注册用户及所有面试记录，包含实时在线状态。两个 Tab 切换，REST 轮询刷新。

## 在线状态定义

- **用户在线**: `User.last_active_at` 在 2 分钟内有更新 → 🟢 在线
- **用户离线**: `User.last_active_at` 为空或超过 2 分钟 → ⚫ 离线
- **面试在线**: Redis 中存在该 `interview_id` 的 WebSocket session → 🟢 WS 连接中
- **面试离线**: Redis 中无 session，但 DB 状态仍为 `in_progress` → 进行中但断连

## 后端改动

### 1. User 模型加 `last_active_at`

`app/models/user.py`：新增字段
```python
last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

需要生成 Alembic 迁移。

### 2. Middleware 自动更新 last_active_at

`app/core/middleware.py`：在认证中间件中，对已认证请求：
```python
if current_user:
    current_user.last_active_at = datetime.now(timezone.utc)
    await db.commit()
```

注意：仅在请求结束时更新一次，避免每个中间件层都写库。用 `request.state._active_updated` 标记去重。

### 3. session_manager 加 `list_active_interview_ids()`

`app/ws/session_manager.py`：新增方法，用 Redis `SCAN` 或维护一个 SET 键：

```python
async def list_active_interview_ids(self) -> list[int]:
    """返回所有当前有活跃 WS 连接的 interview_id"""
    # 方案：SCAN interview:*:state 键
    cursor = 0
    ids = []
    while True:
        cursor, keys = await self.redis.scan(cursor, match="interview:*:state", count=100)
        for key in keys:
            ids.append(int(key.split(":")[1]))
        if cursor == 0:
            break
    return ids
```

### 4. Admin API 端点

全部在 `app/api/v1/admin/` 下，使用 `Depends(get_current_admin)`。

#### `GET /api/admin/monitor/users`

返回所有用户列表：

```json
{
  "items": [
    {
      "user_id": 1,
      "username": "pandahead",
      "role": "admin",
      "is_online": true,
      "last_active_at": "2026-05-16T10:30:00Z",
      "interview_count": 5,
      "active_interview": {"interview_id": 142, "position": "AI Agent开发工程师"}
    }
  ],
  "total": 10,
  "online_count": 3
}
```

#### `GET /api/admin/monitor/interviews`

返回所有面试记录（按创建时间倒序，在线的排前面）：

```json
{
  "items": [
    {
      "interview_id": 142,
      "username": "pandahead",
      "position": "AI Agent开发工程师",
      "difficulty": "初级",
      "mode": "full",
      "status": "in_progress",
      "current_stage": "技术面",
      "started_at": "2026-05-16T10:29:00Z",
      "duration_seconds": 180,
      "is_ws_connected": true
    }
  ],
  "total": 50
}
```

#### `GET /api/admin/monitor/summary`

返回统计数字：

```json
{
  "online_users": 3,
  "total_users": 10,
  "active_interviews": 2,
  "total_interviews": 50
}
```

## 前端改动

### 新页面：`AdminMonitor.vue`

路由：`/admin/monitor`，需管理员权限。

**布局：**
```
┌──────────────────────────────────────┐
│  🔢 在线 3 / 10 用户  进行中 2 面试  │  ← 概览 bar
├──────────────────────────────────────┤
│  [用户列表]  [面试记录]              │  ← Tab 切换
├──────────────────────────────────────┤
│  下次刷新 3s                          │  ← 倒计时
├──────────────────────────────────────┤
│  表格 / 卡片列表                      │
└──────────────────────────────────────┘
```

**Tab1 用户列表 — 桌面端表格：**

| 用户 | 角色 | 状态 | 注册时间 | 面试次数 |
|------|------|------|----------|---------|
| pandahead | admin | 🟢 在线 | 05-01 13:00 | 5 |
| testuser | candidate | ⚫ 离线 | 05-10 08:30 | 2 |

**Tab2 面试记录 — 桌面端表格：**

| 用户 | 岗位 | 难度 | 阶段 | 时长 | 连线 | 状态 | 时间 |
|------|------|------|------|------|------|------|------|
| pandahead | AI开发 | 初级 | 技术面 | 3m | 🟢 | in_progress | 10:29 |
| testuser | 产品经理 | 中级 | - | - | ⚫ | completed | 昨天 |

**手机端：** 表格变卡片，每行一条卡片，tab 保留顶部切换。

### 轮询逻辑

- 进入页面开始轮询，每 5 秒调 summary + 当前 tab 的列表 API
- 倒计时显示 "下次刷新 Xs"
- 离开页面停止轮询（`onUnmounted` 清 interval）

### 导航入口

- **桌面端**：AppLayout header 下拉菜单加 "实时监控"
- **手机端**：底部 admin tab 子菜单加 "监控"（与题库管理、文档管理同级）

## 不变的部分

- 现有 admin 页面（题库、文档、用户管理、邀请码）
- 面试 WebSocket 逻辑
- 用户认证和授权体系
- 前端路由 guard

## 不做

- WebSocket 推送（用 REST 轮询）
- 管理员介入面试（查看 only）
- 全局 WebSocket 在线追踪（用 last_active_at 推断）
- 用户登录/登出事件通知
