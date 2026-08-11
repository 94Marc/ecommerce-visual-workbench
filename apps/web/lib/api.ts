export const assetTypes = [
  "ORIGINAL",
  "CUTOUT",
  "MAIN",
  "DETAIL",
  "DIMENSION",
  "SCENE",
  "USAGE",
  "PACKAGE",
  "CLOSEUP",
  "COMPARE",
] as const;

export const assetStatuses = [
  "DRAFT",
  "PROCESSING",
  "REVIEW",
  "APPROVED",
  "REJECTED",
] as const;

export type AssetType = (typeof assetTypes)[number];
export type AssetStatus = (typeof assetStatuses)[number];

export type Product = {
  id: string;
  name: string;
  category: string;
  material: string | null;
  color: string | null;
  dimensions?: Record<string, string | number | null>;
  weight_value?: string | number | null;
  weight_unit?: string | null;
  selling_points: string[];
  is_archived?: boolean;
  skus: {id: string; code: string; attributes?: Record<string, unknown>}[];
};

export type AssetVersion = {
  id: string;
  asset_id: string;
  version_number: number;
  object_key: string;
  original_filename: string;
  mime_type: string;
  byte_size: number;
  width: number | null;
  height: number | null;
  checksum_sha256: string;
  source_version_id: string | null;
  status: AssetStatus;
  is_deleted: boolean;
  created_at: string;
};

export type Asset = {
  id: string;
  product_id: string;
  sku_id: string | null;
  asset_type: AssetType;
  label: string | null;
  is_archived: boolean;
  versions: AssetVersion[];
  created_at: string;
};

export type GenerationJob = {
  id: string;
  platform: string;
  image_slot: string;
  status: "pending" | "processing" | "completed" | "failed";
  generation_mode?: "STRICT" | "BALANCED" | "CREATIVE";
  reference_asset_version_ids?: string[];
  provider?: string;
  provider_model?: string | null;
  prompt?: string;
  revised_prompt?: string | null;
  provider_request_id?: string | null;
  duration_ms?: number | null;
  retry_count?: number;
  attempt_count?: number;
  output_version_id?: string | null;
  quality_check?: GenerationQualityCheck | null;
  review_result?: {
    decision: string;
    reason: string | null;
    comment: string | null;
    reviewer: string;
    created_at: string;
  } | null;
  created_at: string;
};

export type QualityResult = {
  status: "passed" | "failed" | "unavailable";
  actual?: unknown;
  expected?: unknown;
  score?: number;
  risk?: string;
  details?: string;
};

export type GenerationQualityCheck = {
  product_similarity: QualityResult;
  resolution: QualityResult;
  aspect_ratio: QualityResult;
  file_size: QualityResult;
  format: QualityResult;
  text_risk: QualityResult;
  watermark_risk: QualityResult;
  review_required: boolean;
};

export const rejectReasons = [
  "PRODUCT_CHANGED", "WRONG_COLOR", "WRONG_TEXTURE", "WRONG_SHAPE",
  "UNREALISTIC_USAGE", "AI_ARTIFACT", "TEXT_ERROR", "SIZE_ERROR",
  "PACKAGING_ERROR", "OTHER",
] as const;
export type RejectReason = (typeof rejectReasons)[number];

export const platformCodes = ["temu", "amazon", "tiktok_shop", "shopee", "aliexpress"] as const;
export type PlatformCode = (typeof platformCodes)[number];
export type Platform = {id: string; code: PlatformCode; name: string; enabled: boolean};
export type PlatformRuleVersion = {
  id: string; platform_rule_id: string; platform: PlatformCode; market: string; category: string;
  image_slot: string; image_type: string; version: string; rule_version: string; effective_date: string;
  min_width: number | null; min_height: number | null; ratio: string | null; max_size: number | null;
  text_allowed: boolean; watermark_allowed: boolean; enabled: boolean;
};
export type AssetSlot = {id: string; code: string; image_type: string; position: number; label: string | null};
export type ProductVisualPlan = {
  id: string; product_id: string; platform_id: string; rule_version_id: string; name: string;
  market: string; category: string; requested_outputs: Record<string, number>; slots: AssetSlot[]; created_at: string;
};

export const demoPlatforms: Platform[] = [
  {id: "platform-temu", code: "temu", name: "Temu", enabled: true},
  {id: "platform-amazon", code: "amazon", name: "Amazon", enabled: true},
  {id: "platform-tiktok", code: "tiktok_shop", name: "TikTok Shop", enabled: true},
  {id: "platform-shopee", code: "shopee", name: "Shopee", enabled: true},
  {id: "platform-aliexpress", code: "aliexpress", name: "AliExpress", enabled: true},
];
export const demoRules: PlatformRuleVersion[] = demoPlatforms.flatMap((platform, platformIndex) =>
  ["MAIN", "DETAIL", "DIMENSION"].map((imageSlot, slotIndex) => ({
    id: `rule-${platform.code}-${imageSlot.toLowerCase()}`, platform_rule_id: `definition-${platform.code}-${imageSlot.toLowerCase()}`,
    platform: platform.code, market: platform.code === "temu" ? "US" : "*", category: "*",
    image_slot: imageSlot, image_type: imageSlot, version: platform.code === "temu" ? "2.1.0" : "1.0.0",
    rule_version: platform.code === "temu" ? "2.1.0" : "1.0.0", effective_date: `2026-0${(platformIndex % 5) + 1}-01`,
    min_width: imageSlot === "DETAIL" ? 1200 : 1600, min_height: imageSlot === "DETAIL" ? 1500 : 1600,
    ratio: imageSlot === "DETAIL" ? "4:5" : "1:1", max_size: (5 + slotIndex) * 1024 * 1024,
    text_allowed: imageSlot !== "MAIN", watermark_allowed: false, enabled: true,
  })),
);
export const demoVisualPlans: ProductVisualPlan[] = [{
  id: "plan-temu-launch", product_id: "demo-kettle", platform_id: "platform-temu", rule_version_id: "rule-temu-main",
  name: "Temu US 首发视觉方案", market: "US", category: "旅行小家电",
  requested_outputs: {MAIN: 5, DETAIL: 6, DIMENSION: 2, SCENE: 3, USAGE: 2, PACKAGE: 1, CLOSEUP: 2},
  slots: [{id: "detail-feature", code: "DETAIL_FEATURE_01", image_type: "DETAIL", position: 1, label: "核心卖点"},
    {id: "dimension-front", code: "DIMENSION_FRONT", image_type: "DIMENSION", position: 2, label: "正面尺寸"},
    {id: "usage-home", code: "USAGE_HOME", image_type: "USAGE", position: 3, label: "居家使用"}],
  created_at: "2026-08-10T10:00:00Z",
}];

export const demoProducts: Product[] = [
  {
    id: "demo-kettle",
    name: "折叠旅行电热水壶",
    category: "小家电 · 旅行用品",
    material: "食品级硅胶 / 304 不锈钢",
    color: "鼠尾草绿",
    dimensions: {length: 18, width: 13, height: 10, unit: "cm"},
    weight_value: 0.72,
    weight_unit: "kg",
    selling_points: ["双电压", "折叠收纳", "防干烧"],
    skus: [
      {id: "demo-sku", code: "KETTLE-SAGE-EU", attributes: {插头: "EU", 容量: "600ml"}},
      {id: "demo-sku-us", code: "KETTLE-SAGE-US", attributes: {插头: "US", 容量: "600ml"}},
    ],
  },
  {
    id: "demo-cubes",
    name: "轻量旅行收纳袋 6 件套",
    category: "箱包 · 收纳",
    material: "防泼水涤纶",
    color: "雾蓝",
    selling_points: ["六种尺寸", "透气网面"],
    skus: [{id: "demo-sku-2", code: "CUBE-BLUE-6PC"}],
  },
];

const demoStatuses: AssetStatus[] = [
  "DRAFT",
  "APPROVED",
  "APPROVED",
  "REVIEW",
  "PROCESSING",
  "REVIEW",
  "DRAFT",
  "APPROVED",
  "REJECTED",
  "REVIEW",
];

export const demoAssets: Asset[] = assetTypes.map((assetType, index) => ({
  id: `asset-${assetType.toLowerCase()}`,
  product_id: "demo-kettle",
  sku_id: index < 2 ? "demo-sku" : null,
  asset_type: assetType,
  label:
    assetType === "ORIGINAL"
      ? "供应商正面原图"
      : `${assetType === "COMPARE" ? "核心卖点" : "Temu US"} ${assetType}`,
  is_archived: false,
  created_at: `2026-08-10T0${Math.min(index, 9)}:20:00Z`,
  versions: [
    {
      id: `version-${assetType.toLowerCase()}-1`,
      asset_id: `asset-${assetType.toLowerCase()}`,
      version_number: 1,
      object_key: `demo/${assetType.toLowerCase()}.jpg`,
      original_filename: `${assetType.toLowerCase()}.jpg`,
      mime_type: "image/jpeg",
      byte_size: 840000 + index * 12000,
      width: 1600,
      height: 1600,
      checksum_sha256: `${index}`.repeat(64),
      source_version_id: assetType === "ORIGINAL" ? null : "version-original-1",
      status: demoStatuses[index],
      is_deleted: false,
      created_at: `2026-08-10T0${Math.min(index, 9)}:20:00Z`,
    },
    ...(index > 1 && index % 3 === 0
      ? [
          {
            id: `version-${assetType.toLowerCase()}-2`,
            asset_id: `asset-${assetType.toLowerCase()}`,
            version_number: 2,
            object_key: `demo/${assetType.toLowerCase()}-v2.jpg`,
            original_filename: `${assetType.toLowerCase()}-v2.jpg`,
            mime_type: "image/jpeg",
            byte_size: 790000,
            width: 1600,
            height: 1600,
            checksum_sha256: `${index + 1}`.repeat(64).slice(0, 64),
            source_version_id: `version-${assetType.toLowerCase()}-1`,
            status: demoStatuses[index],
            is_deleted: false,
            created_at: "2026-08-10T10:20:00Z",
          } satisfies AssetVersion,
        ]
      : []),
  ],
}));

export const demoJobs: GenerationJob[] = [
  {
    id: "j-1", platform: "temu", image_slot: "MAIN", status: "completed",
    generation_mode: "STRICT", reference_asset_version_ids: ["demo-original-front", "demo-original-side"],
    provider: "openai", provider_model: "gpt-image-2", provider_request_id: "req_demo_8fc1",
    prompt: "Create a faithful Temu main image from both supplier reference angles. Preserve color, texture, logo and structure.",
    revised_prompt: null, duration_ms: 18420, retry_count: 0, output_version_id: "demo-main-v3",
    quality_check: {
      product_similarity: {status: "unavailable", details: "等待相似度分析器"},
      resolution: {status: "passed", actual: {width: 1600, height: 1600}},
      aspect_ratio: {status: "passed", actual: 1, expected: "1:1"},
      file_size: {status: "passed", actual: 884220}, format: {status: "passed", actual: "image/png"},
      text_risk: {status: "unavailable", details: "等待文字风险分析器"},
      watermark_risk: {status: "unavailable", details: "等待水印风险分析器"}, review_required: true,
    },
    review_result: {decision: "approved", reason: null, comment: "主体与供应商原图一致", reviewer: "当前运营", created_at: "2026-08-10T10:02:00Z"},
    created_at: "2026-08-10T09:30:00Z",
  },
  {id: "j-2", platform: "temu", image_slot: "SCENE", status: "processing", generation_mode: "BALANCED", reference_asset_version_ids: ["demo-original-front"], provider: "openai", prompt: "Place the unchanged product in a realistic travel setting.", retry_count: 1, created_at: "2026-08-10T09:32:00Z"},
  {id: "j-3", platform: "temu", image_slot: "DIMENSION", status: "pending", generation_mode: "STRICT", reference_asset_version_ids: ["demo-original-front", "demo-original-side"], provider: "mock", prompt: "Create an exact dimension view without changing product geometry.", retry_count: 0, created_at: "2026-08-10T09:33:00Z"},
];

export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function read<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${apiUrl}${path}`, {cache: "no-store"});
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export async function loadWorkbench() {
  const [products, jobs] = await Promise.all([
    read<Product[]>("/products", demoProducts),
    read<GenerationJob[]>("/generation-jobs", demoJobs),
  ]);
  return {products, jobs, demo: products === demoProducts};
}

export async function loadGenerationRecords() {
  const jobs = await read<GenerationJob[]>("/generation-jobs", demoJobs);
  return {jobs, demo: jobs === demoJobs};
}

export async function loadProductWorkspace(productId: string) {
  if (productId.startsWith("demo-")) {
    return {product: demoProducts[0], assets: demoAssets, demo: true};
  }
  const product = await read<Product | null>(`/products/${productId}`, null);
  const assets = await read<Asset[]>(`/products/${productId}/assets`, []);
  if (!product) return {product: demoProducts[0], assets: demoAssets, demo: true};
  return {product, assets, demo: false};
}

export async function loadPlatformRuleCenter() {
  const [platforms, rules] = await Promise.all([
    read<Platform[]>("/platform-rules/platforms", demoPlatforms),
    read<PlatformRuleVersion[]>("/platform-rules", demoRules),
  ]);
  return {platforms, rules, demo: platforms === demoPlatforms || rules === demoRules};
}

export async function loadVisualPlanCenter(productId?: string) {
  const [products, platforms, rules, plans] = await Promise.all([
    read<Product[]>("/products", demoProducts), read<Platform[]>("/platform-rules/platforms", demoPlatforms),
    read<PlatformRuleVersion[]>("/platform-rules", demoRules),
    read<ProductVisualPlan[]>(`/visual-plans${productId ? `?product_id=${productId}` : ""}`, demoVisualPlans),
  ]);
  return {products, platforms, rules, plans, demo: plans === demoVisualPlans};
}

export function assetContentUrl(versionId: string) {
  return `${apiUrl}/asset-versions/${versionId}/content`;
}

export function latestVersion(asset: Asset) {
  return [...asset.versions].sort((left, right) => right.version_number - left.version_number)[0];
}

export async function submitReview(
  versionId: string,
  decision: "approved" | "rejected" | "regenerate",
  comment: string,
  reason?: RejectReason,
) {
  const response = await fetch(`${apiUrl}/asset-versions/${versionId}/reviews`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({decision, reviewer: "当前运营", comment: comment || null, reason}),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? "审核操作失败");
  return response.json();
}

export function summarizeJobs(jobs: GenerationJob[]) {
  return jobs.reduce(
    (summary, job) => ({...summary, [job.status]: summary[job.status] + 1}),
    {pending: 0, processing: 0, completed: 0, failed: 0},
  );
}
