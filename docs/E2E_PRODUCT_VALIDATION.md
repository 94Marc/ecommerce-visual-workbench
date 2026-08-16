# Phase 6：真实商品端到端验收

## 结论

当前系统可以完成真实文件上传、不可变资产追踪、确定性模板渲染、审核状态流转、Temu
规则校验和带 manifest 的 ZIP 导出机制。当前环境不能运行 rembg、Real-ESRGAN 或
ComfyUI，因此真实去背景、高清增强、场景图和使用图验收失败或阻塞。不得用 Mock
替代这些真实 Provider，当前整体结论为 **FAIL / 暂不适合完整真实生产**。

可重复执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_e2e_real_product_validation.py -v
```

该场景使用内存数据库和不可覆盖的内存对象存储，测试结束后不保留业务数据或导出包；
每次执行都会从真实 ORIGINAL 重建完整验收上下文。

## 输入素材

| 项目 | 值 |
| --- | --- |
| 用户提供文件 | `C:\Users\ASUS\Desktop\exec-8243b989-ba6d-4ea1-a692-2c40f2b3dc57.png` |
| 测试夹具 | `apps/api/tests/fixtures/gray_cleaning_cloth_original.png` |
| 格式 | PNG（由 Pillow 解码识别，不信任上传声明） |
| 尺寸 | 1254 × 1254 px |
| 文件大小 | 2,454,772 bytes |
| SHA-256 | `813d14ad50adeca43fa818c91fe9691825b5364a0340af35e23d9e62f816f7bc` |

重要警告：原图同时包含灰色、粉色和浅色清洁布，而商品资料声明 `color=Gray`。
这不是纯灰色单品素材，正式生产前必须由人工确认商品范围，不能默认另外两种颜色也属于
该 SKU。

## 商品资料

| 字段 | 值 |
| --- | --- |
| Product | Gray Cleaning Cloth |
| 中文备注 | 灰色清洁布（保存在测试 SKU attributes） |
| SKU | TEST-CLOTH-001 |
| Category | cleaning-cloth |
| Color | Gray |
| Size | 30 cm × 30 cm |
| Material | 未填写；没有可靠来源，因此保持 `null` |
| Selling point 1 | `DEMO: 30 cm × 30 cm size display` |
| Selling point 2 | `DEMO: cleaning-cloth visual workflow validation` |
| Packaging | 无真实来源 |

所有卖点均明确标记为 DEMO，不代表真实商品事实。尺寸从 Product 数据绑定，未交给 AI
自由生成。针对扁平清洁布，验收场景为尺寸图和参数图追加了模板新版本，将平面尺寸显示为
`length × width`，没有覆盖 Demo 模板的历史版本，也没有虚构第三维度、重量或材质。

## 执行记录

| 步骤 | 输入 | Provider / 模式 | 输出 | 耗时记录 | 审核 / 结果 |
| --- | --- | --- | --- | --- | --- |
| Upload | 用户提供 PNG | API + Pillow | ORIGINAL v1 | API 未持久化请求耗时 | PASS；保存 hash、尺寸、MIME、大小、created_at |
| Background Removal | ORIGINAL v1 | rembg | 无 | Provider 预检阶段终止，无处理耗时 | FAIL：`provider_unavailable` |
| Upscale | ORIGINAL v1 | Real-ESRGAN / CONSERVATIVE | 无 | Provider 预检阶段终止，无处理耗时 | FAIL：`provider_unavailable` |
| 测试前置源 | ORIGINAL v1 的原字节副本 | 非 Provider；明确标注测试前置 | APPROVED CUTOUT | 不作为真实处理能力计时 | 仅用于验证下游；**不是 rembg 输出** |
| Main Template | 测试前置 CUTOUT + 商品资料 | TEMPLATE / STRICT / MAIN_WHITE_01 | MAIN AssetVersion | `GenerationJob.duration_ms` | REVIEW → 自动化验收记录 APPROVED；规则 PASS |
| Dimension Template | 测试前置 CUTOUT + 30 cm × 30 cm | TEMPLATE / STRICT / DIMENSION_BASIC_01 新版本 | DIMENSION AssetVersion | `GenerationJob.duration_ms` | REVIEW → 自动化验收记录 APPROVED；规则 PASS |
| Selling Point Template | 测试前置 CUTOUT + DEMO 卖点 | TEMPLATE / STRICT / SELLING_POINT_01 | DETAIL AssetVersion | `GenerationJob.duration_ms` | REVIEW → 自动化验收记录 APPROVED；规则 PASS |
| Parameter Template | 测试前置 CUTOUT + Product/SKU 快照 | TEMPLATE / STRICT / PARAMETER_01 新版本 | DETAIL AssetVersion | `GenerationJob.duration_ms` | REVIEW → 自动化验收记录 APPROVED；规则 PASS |
| Detail crop | 测试前置 CUTOUT | TEMPLATE / STRICT / DETAIL_CLOSEUP_01 | DETAIL AssetVersion | `GenerationJob.duration_ms` | REVIEW → 自动化验收记录 APPROVED；规则 PASS；没有 AI 纹理重绘 |
| Scene Generation | ORIGINAL / APPROVED CUTOUT | ComfyUI / BALANCED | 无 | Provider 预检阶段终止，无处理耗时 | FAIL：`provider_unavailable` |
| Usage Generation | ORIGINAL / APPROVED CUTOUT | ComfyUI / BALANCED | 无 | Provider 预检阶段终止，无处理耗时 | FAIL：`provider_unavailable` |
| Package Template | 无 APPROVED PACKAGE | TEMPLATE / STRICT / PACKAGE_01 | 无 | 绑定校验阶段终止 | FAIL：`MISSING_SOURCE`；没有生成虚构包装 |
| Review | 5 个模板输出 | 审核 API | 5 个测试态 APPROVED AssetVersion | 审核记录时间戳 | 机制 PASS；自动测试不冒充人工视觉结论 |
| Temu Rule Check | MAIN、DETAIL、DIMENSION 输出 | Rule Engine | 每个任务的 validation_result | 包含在模板任务耗时内 | 已配置项 PASS；SCENE/USAGE=`RULE_NOT_CONFIGURED` |
| ZIP Export | APPROVED 且规则 PASS 的 5 个输出 | ExportService | ZIP + manifest.json | 当前模型未持久化导出耗时 | PASS；未导出失败、缺源或未配置规则的槽位 |

模板任务的实际毫秒值随机器而变，由 `GenerationJob.duration_ms` 持久化；测试要求该任务完成、
规则通过、结果从 REVIEW 经测试审核记录批准，并校验输出 AssetVersion 与源版本的追踪关系。
这只验证状态机和导出门禁；由于原图包含多色商品，自动记录不得当作真实人工视觉批准。Provider
不可用时没有伪造一个看似成功的 duration 或 request ID。

## AssetVersion 与真实性保护

- ORIGINAL 只有一个版本；修改标签、改变状态、追加处理版本和删除均返回冲突。
- 上传时通过真实字节解码取得 PNG、1254 × 1254，并保存原文件 SHA-256 和文件大小。
- 处理和模板渲染全部创建新的 AssetVersion，保存 `source_version_id`。
- 模板渲染只做排版、缩放、裁剪、文字和尺寸线，不重绘商品。
- PACKAGE 模板只接受 APPROVED PACKAGE，不再回退到 CUTOUT 或 MAIN。
- 测试结束再次校验 ORIGINAL 的对象字节和 hash 均未变化。

## 人工 Fidelity Checklist

当前没有可用的真实 SCENE / USAGE AI 输出，因此不能声称自动或人工相似度已通过。

| 检查项 | SCENE | USAGE | 说明 |
| --- | --- | --- | --- |
| COLOR_MATCH | NOT_APPLICABLE | NOT_APPLICABLE | 无生成结果 |
| SHAPE_MATCH | NOT_APPLICABLE | NOT_APPLICABLE | 无生成结果 |
| TEXTURE_MATCH | NOT_APPLICABLE | NOT_APPLICABLE | 无生成结果 |
| EDGE_MATCH | NOT_APPLICABLE | NOT_APPLICABLE | 无生成结果 |
| STRUCTURE_MATCH | NOT_APPLICABLE | NOT_APPLICABLE | 无生成结果 |
| USAGE_REALISTIC | NOT_APPLICABLE | NOT_APPLICABLE | 无生成结果 |
| NO_EXTRA_PRODUCT_FEATURES | NOT_APPLICABLE | NOT_APPLICABLE | 无生成结果 |

未来真实 Provider 产生输出后，审核员必须逐项选择 PASS、FAIL 或 NOT_APPLICABLE；系统当前
没有可靠的自动视觉相似度模型，不能自动替代这一步。

## Temu VisualPlan 与规则结果

验收计划包含：MAIN × 1、DETAIL × 3、DIMENSION × 1、SCENE × 1、USAGE × 1、
PACKAGE × 1。测试只配置真实可验证的 MAIN、DETAIL 和 DIMENSION 规则：最小
1500 × 1500、1:1、PNG、最大 10 MiB、禁止水印；MAIN 禁止文字，DETAIL 和
DIMENSION 允许模板文字。

| 槽位 | 结果 |
| --- | --- |
| MAIN_01 | PASS |
| DETAIL_SELLING_POINT_01 | PASS |
| DETAIL_PARAMETER_01 | PASS |
| DETAIL_CLOSEUP_01 | PASS |
| DIMENSION_FRONT | PASS |
| SCENE_01 | RULE_NOT_CONFIGURED |
| USAGE_HOME | RULE_NOT_CONFIGURED |
| PACKAGE_01 | MISSING_SOURCE |

规则缺失不会默认通过。PACKAGE 即使未来配置了规则，在真实包装素材缺失时仍必须保持
`MISSING_SOURCE` 或明确的 `DEMO_ONLY`，不得作为真实包装事实导出。

## ZIP 结构与 manifest

ZIP 固定建立以下目录，即使某个目录没有合格素材：

```text
TEST-CLOTH-001/
├── main/
├── detail/
├── dimension/
├── scene/
├── usage/
└── package/
```

`manifest.json` schema version 为 2.0。每个导出文件记录 Product、SKU、平台、市场、
Asset ID、AssetVersion ID、AssetType、VisualPlan、AssetSlot、模板/Provider、审核状态、
规则结果和 SHA-256。`missing_slots` 明确记录 SCENE、USAGE 和 PACKAGE 未进入导出的原因。

## Pass / Fail 总结

| 验收项 | 状态 | 说明 |
| --- | --- | --- |
| Upload | PASS | 真实 PNG 上传及元数据、hash、不可变校验通过 |
| Background Removal | FAIL | rembg 未安装/未启用，`provider_unavailable` |
| Upscale | FAIL | Real-ESRGAN 未安装/未启用，`provider_unavailable` |
| Main Template | PASS（下游测试） | 使用明确标注的测试前置 CUTOUT，不代表 rembg 已通过 |
| Dimension Template | PASS（下游测试） | 数值来自 Product；模板追加版本适配二维商品 |
| Selling Point Template | PASS（DEMO） | 卖点全部带 DEMO 标记 |
| Parameter Template | PASS（受限） | 未显示缺失的材质、重量或第三维度 |
| Scene Generation | FAIL | ComfyUI 未配置，`provider_unavailable` |
| Usage Generation | FAIL | ComfyUI 未配置，`provider_unavailable` |
| Detail | PASS（下游测试） | 真实源图 crop/template，无 AI 重绘 |
| Package | FAIL | 无真实包装素材，`MISSING_SOURCE` |
| Review | PARTIAL | 状态流转与门禁 PASS；尚未完成真实人工视觉批准 |
| Platform Rule Check | PARTIAL | 已配置 5 个输出 PASS；SCENE/USAGE 规则缺失 |
| ZIP Export | PASS（受限） | 只含 APPROVED 且规则 PASS 的 5 个模板输出 |

## 发现的问题与上线条件

1. 当前环境缺少 rembg、ONNX Runtime、Real-ESRGAN 可执行文件和 ComfyUI 配置。
2. 原图包含多种颜色，与 `Gray` 单 SKU 声明有范围冲突。
3. 没有真实包装素材。
4. Temu SCENE 和 USAGE 规则未配置。
5. 当前未验证真实 AI 场景/使用图的商品保真度和手部自然度。
6. 请求上传耗时和 ZIP 导出耗时尚未作为业务字段持久化；生成任务耗时已持久化。
7. E2E 为验证 ZIP 门禁写入了明确标注的自动化 APPROVED 记录；它不等同于人工视觉验收。

在真实 Provider 安装并成功运行、补齐平台规则、提供 SKU 范围清晰的商品图和真实包装素材，
并完成人工 Fidelity Checklist 前，本系统不应被判定为完整真实生产可用。

## Phase 7.6：Scene Placement Validator（2026-08-16）

`product_scene_v2` 保留“AI 仅生成环境，真实 CUTOUT 进行确定性合成”的架构。验证器使用
normalized anchor polygon 约束商品投影，记录承托面覆盖率、外溢率、画面面积占比、透视矩阵、
表面角度和 Alpha 派生接触阴影参数。它不修改商品 RGB，也不使用视觉模型伪装物理测量。

| 候选 | Anchor | inside ratio | overflow ratio | area ratio | 自动验证 | 人工结论 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| A / 右侧台面 | `COUNTERTOP_RIGHT_EDGE` | 0.146527 | 0.853473 | 0.013720 | `PLACEMENT_INVALID`, `PLACEMENT_OVERFLOW` | REJECTED |
| B / 中间主台面 | `COUNTERTOP_MAIN` | 1.000000 | 0.000000 | 0.012546 | VALID；`PLACEMENT_SCALE_WARNING` | APPROVED_FOR_SMOKE_TEST |

面积范围 `0.05–0.18` 仅为 countertop smoke-test 视觉建议。B 的面积警告不等于真实物理尺寸
失败；测试尺寸来自 `DEMO_TEST_DATA`，因此 B 不得升级为生产级 APPROVED。A 的自动拦截来自
承托面覆盖不足；人工审核另记录 `PRODUCT_PLACEMENT_UNREALISTIC`、
`PERSPECTIVE_UNREALISTIC` 和 `SHADOW_UNREALISTIC`。

结论：**ARCHITECTURE_PASS** — “AI generates environment; deterministic pipeline preserves and
places real product pixels.” 本轮没有生成新 AI 背景，也没有执行 USAGE。
