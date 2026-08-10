"use client";

import { Badge, Button, Card, cn } from "@ecommerce-visual-workbench/ui";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  FileImage,
  History,
  LockKeyhole,
  PackagePlus,
  Ruler,
  Upload,
  Weight,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";

import { AssetArtwork } from "@/components/asset-artwork";
import {
  apiUrl,
  assetTypes,
  latestVersion,
  type Asset,
  type AssetStatus,
  type AssetType,
  type Product,
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

export function ProductWorkspace({
  product,
  initialAssets,
  demo,
}: {
  product: Product;
  initialAssets: Asset[];
  demo: boolean;
}) {
  const [assets, setAssets] = useState(initialAssets);
  const [filter, setFilter] = useState<AssetType | "ALL">("ALL");
  const [selectedId, setSelectedId] = useState(initialAssets[0]?.id ?? "");
  const [notice, setNotice] = useState<string | null>(null);
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
