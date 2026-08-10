export type Product = {
  id: string;
  name: string;
  category: string;
  material: string | null;
  color: string | null;
  selling_points: string[];
  skus: {id: string; code: string}[];
};

export type GenerationJob = {
  id: string;
  platform: string;
  image_slot: string;
  status: "pending" | "processing" | "completed" | "failed";
  created_at: string;
};

const demoProducts: Product[] = [
  {
    id: "demo-kettle",
    name: "折叠旅行电热水壶",
    category: "小家电 · 旅行用品",
    material: "食品级硅胶 / 304 不锈钢",
    color: "鼠尾草绿",
    selling_points: ["双电压", "折叠收纳", "防干烧"],
    skus: [{id: "demo-sku", code: "KETTLE-SAGE-EU"}],
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

const demoJobs: GenerationJob[] = [
  {id: "j-1", platform: "temu", image_slot: "MAIN", status: "completed", created_at: "2026-08-10T09:30:00Z"},
  {id: "j-2", platform: "temu", image_slot: "SCENE", status: "processing", created_at: "2026-08-10T09:32:00Z"},
  {id: "j-3", platform: "temu", image_slot: "DIMENSION", status: "pending", created_at: "2026-08-10T09:33:00Z"},
];

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

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

export function summarizeJobs(jobs: GenerationJob[]) {
  return jobs.reduce(
    (summary, job) => ({...summary, [job.status]: summary[job.status] + 1}),
    {pending: 0, processing: 0, completed: 0, failed: 0},
  );
}

