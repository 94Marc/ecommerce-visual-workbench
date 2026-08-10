# Product Visual Workspace — Phase 1

## 页面

- `/products/{productId}`：商品基本信息、SKU 矩阵、十类图片资产、版本轨道和原图上传。
- `/reviews`：待审核队列、大图检查、通过、拒绝和重新处理。
- API 不可用时前端使用明确标记的演示数据；连接 API 后读取真实 Product、Asset 与 AssetVersion。

## 图片状态

状态保存在 `AssetVersion.status`：

```text
DRAFT → PROCESSING → REVIEW → APPROVED
                       └────→ REJECTED → PROCESSING
```

模拟 Worker 完成处理后创建状态为 `REVIEW` 的新版本。审核通过同步为 `APPROVED`，拒绝或重新处理同步为 `REJECTED`；重新处理同时创建新任务。

## 不可变与删除语义

- ORIGINAL Asset 及其 AssetVersion 不允许更新、追加处理版本或删除。
- 图片文件内容不可原位修改；任何裁切、压缩、排版或替换都创建新的 AssetVersion 和对象键。
- Product 和派生 Asset 使用归档；派生 Version 与 Review 使用软删除。对象存储内容不因业务删除而移除。

## CRUD API

- Product：`POST/GET/PATCH/DELETE /api/v1/products`，DELETE 为归档，另有 restore。
- Asset：上传、列表、读取、修改标签、归档；十种 `asset_type` 使用统一模型。
- Version：追加处理版本、列表、读取、状态更新、软删除、读取图片内容。
- Review：创建、列表、读取、修改审核说明、软删除。审核决定通过追加记录表达。

## Phase 1 限制

本阶段不调用 AI。图片生产由确定性的模拟 Worker 完成；平台规则、版本、审核和 ZIP 导出契约保持与未来真实处理器一致。
