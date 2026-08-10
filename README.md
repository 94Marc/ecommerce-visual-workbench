# ecommerce-visual-workbench

跨境电商 AI 商品视觉生产工作台。输入供应商原始商品素材，按平台规则组织为主图、详情图、尺寸图、场景图、使用图、包装图、细节图、对比图，并经过审核后导出平台素材 ZIP。

第一阶段不接真实 AI 模型，生成任务由模拟 Worker 产出可审核的占位版本，先验证完整业务闭环。

## Workspace

```text
apps/       web (Next.js) 与 api (FastAPI)
services/   ai-worker、image-worker、rule-engine
packages/   ui、editor、templates
platforms/  temu、amazon、tiktok-shop、shopee、aliexpress
infra/      docker、postgres、redis、minio
docs/       产品、架构、数据、平台规则与阶段计划
```

## Quick start

1. 复制 `.env.example` 为 `.env`。
2. 运行 `docker compose -f infra/docker/compose.yaml up -d`。
3. 后端：`python -m pip install -e ".[dev]"`，然后 `uvicorn app.main:app --app-dir apps/api --reload`。
4. 前端：`npm install`，然后 `npm run dev --workspace @ecommerce-visual-workbench/web`。
5. 打开 `http://localhost:3000`，API 文档位于 `http://localhost:8000/docs`。

## Phase 1 boundaries

包含商品中心、不可变图片资产、平台规则、模拟生成任务、审核和 ZIP 导出。不包含订单、库存、采购、物流、客服、财务、广告和自动刊登。

详细设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与 [docs/DATA_MODEL.md](docs/DATA_MODEL.md)。

