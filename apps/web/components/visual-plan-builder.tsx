"use client";

import type {EcommerceTemplate} from "@ecommerce-visual-workbench/templates";
import { Badge, Button, Card, cn } from "@ecommerce-visual-workbench/ui";
import { CheckCircle2, ClipboardList, Minus, Plus, Save, Target } from "lucide-react";
import { useMemo, useState } from "react";

import {
  apiUrl,
  type Platform,
  type PlatformRuleVersion,
  type Product,
  type ProductVisualPlan,
} from "@/lib/api";

const types = ["MAIN", "DETAIL", "DIMENSION", "SCENE", "USAGE", "PACKAGE", "CLOSEUP"] as const;
const labels: Record<(typeof types)[number], string> = {
  MAIN: "主图",
  DETAIL: "详情图",
  DIMENSION: "尺寸图",
  SCENE: "场景图",
  USAGE: "使用图",
  PACKAGE: "包装图",
  CLOSEUP: "细节图",
};
const defaults = {MAIN: 5, DETAIL: 6, DIMENSION: 2, SCENE: 3, USAGE: 2, PACKAGE: 1, CLOSEUP: 2};

export function VisualPlanBuilder({
  products,
  platforms,
  rules,
  templates,
  initialPlans,
  initialProductId,
  demo,
}: {
  products: Product[];
  platforms: Platform[];
  rules: PlatformRuleVersion[];
  templates: EcommerceTemplate[];
  initialPlans: ProductVisualPlan[];
  initialProductId?: string;
  demo: boolean;
}) {
  const [plans, setPlans] = useState(initialPlans);
  const [productId, setProductId] = useState(initialProductId ?? products[0]?.id ?? "");
  const [platformId, setPlatformId] = useState(platforms[0]?.id ?? "");
  const [counts, setCounts] = useState<Record<(typeof types)[number], number>>(defaults);
  const [message, setMessage] = useState<string | null>(null);
  const [templateBindings, setTemplateBindings] = useState<Record<string, string>>(() => ({
    MAIN: templates.find((item) => item.code === "MAIN_WHITE_01")?.id ?? "",
    DETAIL: templates.find((item) => item.code === "SELLING_POINT_01")?.id ?? "",
    DIMENSION: templates.find((item) => item.code === "DIMENSION_BASIC_01")?.id ?? "",
    PACKAGE: templates.find((item) => item.code === "PACKAGE_01")?.id ?? "",
    CLOSEUP: templates.find((item) => item.code === "DETAIL_CLOSEUP_01")?.id ?? "",
  }));
  const platform = platforms.find((item) => item.id === platformId) ?? platforms[0];
  const eligibleRules = rules.filter((rule) => rule.platform === platform?.code);
  const [ruleVersionId, setRuleVersionId] = useState(rules[0]?.id ?? "");
  const selectedRule = eligibleRules.find((rule) => rule.id === ruleVersionId) ?? eligibleRules[0];
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const preview = useMemo(
    () => types.flatMap((type) => Array.from({length: counts[type]}, (_, index) => ({type, code: `${type}_${String(index + 1).padStart(2, "0")}`}))),
    [counts],
  );

  function adjust(type: (typeof types)[number], delta: number) {
    setCounts((current) => ({...current, [type]: Math.max(0, Math.min(50, current[type] + delta))}));
  }

  async function savePlan() {
    if (!productId || !platform || !selectedRule) {
      setMessage("请先选择商品、平台和有效规则版本。 ");
      return;
    }
    const requested_outputs = Object.fromEntries(Object.entries(counts).filter(([, count]) => count > 0));
    const product = products.find((item) => item.id === productId);
    const payload = {
      product_id: productId,
      platform_id: platform.id,
      rule_version_id: selectedRule.id,
      name: `${platform.name} ${selectedRule.market} 视觉方案`,
      market: selectedRule.market,
      category: product?.category ?? selectedRule.category,
      requested_outputs,
      slots: preview.map((slot, index) => ({
        code: slot.code,
        image_type: slot.type,
        label: null,
        template_id: templateBindings[slot.type] || null,
        position: index + 1,
      })),
    };
    if (demo) {
      setPlans((current) => [{
        ...payload,
        id: `local-plan-${Date.now()}`,
        slots: preview.map((slot, index) => ({id: `local-slot-${index}`, code: slot.code, image_type: slot.type, position: index + 1, label: null, template_id: templateBindings[slot.type] || null})),
        created_at: new Date().toISOString(),
      }, ...current]);
      setMessage("演示方案已生成；连接 API 后会固定到所选规则版本。 ");
      return;
    }
    const response = await fetch(`${apiUrl}/visual-plans`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setMessage((await response.json()).detail ?? "视觉方案创建失败");
      return;
    }
    const created = (await response.json()) as ProductVisualPlan;
    setPlans((current) => [created, ...current]);
    setMessage("视觉方案已保存，所有槽位已确定性生成。 ");
  }

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 p-5 lg:p-8">
      <section className="grid gap-5 2xl:grid-cols-[420px_1fr]">
        <Card className="p-0">
          <div className="border-b border-[#e3e7ee] p-5"><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">PLAN CONTEXT</p><h2 className="display-face mt-1 text-xl font-bold">定义投放上下文</h2></div>
          <div className="grid gap-4 p-5">
            <SelectField label="商品" value={productId} onChange={setProductId} options={products.map((item) => ({value: item.id, label: item.name}))} />
            <SelectField label="平台" value={platformId} onChange={(value) => {setPlatformId(value); const code = platforms.find((item) => item.id === value)?.code; setRuleVersionId(rules.find((rule) => rule.platform === code)?.id ?? "");}} options={platforms.map((item) => ({value: item.id, label: item.name}))} />
            <SelectField label="规则版本" value={selectedRule?.id ?? ""} onChange={setRuleVersionId} options={eligibleRules.map((rule) => ({value: rule.id, label: `${rule.image_slot} · v${rule.version} · ${rule.market}`}))} />
            {selectedRule && (
              <div className="crop-corners bg-[#f7f9fc] p-4">
                <div className="flex items-center justify-between"><Badge>{selectedRule.market} / {selectedRule.category}</Badge><span className="utility-face text-[10px]">{selectedRule.effective_date}</span></div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-xs"><div><span className="text-[#8a94a6]">画布下限</span><strong className="mt-1 block">{selectedRule.min_width} × {selectedRule.min_height}</strong></div><div><span className="text-[#8a94a6]">比例</span><strong className="mt-1 block">{selectedRule.ratio}</strong></div></div>
              </div>
            )}
            <div className="rounded-lg border border-[#e0e5ed] bg-[#fffaf8] p-4 text-xs leading-5 text-[#7a5549]">方案会固定到当前 RuleVersion。未来规则更新不会改变已创建方案，便于复核与复现。</div>
          </div>
        </Card>

        <Card className="p-0">
          <div className="flex items-center justify-between border-b border-[#e3e7ee] p-5"><div><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">OUTPUT MATRIX</p><h2 className="display-face mt-1 text-xl font-bold">图片生产清单</h2></div><div className="text-right"><div className="display-face text-3xl font-bold">{total}</div><div className="text-[10px] text-[#8a94a6]">TOTAL SLOTS</div></div></div>
          <div className="grid gap-px bg-[#e3e7ee] sm:grid-cols-2 xl:grid-cols-4">
            {types.map((type, index) => (
              <div key={type} className={cn("bg-white p-5", index === 0 && "bg-[#fff7f3]") }>
                <div className="flex items-start justify-between"><div><span className="utility-face text-[10px] text-[#8a94a6]">{type}</span><h3 className="mt-1 font-bold">{labels[type]}</h3></div><span className="display-face text-3xl font-bold text-[#263149]">{String(counts[type]).padStart(2, "0")}</span></div>
                <div className="mt-5 flex items-center gap-2"><button onClick={() => adjust(type, -1)} className="grid h-8 w-8 place-items-center rounded-lg border border-[#dce2eb]" aria-label={`减少${labels[type]}`}><Minus className="h-3.5 w-3.5" /></button><div className="h-1 flex-1 rounded-full bg-[#edf0f4]"><div className="h-full rounded-full bg-[#ff6433]" style={{width: `${Math.min(100, counts[type] * 12)}%`}} /></div><button onClick={() => adjust(type, 1)} className="grid h-8 w-8 place-items-center rounded-lg border border-[#dce2eb]" aria-label={`增加${labels[type]}`}><Plus className="h-3.5 w-3.5" /></button></div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e3e7ee] p-5"><p className="text-xs text-[#738094]">数量变更会重新展开槽位；不会创建图片，也不会调用 AI。</p><Button onClick={savePlan}><Save className="h-4 w-4" />保存视觉方案</Button></div>
        </Card>
      </section>

      <Card className="p-0">
        <div className="border-b border-[#e3e7ee] p-5"><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">TEMPLATE ROUTING</p><h2 className="display-face mt-1 text-xl font-bold">槽位模板绑定</h2><p className="mt-1 text-xs text-[#7c8799]">方案保存模板 ID；实际渲染仍固定到当时选择的 TemplateVersion。</p></div>
        <div className="grid gap-px bg-[#e3e7ee] sm:grid-cols-2 lg:grid-cols-4">
          {types.map((type) => <label key={type} className="grid gap-2 bg-white p-4 text-xs font-bold"><span>{type} · {labels[type]}</span><select className="rounded-lg border border-[#d7dde7] bg-white p-2 font-normal" value={templateBindings[type] ?? ""} onChange={(event) => setTemplateBindings((current) => ({...current, [type]: event.target.value}))}><option value="">不绑定模板</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.code}</option>)}</select></label>)}
        </div>
      </Card>

      <section className="grid gap-5 xl:grid-cols-[1fr_420px]">
        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-[#e3e7ee] p-5"><div><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">ASSET SLOT MAP</p><h2 className="display-face mt-1 text-xl font-bold">确定性槽位预览</h2></div><Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">{preview.length} 个待生产位置</Badge></div>
          <div className="grid gap-2 p-5 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
            {preview.map((slot) => <div key={slot.code} className="rounded-lg border border-[#dfe4ec] bg-[#f8fafc] p-3"><div className="flex items-center justify-between"><Target className="h-3.5 w-3.5 text-[#ff6433]" /><span className="h-1.5 w-1.5 rounded-full bg-[#cbd2dc]" /></div><div className="utility-face mt-5 text-[11px] font-bold">{slot.code}</div><div className="mt-1 text-[10px] text-[#8a94a6]">{labels[slot.type]}</div></div>)}
          </div>
        </Card>

        <Card className="p-0">
          <div className="border-b border-[#e3e7ee] p-5"><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">SAVED PLANS</p><h2 className="display-face mt-1 text-xl font-bold">已保存方案</h2></div>
          <div className="divide-y divide-[#e8ebf0]">
            {plans.slice(0, 4).map((plan) => <div key={plan.id} className="p-5"><div className="flex items-start gap-3"><div className="rounded-lg bg-[#eef2f7] p-2"><ClipboardList className="h-4 w-4" /></div><div className="min-w-0 flex-1"><h3 className="truncate text-sm font-bold">{plan.name}</h3><p className="mt-1 text-xs text-[#7c8799]">{plan.market} · {Object.values(plan.requested_outputs).reduce((sum, count) => sum + count, 0)} 个槽位</p><div className="mt-3 flex flex-wrap gap-1">{Object.entries(plan.requested_outputs).slice(0, 4).map(([type, count]) => <Badge key={type}>{type} × {count}</Badge>)}</div></div><CheckCircle2 className="h-4 w-4 text-emerald-600" /></div></div>)}
          </div>
        </Card>
      </section>
      {message && <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{message}</div>}
    </div>
  );
}

function SelectField({label, value, onChange, options}: {label: string; value: string; onChange: (value: string) => void; options: {value: string; label: string}[]}) {
  return <label className="grid gap-1.5 text-xs font-bold text-[#667085]">{label}<select value={value} onChange={(event) => onChange(event.target.value)} className="rounded-lg border border-[#d7dde7] bg-white px-3 py-2.5 text-sm font-normal text-[#172033] outline-none focus:border-[#ff6433]">{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}
