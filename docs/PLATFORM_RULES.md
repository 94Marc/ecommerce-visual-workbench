# Platform Rules

## 统一规则结构

规则采用 Platform → PlatformMarket → PlatformCategory → PlatformRule → RuleVersion。扁平 API 命令仍接收 `platform`、`market`、`category`、`image_slot`、`image_type`、`version` 与 `effective_date`，服务会自动归入规范化层级。解析时先按精确市场/类目优先于 `*` 通配，再选择生效日期不晚于目标日期且语义版本最高的启用 RuleVersion。

RuleVersion 的标准字段：

- `min_width` / `min_height`
- `ratio`
- `max_size`（字节）
- `text_allowed` / `watermark_allowed`
- `extra_constraints`（格式、背景等扩展策略）

## 平台注册表

| 平台 | code | V1 状态 | 适配策略 |
|---|---|---|---|
| Temu | `temu` | 默认种子规则与完整演示 | 严格校验主图与槽位数量 |
| Amazon | `amazon` | 框架 | 规则数据 + 命名适配器 |
| TikTok Shop | `tiktok_shop` | 框架 | 规则数据 + 市场适配器 |
| Shopee | `shopee` | 框架 | 规则数据 + 市场适配器 |
| AliExpress | `aliexpress` | 框架 | 规则数据 + 命名适配器 |

平台规则会变化，仓库中的种子数据仅用于开发演示；生产发布前必须由运营确认来源和生效日期。
