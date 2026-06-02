# 文档管理前端交互改进 — 功能设计

2026-06-02

## 概述

补充 DocumentUpload.vue 三个缺失的交互功能：上传后自动轮询状态、error 文档重处理、分页。

不涉及底层 RAG 架构改动，纯前端交互增强。

## 现状

| 缺失 | 影响 |
|------|------|
| 无自动轮询 | 上传后显示"处理中"不再变化，用户不知道何时就绪 |
| 无重处理按钮 | error 文档无法一键重试，只能删除重新上传 |
| 无分页 | 超过 50 个文档时无法翻页 |

## 改动

### 1. 自动轮询

- 列表中存在 `status === 'processing'` 的文档时，开启 3 秒轮询
- 所有文档 status 变为 ready/error 后停止轮询
- 用 `setInterval` + 组件卸载时 `clearInterval`
- 轮询接口: `GET /api/admin/documents/{id}`（已存在）

### 2. 重处理按钮

- error 状态的文档操作列出现"重处理"按钮（带警告图标）
- 点击调用 `POST /api/admin/documents/{id}/reprocess`
- adminService.js 新增 `reprocessDocument(id)` 函数
- 成功后显示 loading，status 变回 processing，恢复轮询

### 3. 分页

- 后端已支持 `page` / `page_size` 参数
- 前端加 `el-pagination` 组件，默认 page_size=20
- 上传或删除后重置到第一页

## 文件变更

| 操作 | 文件 |
|------|------|
| 修改 | `vue_ai_interview/src/views/admin/DocumentUpload.vue` |
| 修改 | `vue_ai_interview/src/services/adminService.js` |

## 后端不变

无新增 API，只用已有端点：

- `GET /api/admin/documents?page=1&page_size=20`
- `GET /api/admin/documents/{id}`
- `POST /api/admin/documents/{id}/reprocess`
