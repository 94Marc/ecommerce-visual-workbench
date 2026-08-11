# Ecommerce Template System

## Purpose

The template system turns verified product data and approved image assets into deterministic ecommerce artwork. It never redraws a product and never calls an AI provider.

```text
Product / SKU data + APPROVED assets + TemplateVersion
  -> template render task (provider type TEMPLATE)
  -> PNG or JPEG
  -> new REVIEW AssetVersion
  -> human review
  -> ProductVisualPlan / platform ZIP
```

## Template and TemplateVersion

`Template` is the stable library identity used by VisualPlan slots. It stores code, name, type, lifecycle status, and an optional preview asset. `TemplateStatus` is `DRAFT`, `ACTIVE`, or `ARCHIVED`.

`TemplateVersion` is append-only. Canvas dimensions, background, and `schema_json` are fixed on the version. Saving creates the next integer version; no API updates a historical version. Render records always reference the exact version used.

Supported types are `MAIN`, `DETAIL`, `DIMENSION`, `SELLING_POINT`, `PARAMETER`, `PACKAGE`, and `COMPARE`.

## Schema

Schema version `1.0` supports `IMAGE`, `TEXT`, `SHAPE`, `LINE`, `ICON`, and `GROUP`. Every layer has a stable ID, geometry, rotation, opacity, visibility, lock state, and z-index. Type-specific properties are validated before persistence.

Image bindings are limited to `{{asset.main}}`, `{{asset.cutout}}`, `{{asset.closeup}}`, and `{{asset.package}}`.

The editor uses `react-konva` for selection, movement, scaling, rotation, lock/visibility, layer order, copy/delete, and undo/redo. The API uses a deterministic Pillow renderer for the same schema.

## Data binding and dimensions

Text values come from a snapshot of Product and SKU data: product name, material, color, length, width, height, weight, SKU code, and selling points. Dimensions support `mm`, `cm`, `m`, and `inch` with deterministic conversion.

Phase 5 does not visually measure an object. Missing measurements stay empty rather than being inferred. Dimensions, weight, and parameters are never delegated to AI.

## Asset selection and truthfulness

Only non-deleted `APPROVED` AssetVersions belonging to the selected Product may be bound. Explicit bindings with any other status fail. Automatic preference is:

1. CUTOUT, then MAIN for product cutouts
2. MAIN, then CUTOUT for main imagery
3. CLOSEUP, then CUTOUT, then MAIN for closeups
4. PACKAGE, then CUTOUT, then MAIN for package imagery

The renderer never overwrites source bytes. Layout, contain/cover/manual positioning, crop, rotation, text, lines, background, icons, and auxiliary shapes are permitted. Product color, texture, shape, Logo, and packaging text may not change.

## Render pipeline

`TemplateRenderService` receives a TemplateVersion, Product, optional SKU, bindings, optional AssetSlot, and output settings. It creates a unified `GenerationJob` with `provider_type=TEMPLATE` and a matching `RENDER_*_TEMPLATE` task type.

Success creates a derived Asset or appends to the Asset assigned to a slot. Every output is a new immutable AssetVersion in `REVIEW`. Failures retain their task record and reason.

## Traceability

`TemplateRenderRecord` links Template, exact TemplateVersion, GenerationJob, output AssetVersion, Product/SKU, all source AssetVersions, the product data snapshot, and render time. An exported image can therefore be audited after product data or the active template changes.

## VisualPlan integration

`AssetSlot.template_id` binds a semantic slot such as `DIMENSION_FRONT` to `DIMENSION_BASIC_01`. A plan stores template identity for routing; each render pins the exact TemplateVersion.

## Initial templates

- `MAIN_WHITE_01`
- `DIMENSION_BASIC_01`
- `SELLING_POINT_01`
- `PARAMETER_01`
- `PACKAGE_01`
- `DETAIL_CLOSEUP_01`

They are restrained, platform-neutral starting points rather than marketing-heavy designs.
