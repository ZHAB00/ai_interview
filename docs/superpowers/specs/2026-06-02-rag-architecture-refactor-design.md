# RAG 架构重构 — 功能设计

2026-06-02

## 概述

重构文档知识库底层架构，解决当前三大问题：固定大小分块破坏语义连贯性、多文档逐个遍历索引导致搜索 O(N×M)、无锁无缓存不支持并发。

## 现状问题

| 问题 | 现状 | 影响 |
|------|------|------|
| 分块 | 固定 500 字 + 100 重叠，RecursiveCharacterTextSplitter | 句子拦腰截断，丢失语义 |
| 索引 | 每文档一个 FAISS 文件，search_all 逐个遍历 | 文档多时线性变慢 |
| 并发 | 无锁、无缓存、无线程池 | 同时上传+搜索可能数据竞争 |

## 目标架构

### 索引层：统一 IndexIDMap + FlatIP

```
旧: data/faiss/doc_1.faiss, doc_2.faiss, ...  (N个文件逐个搜)
新: data/faiss/unified.faiss + unified.registry.json  (单一索引一次搜)
```

- `IndexIDMap(IndexFlatIP)`: 支持 `add_with_ids(doc_id, embedding)` 和 `remove_ids(doc_id)`，document_id 直接映射到向量 ID
- 注册表 JSON: `{doc_id: [vector_ids_start, vector_ids_end], chunks: [...]}`，search 后用 doc_id 查 chunk 文本

### 分块策略：按文档类型自适应

| 文档类型 | chunk_size | overlap | 策略 |
|---------|-----------|---------|------|
| PDF | 按页边界 | 150 | 先用 pypdf 按页提取，超 1000 字的页内递归切分 |
| DOCX | 按段落/标题 | 150 | python-docx 遍历段落，检测标题样式(H1-H4)，同级标题段落聚合 |
| TXT/MD | 800 | 150 | RecursiveCharacterTextSplitter，保留换行符作为自然边界 |

**上下文头**: 每个 chunk 自动拼接 `[文档:{filename}] [章节:{heading}] {chunk_text}`

### 读写锁

- **写锁**: 全局 `asyncio.Lock`，上传/删除/重处理时持有
  - 保证 FAISS 索引 + 注册表 + 磁盘文件原子更新
- **读无锁**: FAISS `IndexFlatIP.search()` 天然线程安全
- `asyncio.to_thread` 将所有 CPU 密集操作（embed、FAISS IO）放到线程池

### 嵌入缓存

- Redis key: `emb:{md5(query)}`
- TTL: 1 小时
- 命中后跳过 sentence-transformers 推理（~50ms → ~0ms）

### 持久化

- 写入时: 锁 → FAISS `write_index` + JSON dump registry
- 启动时: 如果 `unified.faiss` 存在，加载并加载注册表
- 与旧索引兼容: 启动时发现旧的 `doc_*.faiss` 文件则自动迁移到统一索引

## 文件变更

| 操作 | 文件 |
|------|------|
| 重写 | `app/services/vector_store.py` |
| 新增 | `app/services/embedding_cache.py` |
| 修改 | `app/api/v1/admin/documents.py`（适配新接口） |
| 不变 | `app/services/rag_service.py`（接口不打破） |

## 接口兼容

- `embed_texts()`, `embed_query()` 保持不变
- `add_document()` 改为向统一索引追加
- `search_all()` 改为在统一索引搜索 + 注册表查 chunk
- `delete_document()` 改为 `remove_ids` + 清理注册表
- `chunk_text()` 改为智能分块（PDF 按页, DOCX 按标题, TXT 不变）
- 新增 `_rebuild_registry()` 启动时从旧索引迁移

## REST API 不变

对外接口 `POST /api/admin/documents`, `GET /api/admin/documents`, `DELETE /api/admin/documents/{id}` 不改变，只升级底层实现。

## 部署注意

- 首次启动会自动迁移旧的 `doc_*.faiss` 文件
- 迁移完成后 `data/faiss/` 下只剩 `unified.faiss` + `unified.registry.json`
- 旧 `doc_*.faiss` 备份到 `data/faiss/backup/`
