# 管理员实时监控面板 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 管理员页面实时查看所有用户在线状态和面试记录，两个 Tab 切换，REST 每 5 秒轮询刷新。

**Architecture:** 后端加 User.last_active_at 字段（deps 自动更新），session_manager 加 interview_id 列表方法，新建 admin monitor API（3 个端点）。前端新建 AdminMonitor.vue，路由 /admin/monitor，AppLayout 桌面 dropdown + 手机弹出菜单入口。

**Tech Stack:** FastAPI + SQLAlchemy async + Redis + Vue 3 + Element Plus

---

## 文件结构

| 文件 | 角色 |
|------|------|
| `FastAPI_ai_interview/app/models/user.py` | 新增 `last_active_at` 字段 |
| `FastAPI_ai_interview/app/api/deps.py` | `get_current_user` 中更新 `last_active_at` |
| `FastAPI_ai_interview/app/ws/session_manager.py` | 新增 `list_active_interview_ids()` |
| `FastAPI_ai_interview/app/api/v1/admin/monitor.py` | **新建** — 3 个监控 API 端点 |
| `FastAPI_ai_interview/app/schemas/admin.py` | 新增 monitor 相关的 Pydantic schema |
| `FastAPI_ai_interview/app/main.py` | 注册 admin_monitor_router |
| `vue_ai_interview/src/views/admin/AdminMonitor.vue` | **新建** — 监控页面 |
| `vue_ai_interview/src/router/index.js` | 新增 `/admin/monitor` 路由 |
| `vue_ai_interview/src/components/AppLayout.vue` | 桌面 dropdown + 手机弹出菜单 |
| `vue_ai_interview/src/services/adminService.js` | 新增 monitor API 调用函数 |

---

### Task 1: User 模型加 last_active_at + 生成迁移

**文件:**
- 修改: `FastAPI_ai_interview/app/models/user.py`

- [ ] **Step 1: 添加字段**

在 `updated_at` 之后（第27行后）添加：

```python
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 2: 生成 Alembic 迁移**

```bash
docker exec fastapi_ai_interview-backend-1 python3 -m alembic revision --autogenerate -m "add_last_active_at_to_users"
docker exec fastapi_ai_interview-backend-1 python3 -m alembic upgrade head
```

注意：本地开发环境下，迁移文件生成后需确认 `down_revision` 指向当前唯一头（参考 project_state.md 迁移链架构）。

- [ ] **Step 3: Commit**

```bash
git add FastAPI_ai_interview/app/models/user.py FastAPI_ai_interview/app/alembic/versions/*last_active_at*.py
git commit -m "feat: add last_active_at field to User model"
```

---

### Task 2: deps.py 中自动更新 last_active_at

**文件:**
- 修改: `FastAPI_ai_interview/app/api/deps.py`

- [ ] **Step 1: 添加 datetime import**

在第1行后添加（如果还没有）：

```python
from datetime import datetime, timezone
```

检查现有的 import — 如果没有 `datetime` 和 `timezone`，在开头加一行：
```python
from datetime import datetime, timezone
```

- [ ] **Step 2: 在 get_current_user 返回前更新 last_active_at**

在 `return user` 之前（第51行前）添加：

```python
    # Update last_active_at for online status tracking (admin monitor)
    user.last_active_at = datetime.now(timezone.utc)
    await db.commit()
```

完整变更（仅显示函数尾部）：

```python
    if user.is_disabled:
        raise UnauthorizedException(message="账号已被禁用")

    # Update last_active_at for online status tracking (admin monitor)
    user.last_active_at = datetime.now(timezone.utc)
    await db.commit()

    return user
```

- [ ] **Step 3: Commit**

```bash
git add FastAPI_ai_interview/app/api/deps.py
git commit -m "feat: auto-update last_active_at on every authenticated request"
```

---

### Task 3: session_manager 加 list_active_interview_ids()

**文件:**
- 修改: `FastAPI_ai_interview/app/ws/session_manager.py`

- [ ] **Step 1: 在 SessionManager 类中添加方法**

在 `is_available` property 之前（第172行前）添加：

```python
    async def list_active_interview_ids(self) -> list[int]:
        """Return all interview IDs that currently have active WS session state."""
        await self._ensure_connection()
        if not self.redis:
            return []
        ids = []
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match="interview:*:state", count=100
            )
            for key in keys:
                try:
                    ids.append(int(key.split(":")[1]))
                except (ValueError, IndexError):
                    pass
            if cursor == 0:
                break
        return ids
```

- [ ] **Step 2: Commit**

```bash
git add FastAPI_ai_interview/app/ws/session_manager.py
git commit -m "feat: add list_active_interview_ids() to session_manager"
```

---

### Task 4: 创建 admin monitor API 端点 + schemas

**文件:**
- 创建: `FastAPI_ai_interview/app/api/v1/admin/monitor.py`
- 修改: `FastAPI_ai_interview/app/schemas/admin.py`
- 修改: `FastAPI_ai_interview/app/main.py`

- [ ] **Step 1: 添加 Pydantic schemas**

在 `app/schemas/admin.py` 末尾追加：

```python
# ── Monitor ──

class MonitorUserItem(BaseModel):
    user_id: int
    username: str
    role: str
    is_online: bool
    last_active_at: datetime | None
    interview_count: int
    active_interview: dict | None  # {interview_id, position}


class MonitorUserListResponse(BaseModel):
    items: list[MonitorUserItem]
    total: int
    online_count: int


class MonitorInterviewItem(BaseModel):
    interview_id: int
    username: str
    position: str
    difficulty: str
    mode: str
    status: str
    current_stage: str | None
    started_at: datetime | None
    duration_seconds: int | None
    is_ws_connected: bool
    created_at: datetime


class MonitorInterviewListResponse(BaseModel):
    items: list[MonitorInterviewItem]
    total: int


class MonitorSummaryResponse(BaseModel):
    online_users: int
    total_users: int
    active_interviews: int
    total_interviews: int
```

- [ ] **Step 2: 创建 monitor.py**

```python
"""Admin real-time monitoring endpoints."""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_db
from app.models.user import User
from app.models.interview import Interview
from app.ws.session_manager import session_manager
from app.schemas.admin import (
    MonitorUserItem,
    MonitorUserListResponse,
    MonitorInterviewItem,
    MonitorInterviewListResponse,
    MonitorSummaryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/monitor", tags=["管理后台-实时监控"])

ONLINE_WINDOW_MINUTES = 2


@router.get("/users", response_model=MonitorUserListResponse)
async def list_users_for_monitor(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回所有用户及其在线状态。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)

    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    # Count interviews per user
    interview_counts = {}
    active_interviews = {}
    if users:
        user_ids = [u.id for u in users]
        count_result = await db.execute(
            select(Interview.user_id, func.count(Interview.id))
            .where(Interview.user_id.in_(user_ids))
            .group_by(Interview.user_id)
        )
        for row in count_result:
            interview_counts[row[0]] = row[1]

        active_result = await db.execute(
            select(Interview).where(
                Interview.user_id.in_(user_ids),
                Interview.status == "in_progress",
                Interview.deleted_at.is_(None),
            )
        )
        for iv in active_result.scalars().all():
            active_interviews[iv.user_id] = {
                "interview_id": iv.id,
                "position": iv.position,
            }

    items = []
    online_count = 0
    for u in users:
        is_online = u.last_active_at is not None and u.last_active_at > cutoff
        if is_online:
            online_count += 1
        items.append(MonitorUserItem(
            user_id=u.id,
            username=u.username,
            role=u.role,
            is_online=is_online,
            last_active_at=u.last_active_at,
            interview_count=interview_counts.get(u.id, 0),
            active_interview=active_interviews.get(u.id),
        ))

    return MonitorUserListResponse(
        items=items,
        total=len(items),
        online_count=online_count,
    )


@router.get("/interviews", response_model=MonitorInterviewListResponse)
async def list_interviews_for_monitor(
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回所有面试记录，在线的排最前面。"""
    page_size = min(page_size, 200)
    now = datetime.now(timezone.utc)

    # Get active WS interview IDs
    active_ids = await session_manager.list_active_interview_ids()
    active_id_set = set(active_ids) if active_ids else set()

    # Query total
    count_result = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.deleted_at.is_(None)
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Interview)
        .options(selectinload(Interview.user))
        .where(Interview.deleted_at.is_(None))
        .order_by(Interview.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    interviews = result.scalars().all()

    items = []
    for iv in interviews:
        duration = None
        if iv.started_at:
            duration = int((now - iv.started_at).total_seconds())

        items.append(MonitorInterviewItem(
            interview_id=iv.id,
            username=iv.user.username if iv.user else "未知",
            position=iv.position,
            difficulty=iv.difficulty,
            mode=iv.mode,
            status=iv.status,
            current_stage=iv.current_stage,
            started_at=iv.started_at,
            duration_seconds=duration if iv.status == "in_progress" else None,
            is_ws_connected=iv.id in active_id_set,
            created_at=iv.created_at,
        ))

    # Sort: WS-connected first
    items.sort(key=lambda x: x.is_ws_connected, reverse=True)

    return MonitorInterviewListResponse(items=items, total=total)


@router.get("/summary", response_model=MonitorSummaryResponse)
async def get_monitor_summary(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回概览统计数字。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)

    total_users_result = await db.execute(
        select(func.count()).select_from(User)
    )
    total_users = total_users_result.scalar() or 0

    online_users_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.last_active_at.isnot(None),
            User.last_active_at > cutoff,
        )
    )
    online_users = online_users_result.scalar() or 0

    total_interviews_result = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.deleted_at.is_(None)
        )
    )
    total_interviews = total_interviews_result.scalar() or 0

    active_interviews_result = await db.execute(
        select(func.count()).select_from(Interview).where(
            Interview.status == "in_progress",
            Interview.deleted_at.is_(None),
        )
    )
    active_interviews = active_interviews_result.scalar() or 0

    return MonitorSummaryResponse(
        online_users=online_users,
        total_users=total_users,
        active_interviews=active_interviews,
        total_interviews=total_interviews,
    )
```

- [ ] **Step 3: 在 main.py 中注册路由**

在 `app/main.py` 的 import 区域添加：

```python
from app.api.v1.admin.monitor import router as admin_monitor_router
```

在 `app.include_router(admin_invite_codes_router)` 之后添加：

```python
    app.include_router(admin_monitor_router)
```

完整的 import 区域可以在现有 admin router imports 后面加（大概在第16行附近）。

- [ ] **Step 4: Commit**

```bash
git add FastAPI_ai_interview/app/api/v1/admin/monitor.py FastAPI_ai_interview/app/schemas/admin.py FastAPI_ai_interview/app/main.py
git commit -m "feat: add admin monitor API endpoints (users, interviews, summary)"
```

---

### Task 5: 创建 AdminMonitor.vue 页面

**文件:**
- 创建: `vue_ai_interview/src/views/admin/AdminMonitor.vue`

- [ ] **Step 1: 创建完整的 AdminMonitor.vue**

```vue
<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../services/api.js'

const router = useRouter()

// --- State ---
const activeTab = ref('users') // 'users' | 'interviews'
const users = ref([])
const interviews = ref([])
const summary = ref({ online_users: 0, total_users: 0, active_interviews: 0, total_interviews: 0 })
const loading = ref(false)
const countdown = ref(5)

let pollTimer = null
let countdownTimer = null

// --- Polling ---
async function fetchData() {
  loading.value = true
  try {
    const [summaryRes, dataRes] = await Promise.all([
      api.get('/api/admin/monitor/summary'),
      api.get(activeTab.value === 'users'
        ? '/api/admin/monitor/users'
        : '/api/admin/monitor/interviews'
      ),
    ])
    summary.value = summaryRes.data
    if (activeTab.value === 'users') {
      users.value = dataRes.data.items || []
    } else {
      interviews.value = dataRes.data.items || []
    }
  } catch (err) {
    if (err.response?.status === 401 || err.response?.status === 403) {
      router.push('/dashboard')
    }
  } finally {
    loading.value = false
  }
}

function startPolling() {
  fetchData()
  countdown.value = 5
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) countdown.value = 5
  }, 1000)
  pollTimer = setInterval(() => {
    fetchData()
    countdown.value = 5
  }, 5000)
}

function stopPolling() {
  clearInterval(pollTimer)
  clearInterval(countdownTimer)
}

function switchTab(tab) {
  activeTab.value = tab
  fetchData()
  countdown.value = 5
}

onMounted(startPolling)
onUnmounted(stopPolling)

// --- Helpers ---
function formatDuration(seconds) {
  if (seconds == null) return '-'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}分${s}秒` : `${s}秒`
}

function formatTime(dt) {
  if (!dt) return '-'
  const d = new Date(dt)
  const now = new Date()
  const diffMs = now - d
  if (diffMs < 86400000) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return `${d.getMonth() + 1}/${d.getDate()} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

function statusLabel(status) {
  const map = { created: '待开始', in_progress: '进行中', completed: '已完成', abandoned: '已放弃' }
  return map[status] || status
}

function statusClass(status) {
  return 'status-' + status
}

const isMobile = computed(() => window.innerWidth <= 768)
</script>

<template>
  <div class="monitor-page">
    <!-- Summary Bar -->
    <div class="summary-bar">
      <div class="summary-item">
        <span class="summary-num online">{{ summary.online_users }}</span>
        <span class="summary-label">在线用户</span>
        <span class="summary-div">/ {{ summary.total_users }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-num active">{{ summary.active_interviews }}</span>
        <span class="summary-label">进行中面试</span>
        <span class="summary-div">/ {{ summary.total_interviews }}</span>
      </div>
      <div class="summary-item refresh-info">
        <span>下次刷新 {{ countdown }}s</span>
      </div>
    </div>

    <!-- Tab Switcher -->
    <div class="tab-bar">
      <button
        :class="['tab-btn', { active: activeTab === 'users' }]"
        @click="switchTab('users')"
      >用户列表</button>
      <button
        :class="['tab-btn', { active: activeTab === 'interviews' }]"
        @click="switchTab('interviews')"
      >面试记录</button>
    </div>

    <!-- Loading -->
    <div v-if="loading && !users.length && !interviews.length" class="loading-state">
      加载中...
    </div>

    <!-- Users Table -->
    <div v-if="activeTab === 'users'" class="table-wrap">
      <!-- Desktop table -->
      <table v-if="!isMobile" class="data-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>角色</th>
            <th>状态</th>
            <th>注册时间</th>
            <th>面试次数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.user_id">
            <td class="cell-user">{{ u.username }}</td>
            <td><span :class="['role-tag', u.role]">{{ u.role === 'admin' ? '管理员' : '用户' }}</span></td>
            <td>
              <span :class="['status-dot', u.is_online ? 'online' : 'offline']"></span>
              {{ u.is_online ? '在线' : '离线' }}
            </td>
            <td class="cell-time">{{ formatTime(u.created_at || u.last_active_at) }}</td>
            <td>{{ u.interview_count }}</td>
          </tr>
        </tbody>
      </table>

      <!-- Mobile cards -->
      <div v-else class="card-list">
        <div v-for="u in users" :key="u.user_id" class="data-card">
          <div class="card-row">
            <span class="card-user">{{ u.username }}</span>
            <span :class="['role-tag', u.role]">{{ u.role === 'admin' ? '管理员' : '用户' }}</span>
            <span :class="['status-dot', u.is_online ? 'online' : 'offline']"></span>
            <span :class="u.is_online ? 'text-online' : 'text-offline'">{{ u.is_online ? '在线' : '离线' }}</span>
          </div>
          <div class="card-row card-meta">
            <span>注册: {{ formatTime(u.created_at) }}</span>
            <span>面试 {{ u.interview_count }} 次</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Interviews Table -->
    <div v-if="activeTab === 'interviews'" class="table-wrap">
      <table v-if="!isMobile" class="data-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>岗位</th>
            <th>难度</th>
            <th>阶段</th>
            <th>时长</th>
            <th>连线</th>
            <th>状态</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="iv in interviews" :key="iv.interview_id">
            <td class="cell-user">{{ iv.username }}</td>
            <td>{{ iv.position }}</td>
            <td><span :class="['diff-tag', iv.difficulty]">{{ iv.difficulty }}</span></td>
            <td>{{ iv.current_stage || '-' }}</td>
            <td>{{ formatDuration(iv.duration_seconds) }}</td>
            <td>
              <span :class="['status-dot', iv.is_ws_connected ? 'online' : 'offline']"></span>
              {{ iv.is_ws_connected ? '连线中' : '离线' }}
            </td>
            <td><span :class="['status-tag', statusClass(iv.status)]">{{ statusLabel(iv.status) }}</span></td>
            <td class="cell-time">{{ formatTime(iv.created_at) }}</td>
          </tr>
        </tbody>
      </table>

      <!-- Mobile cards -->
      <div v-else class="card-list">
        <div v-for="iv in interviews" :key="iv.interview_id" class="data-card">
          <div class="card-row">
            <span class="card-user">{{ iv.username }}</span>
            <span :class="['status-tag', statusClass(iv.status)]">{{ statusLabel(iv.status) }}</span>
            <span :class="['status-dot', iv.is_ws_connected ? 'online' : 'offline']"></span>
          </div>
          <div class="card-row">
            <span>{{ iv.position }}</span>
            <span :class="['diff-tag', iv.difficulty]">{{ iv.difficulty }}</span>
          </div>
          <div class="card-row card-meta">
            <span v-if="iv.current_stage">{{ iv.current_stage }}</span>
            <span v-if="iv.duration_seconds != null">{{ formatDuration(iv.duration_seconds) }}</span>
            <span>{{ formatTime(iv.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.monitor-page {
  padding: 16px 20px;
  max-width: 1100px;
  margin: 0 auto;
}

/* Summary Bar */
.summary-bar {
  display: flex;
  gap: 24px;
  padding: 12px 16px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.summary-item { display: flex; align-items: baseline; gap: 4px; }
.summary-num { font-size: 22px; font-weight: 700; }
.summary-num.online { color: #22c55e; }
.summary-num.active { color: var(--color-accent); }
.summary-label { font-size: 12px; color: var(--color-text-secondary); }
.summary-div { font-size: 14px; color: var(--color-text-secondary); }
.refresh-info { margin-left: auto; font-size: 11px; color: var(--color-text-secondary); }

/* Tab Bar */
.tab-bar { display: flex; gap: 0; margin-bottom: 12px; }
.tab-btn {
  padding: 6px 20px;
  border: 1px solid var(--color-border);
  background: var(--color-card);
  color: var(--color-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn:first-child { border-radius: 4px 0 0 4px; }
.tab-btn:last-child { border-radius: 0 4px 4px 0; }
.tab-btn.active {
  background: var(--color-accent);
  color: #fff;
  border-color: var(--color-accent);
}

/* Data Table */
.table-wrap { overflow-x: auto; }
.data-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
}
.data-table th {
  background: var(--color-bg);
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--color-text-secondary);
  font-size: 12px;
  border-bottom: 1px solid var(--color-border);
}
.data-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text);
}
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover { background: rgba(43, 58, 103, 0.02); }

.cell-user { font-weight: 500; }
.cell-time { color: var(--color-text-secondary); font-size: 12px; }

/* Status */
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}
.status-dot.online { background: #22c55e; }
.status-dot.offline { background: #d1d5db; }

.role-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: 2px;
}
.role-tag.admin { background: rgba(217, 163, 74, 0.15); color: #b8860b; }
.role-tag.candidate { background: rgba(107, 114, 128, 0.1); color: #6b7280; }

.status-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: 2px;
}
.status-in_progress { background: rgba(43, 58, 103, 0.08); color: var(--color-accent); }
.status-completed { background: rgba(34, 197, 94, 0.08); color: #16a34a; }
.status-abandoned { background: rgba(239, 68, 68, 0.08); color: #dc2626; }
.status-created { background: rgba(107, 114, 128, 0.08); color: #6b7280; }

.diff-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: 2px;
  background: rgba(107, 114, 128, 0.08);
  color: #6b7280;
}

.text-online { color: #22c55e; font-size: 12px; }
.text-offline { color: #9ca3af; font-size: 12px; }

/* Loading */
.loading-state {
  text-align: center;
  padding: 40px;
  color: var(--color-text-secondary);
}

/* Mobile Cards */
.card-list { display: flex; flex-direction: column; gap: 8px; }
.data-card {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 10px 12px;
}
.card-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.card-row + .card-row { margin-top: 6px; }
.card-user { font-weight: 600; font-size: 14px; }
.card-meta { font-size: 11px; color: var(--color-text-secondary); gap: 12px; }

/* ── Mobile ── */
@media (max-width: 768px) {
  .monitor-page { padding: 10px 8px; }
  .summary-bar { gap: 12px; padding: 8px 12px; }
  .summary-num { font-size: 18px; }
  .refresh-info { margin-left: 0; width: 100%; }
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add vue_ai_interview/src/views/admin/AdminMonitor.vue
git commit -m "feat: create AdminMonitor page with user list and interview records tabs"
```

---

### Task 6: 添加路由 + AppLayout 导航入口

**文件:**
- 修改: `vue_ai_interview/src/router/index.js`
- 修改: `vue_ai_interview/src/components/AppLayout.vue`

- [ ] **Step 1: 添加路由**

在 `vue_ai_interview/src/router/index.js` 的 `/admin/documents` 路由之后添加：

```javascript
  {
    path: '/admin/monitor',
    name: 'AdminMonitor',
    component: () => import('../views/admin/AdminMonitor.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
```

- [ ] **Step 2: 桌面端 dropdown 加"实时监控"**

在 `AppLayout.vue` 的 dropdown 菜单中，第307行"文档管理"之后添加：

```html
              <el-dropdown-item v-if="authStore.isAdmin && !isMobile" @click="router.push('/admin/monitor')">实时监控</el-dropdown-item>
```

- [ ] **Step 3: 手机端 — 改为弹出菜单选择 admin 子页面**

修改 `goTab` 函数中 admin 的处理逻辑（第106-113行），从双项切换改为弹出 ActionSheet/菜单：

```javascript
  // Admin tab — show popup to choose sub-page
  if (tab.key === 'admin') {
    showAdminMenu.value = true
    return
  }
```

在 `adminTabSub` 定义附近（第119行后）添加：

```javascript
const showAdminMenu = ref(false)

function goAdminPage(page) {
  showAdminMenu.value = false
  if (page === 'questions') router.push('/admin/questions')
  else if (page === 'documents') router.push('/admin/documents')
  else if (page === 'monitor') router.push('/admin/monitor')
}
```

在模板底部（`</nav>` 之后）添加弹出菜单（用 Element Plus `el-dialog` 或手写 action sheet）：

```html
    <!-- Admin sub-menu (mobile) -->
    <el-dialog v-model="showAdminMenu" title="管理" width="280px" :close-on-click-modal="true" class="admin-menu-dialog">
      <div class="admin-menu-list">
        <div class="admin-menu-item" @click="goAdminPage('questions')">
          <el-icon><EditPen /></el-icon>
          <span>题库管理</span>
        </div>
        <div class="admin-menu-item" @click="goAdminPage('documents')">
          <el-icon><FolderOpened /></el-icon>
          <span>文档管理</span>
        </div>
        <div class="admin-menu-item" @click="goAdminPage('monitor')">
          <el-icon><DataAnalysis /></el-icon>
          <span>实时监控</span>
        </div>
      </div>
    </el-dialog>
```

注意：Icon 名字 `Edit`, `Folder`, `Monitor` 需要确认 Element Plus Icons 中存在。可替换为任意合适的图标。

添加样式（在 AppLayout 的 `<style scoped>` 中）：

```css
.admin-menu-list { display: flex; flex-direction: column; }
.admin-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  font-size: 15px;
  cursor: pointer;
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text);
}
.admin-menu-item:last-child { border-bottom: none; }
.admin-menu-item:active { background: var(--color-bg); }
```

- [ ] **Step 4: Commit**

```bash
git add vue_ai_interview/src/router/index.js vue_ai_interview/src/components/AppLayout.vue
git commit -m "feat: add /admin/monitor route and navigation entries for desktop and mobile"
```

---

## 验证清单

1. **后端 API**
   - [ ] `GET /api/admin/monitor/summary` 返回统计数据
   - [ ] `GET /api/admin/monitor/users` 返回所有用户 + 在线状态
   - [ ] `GET /api/admin/monitor/interviews` 返回所有面试 + WS 连接状态
   - [ ] 非 admin 访问返回 403
   - [ ] 每次请求 `get_current_user` 自动更新 `last_active_at`

2. **前端页面**
   - [ ] 桌面端 `/admin/monitor` 显示表格，两个 tab 正常切换
   - [ ] 手机端卡片布局，tab 正常切换
   - [ ] 每 5 秒自动刷新，倒计时显示正确
   - [ ] 概览 bar 显示在线用户数和进行中面试数
   - [ ] 在线用户显示绿点，离线显示灰点
   - [ ] 离开页面后轮询停止
   - [ ] 桌面端用户下拉菜单有"实时监控"入口
   - [ ] 手机端底部"管理"tab 弹出菜单有三项可选
