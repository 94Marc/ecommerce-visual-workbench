# PRD V1 — 跨境电商视觉生产工作台

## 1. 背景与目标

跨境卖家通常从供应商处获得质量、尺寸、背景和命名不统一的图片。V1 将这些素材转换为按平台和图片槽位组织、可审核、可追溯、可导出的上架素材包。首要平台是 Temu，同时用相同领域模型承载 Amazon、TikTok Shop、Shopee 与 AliExpress。

## 2. 用户与核心任务

- 运营：维护商品、SKU 与属性，上传原始素材，发起生产任务。
- 设计/审核：查看版本链、检查规则结果，通过、拒绝或要求重新生成。
- 负责人：按目标平台导出已通过审核的素材 ZIP，并查看 manifest。

## 3. V1 用户流程

1. 创建 Product 与至少一个 SKU。
2. 上传 ORIGINAL 资产；系统创建不可变的首个 AssetVersion。
3. 选择平台、市场、类目和图片槽位，系统解析当前有效规则。
4. 创建生成任务；模拟 Worker 创建派生 Asset 与 AssetVersion。
5. 审核派生版本：通过、拒绝或重新生成。
6. 将通过审核且符合规则的素材导出为 ZIP。

## 4. 功能范围

### 商品中心

商品字段：名称、分类、材质、颜色、尺寸、重量、卖点。SKU 支持独立编码和属性覆盖。

### 图片资产

类型：`ORIGINAL`、`CUTOUT`、`MAIN`、`DETAIL`、`DIMENSION`、`SCENE`、`USAGE`、`PACKAGE`、`CLOSEUP`、`COMPARE`。原图永久保存；处理只追加版本。

### 规则与生产

规则按 platform、market、category、image_slot、rule_version、effective_date 定位。任务状态为 pending、processing、completed、failed。

### 审核与导出

审核动作为通过、拒绝、重新生成。导出只打包通过版本，并附带机器可读 `manifest.json`。

## 5. 非目标

订单、库存、采购、物流、客服、财务、广告、自动刊登均不在 V1。

## 6. 验收指标

- 原始版本不存在更新/覆盖 API。
- 相同规则查询在同一生效日得到确定性结果。
- 任务与审核状态转换由领域服务校验。
- ZIP 内文件与 manifest 一一对应。
- Temu 全流程可演示；其他四个平台能注册、存储规则并扩展适配器。

