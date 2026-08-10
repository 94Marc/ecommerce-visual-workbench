# Platform Rules

## 统一规则结构

每条规则必须含：`platform`、`market`、`category`、`image_slot`、`rule_version`、`effective_date`、`constraints`。解析时按平台、市场、类目、槽位过滤，选择生效日期不晚于目标日期且版本最高的启用规则。

`constraints` 的标准键：

- `min_width` / `min_height` / `max_width` / `max_height`
- `aspect_ratios`
- `formats`
- `max_file_size_mb`
- `background`
- `min_count` / `max_count`
- `text_policy`、`watermark_policy`

## 平台注册表

| 平台 | code | V1 状态 | 适配策略 |
|---|---|---|---|
| Temu | `temu` | 默认种子规则与完整演示 | 严格校验主图与槽位数量 |
| Amazon | `amazon` | 框架 | 规则数据 + 命名适配器 |
| TikTok Shop | `tiktok_shop` | 框架 | 规则数据 + 市场适配器 |
| Shopee | `shopee` | 框架 | 规则数据 + 市场适配器 |
| AliExpress | `aliexpress` | 框架 | 规则数据 + 命名适配器 |

平台规则会变化，仓库中的种子数据仅用于开发演示；生产发布前必须由运营确认来源和生效日期。

