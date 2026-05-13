# 限时邀请码 — 功能设计

2026-05-13

## 概述

在现有 30 分钟动态轮换码基础上，新增**限时邀请码**功能。管理员可在 header 邀请码弹窗中生成带有效期和使用次数限制的独立邀请码，与旧码共存。

## 现状

- 邀请码通过 HMAC-SHA256 每 15 分钟轮换生成（+15 分钟容错 = 最多 30 分钟有效）
- 无数据库表，纯算法计算
- 管理员只能从 header 弹窗获取当前码
- 验证逻辑在 `security.py:validate_invite_code()`

## 需求

1. 两种邀请码并存：旧的 30 分钟轮换码 + 新的限时码
2. 管理员在现有 header 弹窗中生成限时码
3. 固定时长选项：30分钟 / 1小时 / 2小时 / 6小时 / 12小时 / 1天 / 3天 / 7天 / 30天
4. 次数限制选项：1次 / 3次 / 5次 / 10次 / 50次 / 不限
5. 有效期从生成时刻开始计算
6. 手机端适配

## 数据库

新增 `invite_codes` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer | 主键，自增 |
| `code` | String(32) | 邀请码，unique index |
| `max_uses` | Integer | 最大使用次数，nullable（null = 不限） |
| `use_count` | Integer | 已使用次数，默认 0 |
| `expires_at` | DateTime | 过期时间 |
| `created_by` | Integer | FK → users.id，创建者 |
| `is_active` | Boolean | 是否启用，默认 true |
| `created_at` | DateTime | 创建时间 |

### 索引

- `code` unique index
- `(code, is_active, expires_at)` 复合索引（验证查询）

## 后端

### 模型 `app/models/invite_code.py`

```python
class InviteCode(Base):
    __tablename__ = "invite_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    max_uses = Column(Integer, nullable=True)
    use_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
```

### API 路由 `app/api/v1/admin.py` (已有文件，追加)

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| `POST` | `/api/admin/invite-codes` | 生成限时码 | admin |
| `GET` | `/api/admin/invite-codes` | 列表（最多 5 条活跃的） | admin |
| `DELETE` | `/api/admin/invite-codes/{id}` | 停用码（is_active=false） | admin |

### POST 请求体

```python
class CreateInviteCodeRequest(BaseModel):
    duration_hours: float = Field(..., gt=0)  # 有效期小时数
    max_uses: int | None = None               # null = 不限
```

### 验证流程变更 `security.py:validate_invite_code()`

```
1. 先检查旧的 HMAC 轮换码 → 通过则返回
2. 不通过则查 invite_codes 表：
   - code 匹配 AND is_active = true AND expires_at > now()
   - 有 max_uses 则检查 use_count < max_uses
   → 通过则 use_count += 1，返回
3. 都不通过 → 返回 False
```

## 前端

### 弹窗布局 `AppLayout.vue`

在现有 `el-dialog` 中，上下两个区域：

**上半部分 — 动态轮换码（现有功能，样式不变）**
- 大字显示当前码
- 倒计时
- 复制 + 刷新按钮
- 提示文字

**下半部分 — 限时邀请码（新增）**

```
生成限时邀请码

有效期: [下拉选择]
次数:   [下拉选择]

[生成按钮]

--- 已生成列表 ---
每项显示: 码 | 有效期 | 次数使用情况 | 复制按钮 | 删除按钮
过期项灰显标记"已过期"
```

### 数据流

1. 管理员选择时长+次数 → 点击生成 → `POST /api/admin/invite-codes`
2. 返回码显示在列表顶部
3. 码过期后标记灰显，不自动删除
4. 管理员可手动删除（`DELETE /api/admin/invite-codes/{id}`）
5. 复制功能同现有逻辑

### 手机端适配

- 弹窗宽度 `min(380px, 90vw)`
- 整体可滚动（max-height 限制）
- 按钮触控区域 ≥ 44px
- 下拉选择使用原生 `el-select`，移动端自动适配

## 验证码生成

使用 `secrets.token_hex(6)` 生成 12 位随机十六进制码，与旧码格式一致，均转为大写。

## Alembic 迁移

新增迁移文件创建 `invite_codes` 表。

## 部署流程

同现有流程：数据库迁移 + 后端重建 + 前端重建。

## 范围排除

- 不做邀请码统计/用量分析面板
- 不做邮件/短信发送邀请码
- 不做邀请码一次性链接
- 不做批量生成
- 旧 HMAC 轮换码逻辑不做任何改动
