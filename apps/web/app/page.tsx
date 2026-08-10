import { Badge, Button, Card, cn } from "@ecommerce-visual-workbench/ui";
import {
  Archive,
  Boxes,
  ChevronRight,
  CircleCheck,
  Clock3,
  Download,
  Image as ImageIcon,
  LayoutTemplate,
  Plus,
  ScanLine,
  Settings2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { EditorPreview } from "@/components/editor-preview";
import { loadWorkbench, summarizeJobs } from "@/lib/api";

const navigation = [
  ["生产台", ScanLine],
  ["商品中心", Boxes],
  ["图片资产", ImageIcon],
  ["模板库", LayoutTemplate],
  ["审核队列", ShieldCheck],
  ["导出记录", Archive],
] as const;

const slots = [
  ["主图", "MAIN", "ready"],
  ["场景图", "SCENE", "working"],
  ["尺寸图", "DIMENSION", "queued"],
  ["详情图", "DETAIL", "empty"],
  ["包装图", "PACKAGE", "empty"],
  ["细节图", "CLOSEUP", "empty"],
] as const;

export default async function WorkbenchPage() {
  const {products, jobs, demo} = await loadWorkbench();
  const summary = summarizeJobs(jobs);
  const activeProduct = products[0];

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[238px_1fr]">
      <aside className="bg-[#151c2c] px-4 py-5 text-white lg:sticky lg:top-0 lg:h-screen">
        <div className="flex items-center gap-3 px-2">
          <div className="crop-corners grid h-10 w-10 place-items-center bg-white/5">
            <ScanLine className="h-5 w-5 text-[#ff7448]" />
          </div>
          <div>
            <div className="display-face text-lg font-bold leading-none">FRAMEFLOW</div>
            <div className="utility-face mt-1 text-[9px] tracking-[.16em] text-[#8994aa]">VISUAL OPS / CN</div>
          </div>
        </div>

        <nav className="mt-9 grid grid-cols-3 gap-2 lg:block lg:space-y-1">
          {navigation.map(([label, Icon], index) => (
            <a
              key={label}
              href="#"
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                index === 0 ? "bg-white text-[#172033]" : "text-[#9ba6ba] hover:bg-white/5 hover:text-white",
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
              {index === 4 && <span className="ml-auto rounded-full bg-[#ff6433] px-1.5 text-[10px] text-white">2</span>}
            </a>
          ))}
        </nav>

        <div className="mt-9 hidden border-t border-white/10 pt-5 lg:block">
          <div className="mb-2 flex items-center justify-between text-xs text-[#8994aa]"><span>本月生产额度</span><span>68%</span></div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full w-[68%] bg-[#ff6433]" /></div>
          <button className="mt-6 flex items-center gap-3 text-sm text-[#8994aa]"><Settings2 className="h-4 w-4" />工作区设置</button>
        </div>
      </aside>

      <main className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#dfe4ec] bg-white px-5 py-4 lg:px-8">
          <div>
            <div className="utility-face text-[10px] tracking-[.12em] text-[#8a94a6]">MON · 10 AUG · TEMU US</div>
            <h1 className="display-face mt-1 text-2xl font-bold">视觉生产台</h1>
          </div>
          <div className="flex items-center gap-2">
            {demo && <Badge className="border-amber-200 bg-amber-50 text-amber-700">演示数据</Badge>}
            <Button variant="secondary"><Download className="h-4 w-4" />导出素材</Button>
            <Button><Plus className="h-4 w-4" />新建生产任务</Button>
          </div>
        </header>

        <div className="mx-auto max-w-[1560px] space-y-5 p-5 lg:p-8">
          <section className="grid gap-4 xl:grid-cols-[1.55fr_.75fr]">
            <Card className="overflow-hidden p-0">
              <div className="grid min-h-[196px] md:grid-cols-[1fr_310px]">
                <div className="p-6 lg:p-7">
                  <div className="flex items-center gap-2 text-xs font-bold text-[#ff6433]"><span className="signal-pulse h-2 w-2 rounded-full bg-[#ff6433]" />当前批次 · SKU 01/12</div>
                  <h2 className="display-face mt-4 max-w-xl text-3xl font-bold leading-[1.05] lg:text-4xl">{activeProduct?.name ?? "先创建一个商品"}</h2>
                  <p className="mt-3 text-sm text-[#667085]">{activeProduct?.category ?? "商品中心"} · {activeProduct?.material ?? "上传供应商素材后开始生产"}</p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    {activeProduct?.selling_points.map((point) => <Badge key={point}>{point}</Badge>)}
                  </div>
                </div>
                <div className="relative flex items-center justify-center overflow-hidden bg-[#e7ede8] p-6">
                  <div className="absolute inset-4 crop-corners opacity-70" />
                  <div className="h-32 w-24 rounded-[26px_26px_18px_18px] border-2 border-[#8ea293] bg-[#c6d4c8] shadow-[0_22px_30px_rgba(46,70,52,.16)]">
                    <div className="mx-auto mt-5 h-2 w-11 rounded-full bg-[#8ea293]" />
                    <div className="mx-auto mt-14 h-1 w-14 bg-white/70" />
                  </div>
                  <span className="utility-face absolute bottom-5 right-5 text-[10px] text-[#6c7d70]">ORIGINAL / V1</span>
                </div>
              </div>
            </Card>

            <Card className="grid grid-cols-2 divide-x divide-y divide-[#e5e9f0] overflow-hidden p-0">
              {[
                {label: "待处理", value: summary.pending, Icon: Clock3, color: "text-amber-600"},
                {label: "生产中", value: summary.processing, Icon: Sparkles, color: "text-[#ff6433]"},
                {label: "已完成", value: summary.completed, Icon: CircleCheck, color: "text-emerald-600"},
                {label: "商品数", value: products.length, Icon: Boxes, color: "text-blue-600"},
              ].map(({label, value, Icon, color}) => (
                <div key={label} className="p-5">
                  <Icon className={cn("h-4 w-4", color)} />
                  <div className="display-face mt-4 text-3xl font-bold">{String(value).padStart(2, "0")}</div>
                  <div className="mt-1 text-xs text-[#7c8799]">{label}</div>
                </div>
              ))}
            </Card>
          </section>

          <section className="grid gap-5 2xl:grid-cols-[1fr_480px]">
            <Card className="p-5 lg:p-6">
              <div className="flex items-end justify-between gap-4">
                <div><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">SLOT PRODUCTION</p><h2 className="display-face mt-1 text-xl font-bold">平台图片槽位</h2></div>
                <Badge className="border-[#ffd2c5] bg-[#fff4f0] text-[#c9431b]">Temu · US · 通用类目</Badge>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {slots.map(([label, code, state], index) => (
                  <button key={code} className={cn("group relative min-h-36 rounded-xl border p-4 text-left transition", index === 0 ? "border-[#ff6433] bg-[#fff8f5]" : "border-[#e0e5ed] bg-[#f8fafc] hover:border-[#b8c1cf]")}>
                    <div className="flex items-start justify-between"><span className="utility-face text-[10px] text-[#8a94a6]">{code}</span><span className={cn("h-2 w-2 rounded-full", state === "ready" && "bg-emerald-500", state === "working" && "signal-pulse bg-[#ff6433]", state === "queued" && "bg-amber-400", state === "empty" && "bg-[#cdd4df]")} /></div>
                    <div className="mt-10 text-base font-bold">{label}</div>
                    <div className="mt-1 text-xs text-[#7c8799]">{state === "ready" ? "待审核 · V1" : state === "working" ? "模拟生成中" : state === "queued" ? "队列第 2 位" : "尚未创建"}</div>
                    <ChevronRight className="absolute bottom-4 right-4 h-4 w-4 text-[#a6afbd] transition-transform group-hover:translate-x-1" />
                  </button>
                ))}
              </div>
            </Card>

            <Card className="p-5 lg:p-6">
              <div className="flex items-center justify-between"><div><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">KONVA TEMPLATE</p><h2 className="display-face mt-1 text-xl font-bold">主图安全区</h2></div><Badge>1600 × 1600</Badge></div>
              <div className="mt-5"><EditorPreview /></div>
              <div className="mt-4 flex items-center justify-between text-xs text-[#6c778a]"><span>橙色虚线内保留主体与卖点</span><button className="font-bold text-[#d94b20]">打开编辑器</button></div>
            </Card>
          </section>

          <Card className="overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-[#e3e7ee] px-5 py-4"><div><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">LIVE QUEUE</p><h2 className="display-face mt-1 text-lg font-bold">最近生产任务</h2></div><button className="text-xs font-bold text-[#5d687b]">查看全部</button></div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-[#f7f9fc] text-[10px] uppercase tracking-wider text-[#8490a3]"><tr><th className="px-5 py-3 font-semibold">任务</th><th className="px-5 py-3 font-semibold">平台</th><th className="px-5 py-3 font-semibold">图片槽位</th><th className="px-5 py-3 font-semibold">状态</th><th className="px-5 py-3 font-semibold">创建时间</th></tr></thead>
                <tbody className="divide-y divide-[#e8ebf0]">
                  {jobs.slice(0, 5).map((job) => <tr key={job.id} className="hover:bg-[#fafbfd]"><td className="utility-face px-5 py-4 text-xs text-[#667085]">{job.id.slice(0, 12)}</td><td className="px-5 py-4 font-bold capitalize">{job.platform.replace("_", " ")}</td><td className="px-5 py-4">{job.image_slot}</td><td className="px-5 py-4"><Badge className={cn(job.status === "completed" && "border-emerald-200 bg-emerald-50 text-emerald-700", job.status === "processing" && "border-orange-200 bg-orange-50 text-orange-700", job.status === "pending" && "border-amber-200 bg-amber-50 text-amber-700")}>{job.status}</Badge></td><td className="px-5 py-4 text-[#7b8698]">{new Date(job.created_at).toLocaleString("zh-CN", {hour12: false})}</td></tr>)}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
