export const templateTypes = [
  "MAIN",
  "DETAIL",
  "DIMENSION",
  "SELLING_POINT",
  "PARAMETER",
  "PACKAGE",
  "COMPARE",
] as const;

export const layerTypes = ["IMAGE", "TEXT", "SHAPE", "LINE", "ICON", "GROUP"] as const;
export const dimensionUnits = ["mm", "cm", "m", "inch"] as const;

export type TemplateType = (typeof templateTypes)[number];
export type TemplateStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";
export type LayerType = (typeof layerTypes)[number];
export type DimensionUnit = (typeof dimensionUnits)[number];
export type ImageFit = "contain" | "cover" | "manual";

export type TemplateLayer = {
  id: string;
  type: LayerType;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  opacity: number;
  visible: boolean;
  locked: boolean;
  zIndex: number;
  text?: string;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: "normal" | "medium" | "semibold" | "bold";
  align?: "left" | "center" | "right";
  lineHeight?: number;
  fill?: string;
  stroke?: string;
  strokeWidth?: number;
  assetSource?: "{{asset.main}}" | "{{asset.cutout}}" | "{{asset.closeup}}" | "{{asset.package}}";
  fit?: ImageFit;
  crop?: Record<string, number>;
  cornerRadius?: number;
  points?: number[];
  dash?: number[];
  arrowStart?: boolean;
  arrowEnd?: boolean;
  icon?: string;
  children?: TemplateLayer[];
};

export type TemplateDocument = {
  schemaVersion: "1.0";
  layers: TemplateLayer[];
  metadata?: Record<string, unknown>;
};

export type TemplateVersion = {
  id: string;
  template_id: string;
  version: number;
  canvas_width: number;
  canvas_height: number;
  background: {color?: string; [key: string]: unknown};
  schema_json: TemplateDocument;
  created_at: string;
  updated_at: string;
};

export type EcommerceTemplate = {
  id: string;
  name: string;
  code: string;
  template_type: TemplateType;
  status: TemplateStatus;
  preview_asset_id: string | null;
  versions: TemplateVersion[];
  latest_version: TemplateVersion | null;
  created_at: string;
  updated_at: string;
};

export type TemplatePreviewData = {
  product: Record<string, string | number | null | undefined>;
  sku: Record<string, string | number | null | undefined>;
  selling_point_1?: string;
  selling_point_2?: string;
  selling_point_3?: string;
  assets?: Partial<Record<"main" | "cutout" | "closeup" | "package", string>>;
};

const unitToMillimetres: Record<DimensionUnit, number> = {
  mm: 1,
  cm: 10,
  m: 1000,
  inch: 25.4,
};

export function formatDimension(
  value: number | string,
  sourceUnit: DimensionUnit,
  targetUnit: DimensionUnit = sourceUnit,
) {
  const converted = (Number(value) * unitToMillimetres[sourceUnit]) / unitToMillimetres[targetUnit];
  return `${Number(converted.toFixed(2))} ${targetUnit}`;
}

export function resolveBinding(text: string, data: TemplatePreviewData) {
  return text.replace(/\{\{([a-zA-Z0-9_.]+)\}\}/g, (_, path: string) => {
    const value = path.split(".").reduce<unknown>((current, key) => {
      if (!current || typeof current !== "object") return undefined;
      return (current as Record<string, unknown>)[key];
    }, data);
    return value === undefined || value === null ? "" : String(value);
  });
}

export function previewLayer(layer: TemplateLayer, data: TemplatePreviewData): TemplateLayer {
  return {
    ...layer,
    text: layer.text ? resolveBinding(layer.text, data) : layer.text,
    children: layer.children?.map((child) => previewLayer(child, data)),
  };
}

export function previewDocument(document: TemplateDocument, data: TemplatePreviewData) {
  return {...document, layers: document.layers.map((layer) => previewLayer(layer, data))};
}

export function assetBindingUrl(layer: TemplateLayer, data: TemplatePreviewData) {
  const key = layer.assetSource?.match(/^\{\{asset\.(main|cutout|closeup|package)\}\}$/)?.[1] as
    | "main"
    | "cutout"
    | "closeup"
    | "package"
    | undefined;
  return key ? data.assets?.[key] : undefined;
}

export const imageSlots = [
  {code: "MAIN", label: "主图", width: 1600, height: 1600, safeArea: 0.08},
  {code: "DETAIL", label: "详情图", width: 1600, height: 1600, safeArea: 0.06},
  {code: "DIMENSION", label: "尺寸图", width: 1600, height: 1600, safeArea: 0.08},
  {code: "SCENE", label: "场景图", width: 1600, height: 1600, safeArea: 0.04},
  {code: "USAGE", label: "使用图", width: 1600, height: 1600, safeArea: 0.06},
  {code: "PACKAGE", label: "包装图", width: 1600, height: 1600, safeArea: 0.08},
  {code: "CLOSEUP", label: "细节图", width: 1600, height: 1600, safeArea: 0.06},
  {code: "COMPARE", label: "对比图", width: 1600, height: 1600, safeArea: 0.08},
] as const;

export type ImageSlotCode = (typeof imageSlots)[number]["code"];

export function findTemplate(code: ImageSlotCode) {
  return imageSlots.find((slot) => slot.code === code) ?? imageSlots[0];
}
