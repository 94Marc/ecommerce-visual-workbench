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
  created_at: string;
};

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

const demoJobs: GenerationJob[] = [
  {id: "j-1", platform: "temu", image_slot: "MAIN", status: "completed", created_at: "2026-08-10T09:30:00Z"},
  {id: "j-2", platform: "temu", image_slot: "SCENE", status: "processing", created_at: "2026-08-10T09:32:00Z"},
  {id: "j-3", platform: "temu", image_slot: "DIMENSION", status: "pending", created_at: "2026-08-10T09:33:00Z"},
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

export async function loadProductWorkspace(productId: string) {
  if (productId.startsWith("demo-")) {
    return {product: demoProducts[0], assets: demoAssets, demo: true};
  }
  const product = await read<Product | null>(`/products/${productId}`, null);
  const assets = await read<Asset[]>(`/products/${productId}/assets`, []);
  if (!product) return {product: demoProducts[0], assets: demoAssets, demo: true};
  return {product, assets, demo: false};
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
) {
  const response = await fetch(`${apiUrl}/asset-versions/${versionId}/reviews`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({decision, reviewer: "当前运营", comment: comment || null}),
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
