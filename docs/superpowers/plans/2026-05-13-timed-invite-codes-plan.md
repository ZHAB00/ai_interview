# 限时邀请码 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 30 分钟 HMAC 轮换码基础上新增限时邀请码功能（数据库驱动，管理员可创建带有效期和使用次数的独立邀请码）

**Architecture:** 新增 `invite_codes` 表 + 后端 admin API（3 端点）+ 验证链路优先 HMAC 再查数据库 + 前端在现有 header 弹窗中集成

**Tech Stack:** FastAPI + SQLAlchemy async + Vue 3 + Element Plus + Alembic

---

### Task 1: 创建 InviteCode 模型

**Files:**
- Create: `FastAPI_ai_interview/app/models/invite_code.py`
- Modify: `FastAPI_ai_interview/app/models/__init__.py`

- [ ] **Step 1: 创建模型文件**

```python
"""InviteCode model — time-limited join codes managed by admins."""

import secrets

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    max_uses = Column(Integer, nullable=True)  # NULL = unlimited
    use_count = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    creator = relationship("User", lazy="selectin")

    @staticmethod
    def generate_code() -> str:
        return secrets.token_hex(6).upper()
```

- [ ] **Step 2: 注册模型到 __init__.py**

In `FastAPI_ai_interview/app/models/__init__.py`, add after the last import:

```python
from app.models.invite_code import InviteCode
```

And add `"InviteCode"` to `__all__` list.

- [ ] **Step 3: 提交**

```bash
git add FastAPI_ai_interview/app/models/invite_code.py FastAPI_ai_interview/app/models/__init__.py
git commit -m "feat: add InviteCode model for time-limited invite codes"
```

---

### Task 2: 创建 Alembic 迁移

**Files:**
- Create: `FastAPI_ai_interview/alembic/versions/<revision>_add_invite_codes_table.py`

- [ ] **Step 1: 生成迁移**

```bash
cd FastAPI_ai_interview && docker compose exec backend alembic revision --autogenerate -m "add_invite_codes_table"
```

- [ ] **Step 2: 验证迁移文件内容**

确认升级操作包含 `create_table("invite_codes", ...)` 含所有字段：`id, code(unique), max_uses, use_count, expires_at, is_active, created_by, created_at`。

- [ ] **Step 3: 运行迁移**

```bash
cd FastAPI_ai_interview && docker compose exec backend alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade ...`

- [ ] **Step 4: 提交**

```bash
git add FastAPI_ai_interview/alembic/versions/<new_revision>.py
git commit -m "feat: add invite_codes table migration"
```

---

### Task 3: 添加 InviteCode Schemas

**Files:**
- Modify: `FastAPI_ai_interview/app/schemas/admin.py`

- [ ] **Step 1: 在文件末尾追加 schemas**

```python
# ── Invite Codes ──

from datetime import datetime as _dt


class CreateInviteCodeRequest(BaseModel):
    duration_hours: float = Field(gt=0)
    max_uses: int | None = Field(default=None, ge=1)


class InviteCodeItem(BaseModel):
    id: int
    code: str
    max_uses: int | None
    use_count: int
    expires_at: _dt
    is_active: bool
    created_at: _dt


class InviteCodeListResponse(BaseModel):
    items: list[InviteCodeItem]
```

- [ ] **Step 2: 提交**

```bash
git add FastAPI_ai_interview/app/schemas/admin.py
git commit -m "feat: add invite code request/response schemas"
```

---

### Task 4: 创建 Admin Invite Code API

**Files:**
- Create: `FastAPI_ai_interview/app/api/v1/admin/invite_codes.py`
- Modify: `FastAPI_ai_interview/app/main.py`

- [ ] **Step 1: 创建 API 路由文件**

```python
"""Admin invite code management — create, list, deactivate time-limited codes."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.exceptions import NotFoundException
from app.models.invite_code import InviteCode
from app.models.user import User
from app.schemas.admin import CreateInviteCodeRequest, InviteCodeItem, InviteCodeListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/invite-codes", tags=["管理后台-邀请码"])


@router.post("", status_code=201)
async def create_invite_code(
    req: CreateInviteCodeRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """生成限时邀请码。"""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=req.duration_hours)
    invite = InviteCode(
        code=InviteCode.generate_code(),
        max_uses=req.max_uses,
        expires_at=expires_at,
        created_by=current_user.id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    logger.info(f"限时邀请码已生成: id={invite.id}, by={current_user.username}, duration={req.duration_hours}h")
    return {
        "id": invite.id,
        "code": invite.code,
        "max_uses": invite.max_uses,
        "use_count": invite.use_count,
        "expires_at": invite.expires_at.isoformat(),
        "is_active": invite.is_active,
        "created_at": invite.created_at.isoformat(),
    }


@router.get("", response_model=InviteCodeListResponse)
async def list_invite_codes(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出活跃的限时邀请码（最多 5 条）。"""
    result = await db.execute(
        select(InviteCode)
        .where(InviteCode.is_active == True)
        .order_by(InviteCode.created_at.desc())
        .limit(5)
    )
    codes = result.scalars().all()
    return {"items": [
        InviteCodeItem(
            id=c.id,
            code=c.code,
            max_uses=c.max_uses,
            use_count=c.use_count,
            expires_at=c.expires_at,
            is_active=c.is_active,
            created_at=c.created_at,
        )
        for c in codes
    ]}


@router.delete("/{invite_id}", status_code=204)
async def deactivate_invite_code(
    invite_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """停用限时邀请码（软删除）。"""
    result = await db.execute(select(InviteCode).where(InviteCode.id == invite_id))
    invite = result.scalar_one_or_none()
    if not invite:
        raise NotFoundException("邀请码不存在")
    invite.is_active = False
    await db.commit()
    logger.info(f"限时邀请码已停用: id={invite_id}, by={current_user.username}")
    return None
```

- [ ] **Step 2: 在 main.py 注册路由**

In `FastAPI_ai_interview/app/main.py`, add after the last admin router import:

```python
from app.api.v1.admin.invite_codes import router as admin_invite_codes_router
```

And add after the last `app.include_router`:

```python
app.include_router(admin_invite_codes_router)
```

- [ ] **Step 3: 提交**

```bash
git add FastAPI_ai_interview/app/api/v1/admin/invite_codes.py FastAPI_ai_interview/app/main.py
git commit -m "feat: add admin invite code CRUD API endpoints"
```

---

### Task 5: 修改验证链路 — HMAC 优先 + 数据库兜底

**Files:**
- Modify: `FastAPI_ai_interview/app/core/security.py`
- Modify: `FastAPI_ai_interview/app/api/v1/auth.py`

- [ ] **Step 1: 在 security.py 末尾添加数据库验证函数**

```python
async def validate_db_invite_code(code: str, db) -> bool:
    """Check if the code matches an active time-limited invite code in the DB.
    Increments use_count on match. Returns False if not found or expired/fully used.
    """
    from sqlalchemy import select
    from app.models.invite_code import InviteCode
    from datetime import datetime, timezone

    code = code.strip().upper()
    result = await db.execute(
        select(InviteCode).where(
            InviteCode.code == code,
            InviteCode.is_active == True,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        return False

    if invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return False

    if invite.max_uses is not None and invite.use_count >= invite.max_uses:
        return False

    invite.use_count += 1
    await db.commit()
    logger.info(f"DB邀请码使用: id={invite.id}, code={code}, use_count={invite.use_count}")
    return True
```

The `logger = logging.getLogger(__name__)` is already at the top of the file.

- [ ] **Step 2: 在 auth.py 中导入并使用**

In `FastAPI_ai_interview/app/api/v1/auth.py`, add the import after the existing security imports:

```python
from app.core.security import (
    ...
    validate_db_invite_code,  # add this
)
```

Then modify the register function, replacing the validation block (lines 74-76):

```python
    # Step 2: Validate invite code (HMAC first, then DB)
    if not validate_invite_code(req.invite_code):
        if not await validate_db_invite_code(req.invite_code, db):
            raise ValidationErrorException("邀请码不正确")
```

- [ ] **Step 3: 提交**

```bash
git add FastAPI_ai_interview/app/core/security.py FastAPI_ai_interview/app/api/v1/auth.py
git commit -m "feat: add DB-backed invite code validation chain"
```

---

### Task 6: 前端 — 扩展邀请码弹窗

**Files:**
- Modify: `vue_ai_interview/src/components/AppLayout.vue`

- [ ] **Step 1: 添加限时码相关的响应式变量和函数 (script 部分)**

在现有 `// --- Invite Code ---` 块中，紧接 `onUnmounted(() => clearInterval(countdownTimer))` 之前添加：

```js
// --- Timed Invite Codes ---
const timedCodes = ref([])
const duration = ref(2)
const maxUses = ref(5)
const generating = ref(false)

const durationOptions = [
  { label: '30分钟', value: 0.5 },
  { label: '1小时', value: 1 },
  { label: '2小时', value: 2 },
  { label: '6小时', value: 6 },
  { label: '12小时', value: 12 },
  { label: '1天', value: 24 },
  { label: '3天', value: 72 },
  { label: '7天', value: 168 },
  { label: '30天', value: 720 },
]

const maxUsesOptions = [
  { label: '1次', value: 1 },
  { label: '3次', value: 3 },
  { label: '5次', value: 5 },
  { label: '10次', value: 10 },
  { label: '50次', value: 50 },
  { label: '不限', value: 0 },
]

async function fetchTimedCodes() {
  try {
    const { data } = await api.get('/api/admin/invite-codes')
    timedCodes.value = data.items || []
  } catch { timedCodes.value = [] }
}

async function generateTimedCode() {
  generating.value = true
  try {
    await api.post('/api/admin/invite-codes', {
      duration_hours: duration.value,
      max_uses: maxUses.value || null,
    })
    ElMessage.success('邀请码已生成')
    await fetchTimedCodes()
  } catch (e) {
    ElMessage.error(e.response?.data?.error?.message || '生成失败')
  } finally {
    generating.value = false
  }
}

async function copyTimedCode(code) {
  await navigator.clipboard.writeText(code)
  ElMessage.success('邀请码已复制')
}

async function deactivateTimedCode(id) {
  try {
    await api.delete(`/api/admin/invite-codes/${id}`)
    ElMessage.success('邀请码已删除')
    await fetchTimedCodes()
  } catch (e) {
    ElMessage.error(e.response?.data?.error?.message || '删除失败')
  }
}

function isExpired(c) {
  return new Date(c.expires_at) < new Date()
}

function isExhausted(c) {
  return c.max_uses !== null && c.use_count >= c.max_uses
}

function codeStatus(c) {
  if (!c.is_active) return '已停用'
  if (isExpired(c)) return '已过期'
  if (isExhausted(c)) return '已用完'
  if (c.max_uses) return `${c.use_count}/${c.max_uses}次`
  return `${c.use_count}次使用`
}

function expiresFormat(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const m = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${m}-${day} ${h}:${min}到期`
}
```

在 `openInviteDialog()` 函数末尾追加 `fetchTimedCodes()` 调用：

```js
function openInviteDialog() {
  fetchInviteCode()
  fetchTimedCodes()
  inviteDialog.value = true
  // ... rest unchanged
```

- [ ] **Step 2: 更新模板 (template 部分)**

将现有 `<el-dialog>` 替换为：

```html
<!-- Invite Code Dialog -->
<el-dialog v-model="inviteDialog" title="内测邀请码" width="380px" :close-on-click-modal="false" @close="closeInviteDialog" class="invite-dialog">
  <div class="invite-dialog-body">
    <!-- Section 1: rotating code -->
    <div class="invite-section">
      <div class="invite-section-title">动态轮换码</div>
      <div class="invite-code-display">{{ inviteCode }}</div>
      <div class="invite-countdown">
        <span class="countdown-dot" />
        {{ countdown }}
      </div>
      <div class="invite-actions">
        <el-button type="primary" size="small" @click="copyInviteCode">复制邀请码</el-button>
        <el-button size="small" text @click="fetchInviteCode">立即刷新</el-button>
      </div>
      <p class="invite-tip">同一窗口内上一个码也有效（15分钟容错）</p>
    </div>

    <el-divider />

    <!-- Section 2: timed codes -->
    <div class="invite-section">
      <div class="invite-section-title">生成限时邀请码</div>
      <div class="timed-form">
        <div class="timed-form-item">
          <label>有效期</label>
          <el-select v-model="duration" size="small">
            <el-option v-for="o in durationOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
        <div class="timed-form-item">
          <label>次数</label>
          <el-select v-model="maxUses" size="small">
            <el-option v-for="o in maxUsesOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
        <el-button type="primary" size="small" :loading="generating" @click="generateTimedCode" class="timed-gen-btn">
          {{ generating ? '生成中...' : '生成' }}
        </el-button>
      </div>

      <!-- Timed code list -->
      <div v-if="timedCodes.length" class="timed-list">
        <div v-for="c in timedCodes" :key="c.id" class="timed-item" :class="{ 'timed-item--dead': isExpired(c) || isExhausted(c) || !c.is_active }">
          <div class="timed-code">{{ c.code }}</div>
          <div class="timed-meta">
            <span class="timed-status" :class="{ 'timed-status--dead': isExpired(c) || isExhausted(c) || !c.is_active }">{{ codeStatus(c) }}</span>
            <span class="timed-expires">{{ expiresFormat(c.expires_at) }}</span>
          </div>
          <div class="timed-item-actions">
            <el-button size="small" text @click="copyTimedCode(c.code)">复制</el-button>
            <el-button size="small" text type="danger" @click="deactivateTimedCode(c.id)">删除</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</el-dialog>
```

- [ ] **Step 3: 更新样式 (style 部分)**

在 `</style>` 之前追加：

```css
/* invite dialog — timed codes */
.invite-dialog :deep(.el-dialog__body) {
  max-height: 65vh;
  overflow-y: auto;
  padding: 16px 20px;
}

.invite-section {
  text-align: center;
}
.invite-section-title {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* timed form */
.timed-form {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.timed-form-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.timed-form-item label {
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}
.timed-gen-btn {
  flex-shrink: 0;
}

/* timed list */
.timed-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.timed-item {
  background: var(--color-bg);
  border-radius: 8px;
  padding: 10px 12px;
  text-align: left;
}
.timed-item--dead {
  opacity: 0.45;
}
.timed-code {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 3px;
  color: var(--color-accent);
  font-family: 'Courier New', monospace;
  margin-bottom: 4px;
}
.timed-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.timed-status {
  font-size: 11px;
  color: #67C23A;
}
.timed-status--dead {
  color: var(--color-text-secondary);
}
.timed-expires {
  font-size: 11px;
  color: var(--color-text-secondary);
}
.timed-item-actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
}

/* mobile dialog */
@media (max-width: 768px) {
  .invite-dialog {
    --el-dialog-width: 90vw !important;
    max-width: 380px;
  }
  .invite-dialog :deep(.el-dialog__body) {
    padding: 12px 14px;
  }
  .timed-code {
    font-size: 16px;
    letter-spacing: 2px;
  }
  .timed-form {
    gap: 6px;
  }
}
```

同时，将样式块中已有的 `.invite-code-display` 移动端字号调整也保留不变（已在 404-407 行有 `@media (max-width: 768px)` 中的适配）。

- [ ] **Step 4: 提交**

```bash
git add vue_ai_interview/src/components/AppLayout.vue
git commit -m "feat: add timed invite code UI to admin dialog"
```

---

### Task 7: 构建验证

- [ ] **Step 1: 重建后端**

```bash
cd FastAPI_ai_interview && docker compose up -d --build backend
```

- [ ] **Step 2: 运行数据库迁移**

```bash
docker compose exec backend alembic upgrade head
```

Expected: "Running upgrade ... -> ..."

- [ ] **Step 3: 构建前端**

```bash
cd vue_ai_interview && npm run build
```

Expected: 无报错，dist 生成成功。

- [ ] **Step 4: 部署前端**

```bash
sudo cp -r dist/* /var/www/ai_interview/
```

---

### Task 8: 功能验证

- [ ] **Step 1: 验证旧码仍然有效**

用管理员账号获取轮换码 → 用候选者注册验证旧码通过。

- [ ] **Step 2: 验证限时码创建和列表**

管理员打开弹窗 → 选择 1 小时 + 5 次 → 点生成 → 码出现在列表中。

- [ ] **Step 3: 验证限时码注册**

用生成的限时码注册新用户 → 注册成功 → 使用次数从 0/5 变为 1/5。

- [ ] **Step 4: 验证过期码不可用**

将 `expires_at` 手动改到过去（测试数据库）→ 验证该码注册失败。

- [ ] **Step 5: 验证耗尽码不可用**

用完 5 次后 → 验证第 6 次注册失败。

- [ ] **Step 6: 验证删除/停用**

删除限时码 → 列表不再显示 → 该码注册失败。
