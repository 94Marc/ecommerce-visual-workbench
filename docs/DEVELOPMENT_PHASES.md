# Development Phases

## Phase 1 — 业务闭环

- Monorepo、容器基础设施、数据库迁移。
- 商品与 SKU。
- 原图上传和不可变版本链。
- 五平台规则框架，Temu 默认演示规则。
- 模拟生成 Worker。
- 审核、重新生成与 ZIP 导出。
- Next.js 工作台和 Konva 编辑器骨架。

退出条件：用一个商品从 ORIGINAL 走到审核通过并下载 Temu ZIP；自动化测试覆盖领域状态与原图保护。

## Phase 2 — 平台规则中心与商品视觉方案

- 规范化五平台规则层级与版本生效解析。
- 商品视觉方案固定 RuleVersion，保存七类输出数量。
- 数量确定性展开 Asset Slot，并允许语义槽位编码。
- 提供规则台账和视觉方案工作区；仍不接入 AI。

## Phase 3 — 真实生成流水线

统一 ImageGenerationProvider，接入 OpenAI 图片服务并保留测试专用 Mock；生成任务固定规则、视觉方案、槽位与引用图，支持重试、审核、规则复检和 ZIP 导出。

## Phase 3.5 — 商品真实性与质量控制

增加 STRICT/BALANCED/CREATIVE、多个 ORIGINAL 参考角度、可插拔质量 Analyzer、拒绝原因与基于审核意见的追加式重新生成。

## Phase 4 — 真实图片处理 Provider

接入 rembg、Real-ESRGAN 与独立 ComfyUI HTTP 服务；增加 Workflow Registry、统一任务路由、处理输出元数据和商品工作区处理工位。真实 Provider 未配置时明确失败，不以 mock 冒充。

## Phase 5 — 电商图片模板生产系统

增加版本化 Template/TemplateVersion、Konva 编辑器、Product/SKU 动态绑定、确定性尺寸图、APPROVED-only 图片选择、模板任务、AssetVersion 追踪和 VisualPlan 槽位模板绑定。不新增 AI Provider。

## Phase 6 — 团队化与规模化

多租户权限、配额、审计、版本发布、成本治理和高可用部署。

## 明确排除

各阶段均不默认扩张到订单、库存、采购、物流、客服、财务、广告或自动刊登；这些能力需另立产品边界。
