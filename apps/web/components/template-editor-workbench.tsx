"use client";

import type {
  EcommerceTemplate,
  TemplateDocument,
  TemplateLayer,
  TemplatePreviewData,
} from "@ecommerce-visual-workbench/templates";
import {Badge, Button, Card, cn} from "@ecommerce-visual-workbench/ui";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Copy,
  Eye,
  EyeOff,
  Layers3,
  Lock,
  Redo2,
  Save,
  Send,
  Trash2,
  Undo2,
  Unlock,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {useMemo, useState} from "react";

import {
  assetContentUrl,
  copyTemplate,
  latestVersion,
  saveTemplateVersion,
  renderTemplate,
  updateTemplate,
  type Asset,
  type Product,
} from "@/lib/api";

const KonvaTemplateCanvas = dynamic(
  () => import("@ecommerce-visual-workbench/editor").then((module) => module.KonvaTemplateCanvas),
  {ssr: false, loading: () => <div className="h-[680px] w-[680px] animate-pulse bg-white shadow-xl" />},
);

type History = {past: TemplateDocument[]; present: TemplateDocument; future: TemplateDocument[]};

export function TemplateEditorWorkbench({template, products, assets, demo}: {
  template: EcommerceTemplate;
  products: Product[];
  assets: Asset[];
  demo: boolean;
}) {
  const version = template.latest_version!;
  const [history, setHistory] = useState<History>({past: [], present: version.schema_json, future: []});
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(history.present.layers[0]?.id ?? null);
  const [productId, setProductId] = useState(products[0]?.id ?? "");
  const product = products.find((item) => item.id === productId) ?? products[0];
  const [skuId, setSkuId] = useState(product?.skus[0]?.id ?? "");
  const [previewOnly, setPreviewOnly] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const selected = history.present.layers.find((layer) => layer.id === selectedLayerId) ?? null;

  const previewData = useMemo<TemplatePreviewData>(() => {
    const dimensions = product?.dimensions ?? {};
    const withUnit = (key: string) => dimensions[key] == null ? "" : `${dimensions[key]} ${dimensions.unit ?? "cm"}`;
    const approvedUrl = (types: string[]) => {
      const asset = assets.find((item) => item.product_id === product?.id && types.includes(item.asset_type) && item.versions.some((itemVersion) => itemVersion.status === "APPROVED"));
      const approved = asset?.versions.filter((itemVersion) => itemVersion.status === "APPROVED").sort((left, right) => right.version_number - left.version_number)[0];
      return approved ? assetContentUrl(approved.id) : undefined;
    };
    return {
      product: {
        name: product?.name ?? "",
        material: product?.material ?? "",
        color: product?.color ?? "",
        length: withUnit("length"), width: withUnit("width"), height: withUnit("height"),
        weight: product?.weight_value == null ? "" : `${product.weight_value} ${product.weight_unit ?? ""}`,
      },
      sku: {code: product?.skus.find((sku) => sku.id === skuId)?.code ?? ""},
      selling_point_1: product?.selling_points[0] ?? "",
      selling_point_2: product?.selling_points[1] ?? "",
      selling_point_3: product?.selling_points[2] ?? "",
      assets: {
        cutout: approvedUrl(["CUTOUT", "MAIN"]), main: approvedUrl(["MAIN", "CUTOUT"]),
        closeup: approvedUrl(["CLOSEUP", "CUTOUT", "MAIN"]), package: approvedUrl(["PACKAGE", "CUTOUT", "MAIN"]),
      },
    };
  }, [assets, product, skuId]);

  function commit(document: TemplateDocument) {
    if (JSON.stringify(document) === JSON.stringify(history.present)) return;
    setHistory((current) => ({past: [...current.past, current.present], present: document, future: []}));
  }

  function updateSelected(changes: Partial<TemplateLayer>) {
    if (!selected) return;
    commit({...history.present, layers: history.present.layers.map((layer) => layer.id === selected.id ? {...layer, ...changes} : layer)});
  }

  function undo() {
    setHistory((current) => current.past.length ? {past: current.past.slice(0, -1), present: current.past.at(-1)!, future: [current.present, ...current.future]} : current);
  }

  function redo() {
    setHistory((current) => current.future.length ? {past: [...current.past, current.present], present: current.future[0], future: current.future.slice(1)} : current);
  }

  function remove() {
    if (!selected) return;
    commit({...history.present, layers: history.present.layers.filter((layer) => layer.id !== selected.id)});
    setSelectedLayerId(null);
  }

  function duplicate() {
    if (!selected) return;
    const copy = {...selected, id: `${selected.id}_copy_${Date.now()}`, x: selected.x + 24, y: selected.y + 24, zIndex: history.present.layers.length};
    commit({...history.present, layers: [...history.present.layers, copy]});
    setSelectedLayerId(copy.id);
  }

  function reorder(delta: number) {
    if (!selected) return;
    const ordered = [...history.present.layers].sort((left, right) => left.zIndex - right.zIndex);
    const index = ordered.findIndex((layer) => layer.id === selected.id);
    const target = index + delta;
    if (target < 0 || target >= ordered.length) return;
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    const indexes = new Map(ordered.map((layer, position) => [layer.id, position]));
    commit({...history.present, layers: history.present.layers.map((layer) => ({...layer, zIndex: indexes.get(layer.id) ?? layer.zIndex}))});
  }

  async function save() {
    if (demo) {
      setMessage("演示模式已在本地保留当前编辑；连接 API 后保存会创建新的 TemplateVersion。");
      return;
    }
    try {
      await saveTemplateVersion(template.id, {canvas_width: version.canvas_width, canvas_height: version.canvas_height, background: version.background, schema_json: history.present});
      setMessage("已保存为新的模板版本，历史版本保持不变。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); }
  }

  async function publish() {
    if (demo) { setMessage("演示模板已模拟发布；真实环境会将模板状态设为 ACTIVE。"); return; }
    try { await updateTemplate(template.id, {status: "ACTIVE"}); setMessage("模板已发布。"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "发布失败"); }
  }

  async function copyCurrent() {
    if (demo) { setMessage("已模拟复制模板，新模板会从当前最新版本开始。"); return; }
    try { await copyTemplate(template.id, `${template.code}_COPY_${Date.now().toString().slice(-4)}`); setMessage("模板副本已创建。"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "复制失败"); }
  }

  async function generateOutput() {
    if (demo) { setMessage("演示模式已完成模板预览；连接 API 后会生成 REVIEW 状态的新 AssetVersion。"); return; }
    try {
      const result = await renderTemplate({template_version_id: version.id, product_id: productId, sku_id: skuId || undefined, output_format: "PNG"});
      setMessage(`成品已进入审核，AssetVersion ${result.output_asset_version_id.slice(0, 8)}。`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "生成失败"); }
  }

  const layers = [...history.present.layers].sort((left, right) => right.zIndex - left.zIndex);
  return (
    <div className="min-h-screen bg-[#dfe5ed]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#cfd6df] bg-[#151c2c] px-4 py-3 text-white">
        <div className="flex items-center gap-3"><Button variant="ghost" size="icon" asChild><Link href="/templates"><ArrowLeft className="h-4 w-4" /></Link></Button><div><div className="utility-face text-[9px] tracking-[.14em] text-[#8994aa]">{template.code} · V{version.version}</div><h1 className="text-sm font-bold">{template.name}</h1></div><Badge className="border-white/10 bg-white/5 text-white">{template.status}</Badge></div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={undo} disabled={!history.past.length}><Undo2 className="h-4 w-4" />撤销</Button>
          <Button variant="ghost" size="sm" onClick={redo} disabled={!history.future.length}><Redo2 className="h-4 w-4" />重做</Button>
          <Button variant="ghost" size="sm" onClick={() => setPreviewOnly((value) => !value)}><Eye className="h-4 w-4" />预览</Button>
          <Button variant="ghost" size="sm" onClick={copyCurrent}><Copy className="h-4 w-4" />复制模板</Button>
          <Button variant="secondary" size="sm" onClick={save}><Save className="h-4 w-4" />保存新版本</Button>
          <Button variant="secondary" size="sm" onClick={generateOutput}><Layers3 className="h-4 w-4" />生成成品</Button>
          <Button size="sm" onClick={publish}><Send className="h-4 w-4" />发布模板</Button>
        </div>
      </header>

      <div className={cn("grid min-h-[calc(100vh-65px)]", previewOnly ? "grid-cols-1" : "xl:grid-cols-[250px_1fr_300px]")}>
        {!previewOnly && <aside className="border-r border-[#cfd6df] bg-[#f8fafc] p-4">
          <div className="flex items-center justify-between"><span className="utility-face text-[10px] tracking-[.14em] text-[#7b8698]">LAYERS</span><Layers3 className="h-4 w-4" /></div>
          <div className="mt-4 space-y-1">
            {layers.map((layer) => <button key={layer.id} onClick={() => setSelectedLayerId(layer.id)} className={cn("flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs", selectedLayerId === layer.id ? "border-[#ff6433] bg-[#fff2ed]" : "border-transparent hover:bg-white")}><span className="utility-face min-w-12 text-[9px] text-[#8994a6]">{layer.type}</span><span className="min-w-0 flex-1 truncate font-bold">{layer.id}</span>{layer.locked ? <Lock className="h-3 w-3" /> : layer.visible ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}</button>)}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2"><Button variant="secondary" size="sm" onClick={() => reorder(1)}><ArrowUp className="h-3 w-3" />上移</Button><Button variant="secondary" size="sm" onClick={() => reorder(-1)}><ArrowDown className="h-3 w-3" />下移</Button><Button variant="secondary" size="sm" onClick={duplicate}><Copy className="h-3 w-3" />复制</Button><Button variant="secondary" size="sm" onClick={remove}><Trash2 className="h-3 w-3" />删除</Button></div>
        </aside>}

        <main className="relative grid min-w-0 place-items-center overflow-auto p-8 [background-image:linear-gradient(#d4dae3_1px,transparent_1px),linear-gradient(90deg,#d4dae3_1px,transparent_1px)] [background-size:28px_28px]">
          <KonvaTemplateCanvas document={history.present} canvasWidth={version.canvas_width} canvasHeight={version.canvas_height} background={String(version.background.color ?? "#ffffff")} previewData={previewData} selectedLayerId={previewOnly ? null : selectedLayerId} onSelectLayer={setSelectedLayerId} onChange={commit} />
          <div className="absolute bottom-4 left-4 rounded-md bg-[#172033] px-3 py-2 utility-face text-[9px] text-white">{version.canvas_width} × {version.canvas_height} / RGB</div>
        </main>

        {!previewOnly && <aside className="border-l border-[#cfd6df] bg-white p-4">
          <div className="utility-face text-[10px] tracking-[.14em] text-[#7b8698]">PRODUCT PREVIEW</div>
          <label className="mt-3 grid gap-1 text-xs font-bold">商品<select className="rounded-lg border border-[#d7dde7] p-2 font-normal" value={productId} onChange={(event) => {setProductId(event.target.value); setSkuId(products.find((item) => item.id === event.target.value)?.skus[0]?.id ?? "");}}>{products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label className="mt-3 grid gap-1 text-xs font-bold">SKU<select className="rounded-lg border border-[#d7dde7] p-2 font-normal" value={skuId} onChange={(event) => setSkuId(event.target.value)}>{product?.skus.map((sku) => <option key={sku.id} value={sku.id}>{sku.code}</option>)}</select></label>
          <div className="my-5 border-t border-[#e4e8ee]" />
          <div className="utility-face text-[10px] tracking-[.14em] text-[#7b8698]">PROPERTIES</div>
          {selected ? <div className="mt-4 space-y-3">
            <Field label="X" value={selected.x} onChange={(value) => updateSelected({x: value})} /><Field label="Y" value={selected.y} onChange={(value) => updateSelected({y: value})} />
            <Field label="宽度" value={selected.width} onChange={(value) => updateSelected({width: Math.max(0, value)})} /><Field label="高度" value={selected.height} onChange={(value) => updateSelected({height: Math.max(0, value)})} />
            <Field label="旋转" value={selected.rotation} onChange={(value) => updateSelected({rotation: value})} />
            {selected.type === "TEXT" && <label className="grid gap-1 text-xs font-bold">文本<textarea className="min-h-24 rounded-lg border border-[#d7dde7] p-2 font-normal" value={selected.text ?? ""} onChange={(event) => updateSelected({text: event.target.value})} /></label>}
            {selected.type === "IMAGE" && <label className="grid gap-1 text-xs font-bold">定位<select className="rounded-lg border border-[#d7dde7] p-2 font-normal" value={selected.fit ?? "contain"} onChange={(event) => updateSelected({fit: event.target.value as "contain" | "cover" | "manual"})}><option value="contain">contain</option><option value="cover">cover</option><option value="manual">manual</option></select></label>}
            <div className="grid grid-cols-2 gap-2"><Button variant="secondary" size="sm" onClick={() => updateSelected({locked: !selected.locked})}>{selected.locked ? <Unlock className="h-3 w-3" /> : <Lock className="h-3 w-3" />}{selected.locked ? "解锁" : "锁定"}</Button><Button variant="secondary" size="sm" onClick={() => updateSelected({visible: !selected.visible})}>{selected.visible ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}{selected.visible ? "隐藏" : "显示"}</Button></div>
          </div> : <p className="mt-4 text-xs leading-5 text-[#7b8698]">选择画布或图层列表中的对象进行编辑。</p>}
          <div className="mt-5 rounded-lg bg-[#f3f6fa] p-3 text-xs leading-5 text-[#657187]">尺寸、重量和参数只读取 Product / SKU 数据，不允许 AI 或模板自行推测。</div>
          {message && <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">{message}</div>}
        </aside>}
      </div>
    </div>
  );
}

function Field({label, value, onChange}: {label: string; value: number; onChange: (value: number) => void}) {
  return <label className="grid grid-cols-[72px_1fr] items-center gap-2 text-xs font-bold"><span>{label}</span><input type="number" className="rounded-lg border border-[#d7dde7] p-2 font-normal" value={Number(value.toFixed(2))} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
