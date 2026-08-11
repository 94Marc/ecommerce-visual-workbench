"use client";

import { Badge, Button, Card, cn } from "@ecommerce-visual-workbench/ui";
import {
  ArrowUpRight,
  Check,
  Eraser,
  FileImage,
  History,
  ImagePlus,
  LockKeyhole,
  Maximize2,
  PackagePlus,
  Ruler,
  ScanLine,
  Sparkles,
  Upload,
  WandSparkles,
  Weight,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";

import { AssetArtwork } from "@/components/asset-artwork";
import {
  apiUrl,
  assetTypes,
  createImageTask,
  latestVersion,
  type Asset,
  type AssetStatus,
  type AssetType,
  type GenerationJob,
  type Product,
  type TaskType,
  type WorkflowDefinition,
} from "@/lib/api";

const typeLabels: Record<AssetType, string> = {
  ORIGINAL: "原图",
  CUTOUT: "抠图",
  MAIN: "主图",
  DETAIL: "详情图",
  DIMENSION: "尺寸图",
  SCENE: "场景图",
  USAGE: "使用图",
  PACKAGE: "包装图",
  CLOSEUP: "细节图",
  COMPARE: "卖点图",
};

const statusStyle: Record<AssetStatus, string> = {
  DRAFT: "border-slate-200 bg-slate-50 text-slate-600",
  PROCESSING: "border-orange-200 bg-orange-50 text-orange-700",
  REVIEW: "border-blue-200 bg-blue-50 text-blue-700",
  APPROVED: "border-emerald-200 bg-emerald-50 text-emerald-700",
  REJECTED: "border-rose-200 bg-rose-50 text-rose-700",
};

const statusLabels: Record<AssetStatus, string> = {
  DRAFT: "草稿",
  PROCESSING: "处理中",
  REVIEW: "待审核",
  APPROVED: "已通过",
  REJECTED: "已拒绝",
};

const processingActions = [
  {taskType: "REMOVE_BACKGROUND", label: "去背景", detail: "透明 PNG", provider: "rembg", mode: "STRICT", icon: Eraser},
  {taskType: "UPSCALE", label: "高清增强", detail: "保守纹理", provider: "Real-ESRGAN", mode: "STRICT", icon: Maximize2},
  {taskType: "GENERATE_MAIN", label: "生成主图", detail: "平台合规", provider: "ComfyUI / OpenAI", mode: "STRICT", icon: ImagePlus, slot: "MAIN"},
  {taskType: "GENERATE_SCENE", label: "生成场景图", detail: "环境可变", provider: "ComfyUI / OpenAI", mode: "BALANCED", icon: Sparkles, slot: "SCENE"},
  {taskType: "GENERATE_USAGE", label: "生成使用图", detail: "使用语境", provider: "ComfyUI / OpenAI", mode: "BALANCED", icon: WandSparkles, slot: "USAGE"},
  {taskType: "GENERATE_DETAIL", label: "生成详情图", detail: "主体锁定", provider: "ComfyUI / OpenAI", mode: "STRICT", icon: ScanLine, slot: "DETAIL"},
] as const;

export function ProductWorkspace({
  product,
  initialAssets,
  initialJobs,
  workflows,
  demo,
}: {
  product: Product;
  initialAssets: Asset[];
  initialJobs: GenerationJob[];
  workflows: WorkflowDefinition[];
  demo: boolean;
}) {
  const [assets, setAssets] = useState(initialAssets);
  const [jobs, setJobs] = useState(initialJobs);
  const [filter, setFilter] = useState<AssetType | "ALL">("ALL");
  const [selectedId, setSelectedId] = useState(initialAssets[0]?.id ?? "");
  const [notice, setNotice] = useState<string | null>(null);
  const [busyTask, setBusyTask] = useState<TaskType | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const selected = assets.find((asset) => asset.id === selectedId) ?? assets[0];
  const visibleAssets = useMemo(
    () => assets.filter((asset) => filter === "ALL" || asset.asset_type === filter),
    [assets, filter],
  );

  async function uploadOriginal(file: File) {
    if (demo) {
      setNotice("演示模式不会上传文件；连接 API 后将创建永久 ORIGINAL 版本。 ");
      return;
    }
    const body = new FormData();
    body.append("file", file);
    body.append("label", file.name);
    const response = await fetch(`${apiUrl}/products/${product.id}/assets/original`, {
      method: "POST",
      body,
    });
    if (!response.ok) {
      setNotice("上传失败，请检查文件格式和对象存储连接。");
      return;
    }
    const created = (await response.json()) as Asset;
    setAssets((current) => [...current, created]);
    setSelectedId(created.id);
    setNotice("原图已保存，后续处理将创建新的版本。");
  }

  async function startProcessing(action: (typeof processingActions)[number]) {
    if (!selected) return;
    if (demo) {
      setNotice(`${action.label}需要连接真实 API；演示模式不会伪造 Provider 结果。`);
      return;
    }
    const source = latestVersion(selected);
    const isGeneration = action.taskType.startsWith("GENERATE_");
    const references = assets
      .filter((asset) => asset.asset_type === "ORIGINAL")
      .map((asset) => latestVersion(asset).id);
    setBusyTask(action.taskType);
    try {
      const created = await createImageTask({
        source_version_id: source.id,
        task_type: action.taskType,
        generation_mode: action.mode,
        ...(action.taskType === "UPSCALE" ? {upscale_mode: "CONSERVATIVE"} : {}),
        ...(isGeneration ? {
          reference_asset_version_ids: references,
          platform: "temu",
          market: "US",
          category: product.category,
          image_slot: "slot" in action ? action.slot : undefined,
        } : {}),
      });
      setJobs((current) => [created, ...current]);
      setNotice(`${action.label}任务已创建；Worker 将写入新的 AssetVersion。`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "图片处理任务创建失败");
    } finally {
      setBusyTask(null);
    }
  }

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 p-5 lg:p-8">
      {notice && (
        <div className="flex items-center justify-between rounded-xl border border-[#ffd2c5] bg-[#fff7f3] px-4 py-3 text-sm text-[#9f3b1e]">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="font-bold">关闭</button>
        </div>
      )}

      <section className="grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
        <Card className="overflow-hidden p-0">
          <div className="border-b border-[#e3e7ee] px-6 py-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">
                  PRODUCT / {product.id.slice(0, 12).toUpperCase()}
                </div>
                <h2 className="display-face mt-2 text-3xl font-bold">{product.name}</h2>
                <p className="mt-2 text-sm text-[#677286]">{product.category}</p>
              </div>
              <Button variant="secondary" size="sm">编辑商品信息</Button>
            </div>
          </div>
          <div className="grid gap-px bg-[#e7eaf0] sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["材质", product.material ?? "未填写", FileImage],
              ["颜色", product.color ?? "未填写", Check],
              ["尺寸", product.dimensions ? `${product.dimensions.length ?? "–"} × ${product.dimensions.width ?? "–"} × ${product.dimensions.height ?? "–"} ${product.dimensions.unit ?? ""}` : "未填写", Ruler],
              ["重量", product.weight_value ? `${product.weight_value} ${product.weight_unit ?? ""}` : "未填写", Weight],
            ].map(([label, value, Icon]) => (
              <div key={String(label)} className="bg-white p-5">
                <Icon className="h-4 w-4 text-[#ff6433]" />
                <div className="mt-4 text-xs text-[#8a94a6]">{label as string}</div>
                <div className="mt-1 text-sm font-bold text-[#263149]">{value as string}</div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 px-6 py-5">
            {product.selling_points.map((point) => <Badge key={point}>{point}</Badge>)}
          </div>
        </Card>

        <Card className="p-5 lg:p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">SKU MATRIX</p>
              <h2 className="display-face mt-1 text-xl font-bold">SKU 信息</h2>
            </div>
            <Badge>{product.skus.length} 个 SKU</Badge>
          </div>
          <div className="mt-4 space-y-2">
            {product.skus.map((sku) => (
              <div key={sku.id} className="rounded-xl border border-[#e1e5ec] bg-[#f8fafc] p-4">
                <div className="utility-face text-xs font-bold text-[#263149]">{sku.code}</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(sku.attributes ?? {}).map(([key, value]) => (
                    <span key={key} className="rounded-md bg-white px-2 py-1 text-[11px] text-[#687489] ring-1 ring-[#e1e5ec]">
                      {key} · {String(value)}
                    </span>
                  ))}
                  {!Object.keys(sku.attributes ?? {}).length && <span className="text-xs text-[#8a94a6]">暂无变体属性</span>}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1fr_460px]">
        <Card className="overflow-hidden p-0">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[#e1e6ed] px-5 py-5 lg:px-6">
            <div>
              <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">IMAGE PROCESSING DOCK</p>
              <h2 className="display-face mt-1 text-2xl font-bold">图片处理工位</h2>
              <p className="mt-1 text-sm text-[#778296]">先选资产，再选择真实处理路线；不可用的 Provider 会明确失败。</p>
            </div>
            <Badge>{selected ? `${typeLabels[selected.asset_type]} · V${latestVersion(selected).version_number}` : "未选源图"}</Badge>
          </div>
          <div className="grid gap-px bg-[#e4e8ef] sm:grid-cols-2 lg:grid-cols-3">
            {processingActions.map((action) => {
              const Icon = action.icon;
              const running = busyTask === action.taskType;
              const workflow = workflows.find((item) => item.task_type === action.taskType && item.active);
              return (
                <button
                  key={action.taskType}
                  type="button"
                  disabled={!selected || busyTask !== null}
                  onClick={() => void startProcessing(action)}
                  className="group bg-white p-5 text-left transition hover:bg-[#fff8f5] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#ff6433] disabled:cursor-not-allowed disabled:opacity-55"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#172033] text-white transition group-hover:bg-[#ff6433]">
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="utility-face text-[9px] font-bold tracking-[.08em] text-[#9a6655]">{action.mode}</span>
                  </div>
                  <div className="mt-4 text-sm font-bold text-[#263149]">{running ? "正在创建…" : action.label}</div>
                  <div className="mt-1 text-xs text-[#7c8798]">{action.detail} · {workflow?.name ?? action.provider}</div>
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="overflow-hidden p-0">
          <div className="border-b border-[#e1e6ed] px-5 py-5">
            <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">ROUTE LEDGER</p>
            <div className="mt-1 flex items-center justify-between gap-3">
              <h2 className="display-face text-xl font-bold">最近处理记录</h2>
              <Button variant="secondary" size="sm" asChild><Link href="/generation-jobs">全部记录</Link></Button>
            </div>
          </div>
          <div className="divide-y divide-[#e6e9ef]">
            {jobs.slice(0, 4).map((job) => {
              const workflow = workflows.find((item) => item.id === job.workflow_definition_id);
              return (
                <div key={job.id} className="px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="utility-face text-[11px] font-bold text-[#263149]">{job.task_type ?? job.image_slot ?? "IMAGE_TASK"}</span>
                    <Badge className={job.status === "failed" ? "border-rose-200 bg-rose-50 text-rose-700" : job.status === "completed" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : ""}>{job.status}</Badge>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[10px]">
                    {[
                      ["Provider", `${job.provider ?? "待路由"}${job.provider_model ? ` / ${job.provider_model}` : ""}`],
                      ["Mode", job.generation_mode ?? "STRICT"],
                      ["References", `${job.reference_asset_version_ids?.length ?? 1} 张`],
                      ["Workflow", workflow?.name ?? "direct"],
                      ["Duration", job.duration_ms != null ? `${(job.duration_ms / 1000).toFixed(1)}s` : "—"],
                      ["Output Version", job.output_version_id?.slice(0, 12) ?? "等待输出"],
                    ].map(([label, value]) => (
                      <div key={label} className="min-w-0">
                        <dt className="utility-face text-[8px] tracking-[.08em] text-[#9aa2af]">{label}</dt>
                        <dd className="mt-0.5 truncate font-bold text-[#596579]">{value}</dd>
                      </div>
                    ))}
                  </dl>
                  {job.status === "failed" && <p className="mt-2 text-xs text-rose-700">{job.failure_code}: {job.error_message}</p>}
                </div>
              );
            })}
            {!jobs.length && <div className="px-5 py-10 text-center text-sm text-[#7d8798]">选择上方路线创建第一条处理任务。</div>}
          </div>
        </Card>
      </section>

      <section id="assets" className="grid gap-5 2xl:grid-cols-[1fr_370px]">
        <Card className="p-5 lg:p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">ASSET LIGHT TABLE</p>
              <h2 className="display-face mt-1 text-2xl font-bold">图片资产</h2>
              <p className="mt-1 text-sm text-[#778296]">原图锁定保存，处理结果沿版本轨道向右追加。</p>
            </div>
            <div>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadOriginal(file);
                }}
              />
              <Button onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" />上传供应商原图</Button>
            </div>
          </div>

          <div className="mt-5 flex gap-2 overflow-x-auto pb-2">
            <button onClick={() => setFilter("ALL")} className={cn("rounded-full px-3 py-1.5 text-xs font-bold", filter === "ALL" ? "bg-[#172033] text-white" : "bg-[#f0f3f7] text-[#657086]")}>全部 · {assets.length}</button>
            {assetTypes.map((type) => (
              <button key={type} onClick={() => setFilter(type)} className={cn("whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-bold", filter === type ? "bg-[#172033] text-white" : "bg-[#f0f3f7] text-[#657086]")}>
                {typeLabels[type]} · {assets.filter((asset) => asset.asset_type === type).length}
              </button>
            ))}
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {visibleAssets.map((asset) => {
              const version = latestVersion(asset);
              const selectedCard = selected?.id === asset.id;
              return (
                <button
                  key={asset.id}
                  onClick={() => setSelectedId(asset.id)}
                  className={cn("overflow-hidden rounded-xl border bg-white text-left transition", selectedCard ? "border-[#ff6433] ring-2 ring-[#ff6433]/10" : "border-[#e0e5ed] hover:border-[#aeb8c7]")}
                >
                  <div className="h-44"><AssetArtwork type={asset.asset_type} versionId={version.id} demo={demo} /></div>
                  <div className="p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div><span className="font-bold">{typeLabels[asset.asset_type]}</span><span className="utility-face ml-2 text-[10px] text-[#8994a6]">V{version.version_number}</span></div>
                      {asset.asset_type === "ORIGINAL" && <LockKeyhole className="h-3.5 w-3.5 text-[#6c778b]" />}
                    </div>
                    <p className="mt-1 truncate text-xs text-[#7a8598]">{asset.label ?? version.original_filename}</p>
                    <Badge className={cn("mt-3", statusStyle[version.status])}>{statusLabels[version.status]}</Badge>
                  </div>
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="h-fit p-5 lg:sticky lg:top-6 lg:p-6">
          {selected ? (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">VERSION RAIL</p>
                  <h2 className="display-face mt-1 text-xl font-bold">{typeLabels[selected.asset_type]}版本</h2>
                </div>
                {selected.asset_type === "ORIGINAL" && <Badge><LockKeyhole className="mr-1 h-3 w-3" />永久保存</Badge>}
              </div>
              <div className="mt-5 space-y-0">
                {[...selected.versions].sort((left, right) => right.version_number - left.version_number).map((version, index) => (
                  <div key={version.id} className="relative flex gap-3 pb-5 last:pb-0">
                    {index < selected.versions.length - 1 && <div className="absolute left-[7px] top-4 h-full w-px bg-[#dce1e9]" />}
                    <div className={cn("relative mt-1 h-4 w-4 shrink-0 rounded-full border-4 border-white ring-1", version.status === "APPROVED" ? "bg-emerald-500 ring-emerald-300" : version.status === "REJECTED" ? "bg-rose-500 ring-rose-300" : "bg-[#ff6433] ring-[#ffc5b3]")} />
                    <div className="min-w-0 flex-1 rounded-xl border border-[#e1e5ec] bg-[#f8fafc] p-3">
                      <div className="flex items-center justify-between"><span className="utility-face text-xs font-bold">VERSION {version.version_number}</span><Badge className={statusStyle[version.status]}>{statusLabels[version.status]}</Badge></div>
                      <p className="mt-2 truncate text-xs text-[#758095]">{version.original_filename}</p>
                      <div className="mt-2 flex justify-between text-[10px] text-[#9099a8]"><span>{version.width ?? "–"} × {version.height ?? "–"}</span><span>{(version.byte_size / 1024 / 1024).toFixed(2)} MB</span></div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-5 grid gap-2">
                {latestVersion(selected).status === "REVIEW" && (
                  <Button asChild><Link href={`/reviews?product=${product.id}&version=${latestVersion(selected).id}`}><Check className="h-4 w-4" />进入审核</Link></Button>
                )}
                {selected.asset_type !== "ORIGINAL" && <Button variant="secondary"><PackagePlus className="h-4 w-4" />创建处理版本</Button>}
                <Button variant="secondary"><History className="h-4 w-4" />查看完整追溯链</Button>
              </div>
              <div className="mt-5 rounded-xl bg-[#172033] p-4 text-white">
                <div className="flex items-center justify-between"><span className="text-xs font-bold">版本原则</span><ArrowUpRight className="h-4 w-4 text-[#ff7448]" /></div>
                <p className="mt-2 text-xs leading-5 text-[#aeb7c8]">文件内容永不原位覆盖。重新裁切、压缩或排版都会追加版本并保留来源。</p>
              </div>
            </>
          ) : (
            <div className="py-12 text-center text-sm text-[#7a8598]">选择一个图片资产查看版本。</div>
          )}
        </Card>
      </section>
    </div>
  );
}
