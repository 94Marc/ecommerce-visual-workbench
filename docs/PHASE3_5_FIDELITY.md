# Phase 3.5：商品图片真实性与质量控制

本阶段只增强现有生成、审核和资产版本流水线，不新增业务模块。

## Provider 契约

- `ImageGenerationProvider`：商品图生成。
- `BackgroundRemovalProvider`：背景移除。
- `ImageUpscaleProvider`：图片放大。
- 已连接：`OpenAIImageGenerationProvider`、`MockImageGenerationProvider`。
- 明确占位：`ComfyUIImageGenerationProvider`、`RembgBackgroundRemovalProvider`、
  `RealESRGANUpscaleProvider`。占位实现只返回 `provider_unavailable`，不会生成假结果。

## 真实性模式

- `STRICT`：MAIN、DETAIL、DIMENSION、PACKAGE、CLOSEUP 默认使用。Prompt 明确禁止改变
  商品颜色、形状、纹理、Logo、结构、比例和包装细节。
- `BALANCED`：SCENE、USAGE 默认使用。允许调整背景、人物手部、环境和辅助道具，但商品主体
  必须最大程度一致。
- `CREATIVE`：其他营销构图可显式使用，仍要求商品身份和卖点真实。

调用方可以显式覆盖默认模式；实际模式会固化到 `GenerationJob`。

## 多角度 Reference Asset

`reference_asset_version_ids` 保存本次任务实际使用的 ORIGINAL 版本。方案生成接口可以显式传入
最多 10 张参考图；未传时使用商品当前可用的 ORIGINAL 角度。OpenAI Provider 会把所有参考角度
作为 edit 输入。所有引用必须属于同一 Product，且必须是不可变 ORIGINAL 版本。

## 质量门

每个成功输出保存一条 `GenerationQualityCheck`：

- 已真实计算：`resolution`、`aspect_ratio`、`file_size`、`format`。
- 可插拔接口：`ProductSimilarityAnalyzer`、`TextRiskAnalyzer`、
  `WatermarkRiskAnalyzer`。
- 未配置 Analyzer 时结果是 `unavailable`，不是通过；`review_required` 当前始终为 true。

可测规则失败时输出仍作为新 AssetVersion 保存，但状态为 REJECTED，不能审核通过或进入 ZIP。

## 拒绝与重新生成

拒绝或要求重新生成必须提交 `RejectReason` 和 comment。重新生成任务读取：

1. 原任务的所有 reference assets；
2. 上一版实际 Prompt；
3. RejectReason；
4. 人工 comment。

系统把它们写入 `revised_prompt`。Worker 使用 revised prompt，但保留原 prompt 供追踪。新输出追加
为同一 AssetSlot 的新 AssetVersion，旧版本保持不变。

## 生成记录页面

`/generation-jobs` 展示 Provider、模式、参考角度、原始/修订 Prompt、request ID、耗时、重试、
输出版本、质量检查和审核结果。页面的追踪顺序对应真实生产链，不代表新增业务模块。
