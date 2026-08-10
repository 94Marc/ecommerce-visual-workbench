"use client";

import { Badge, Button, Card, cn } from "@ecommerce-visual-workbench/ui";
import { Check, CircleOff, Plus, Ruler, ShieldCheck, X } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import {apiUrl, type Platform, type PlatformCode, type PlatformRuleVersion} from "@/lib/api";

const slots = ["MAIN", "DETAIL", "DIMENSION", "SCENE", "USAGE", "PACKAGE", "CLOSEUP"];

export function PlatformRuleCenter({platforms, initialRules, demo}: {platforms: Platform[]; initialRules: PlatformRuleVersion[]; demo: boolean}) {
  const [rules, setRules] = useState(initialRules);
  const [selected, setSelected] = useState<PlatformCode | "all">("temu");
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState("");
  const visible = useMemo(() => rules.filter((rule) => selected === "all" || rule.platform === selected), [rules, selected]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const imageSlot = String(form.get("image_slot"));
    const payload = {
      platform: form.get("platform"), market: form.get("market"), category: form.get("category"),
      image_slot: imageSlot, image_type: imageSlot, version: form.get("version"), effective_date: form.get("effective_date"),
      min_width: Number(form.get("min_width")), min_height: Number(form.get("min_height")), ratio: form.get("ratio"),
      max_size: Number(form.get("max_size")) * 1024 * 1024, text_allowed: form.get("text_allowed") === "on", watermark_allowed: false,
    };
    let created: PlatformRuleVersion;
    if (demo) {
      created = {...payload, id: `local-${Date.now()}`, platform_rule_id: `local-${Date.now()}`, platform: payload.platform as PlatformCode,
        market: String(payload.market), category: String(payload.category), image_slot: imageSlot, image_type: imageSlot,
        version: String(payload.version), rule_version: String(payload.version), effective_date: String(payload.effective_date),
        ratio: String(payload.ratio), min_width: payload.min_width, min_height: payload.min_height, max_size: payload.max_size,
        text_allowed: payload.text_allowed, watermark_allowed: false, enabled: true};
    } else {
      const response = await fetch(`${apiUrl}/platform-rules`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
      if (!response.ok) {setMessage((await response.json()).detail ?? "规则创建失败"); return;}
      created = await response.json() as PlatformRuleVersion;
    }
    setRules((current) => [created, ...current]); setMessage(demo ? "演示规则已加入当前台账。" : "规则版本已创建。 "); setEditing(false);
  }

  return <div className="mx-auto max-w-[1560px] space-y-5 p-5 lg:p-8">
    <section className="grid gap-4 md:grid-cols-3">
      <Metric label="规则定义" value={new Set(visible.map((rule) => rule.platform_rule_id)).size} note="平台 / 市场 / 类目 / 槽位" icon={<Ruler />} />
      <Metric label="有效版本" value={visible.filter((rule) => rule.enabled).length} note="任务固定具体版本" icon={<ShieldCheck />} />
      <Metric label="平台覆盖" value={platforms.length} note="五平台统一框架" icon={<Check />} />
    </section>
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#e2e7ef] p-5"><div><p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">RULE LEDGER / EFFECTIVE VERSIONS</p><h2 className="display-face mt-1 text-xl font-bold">平台规则台账</h2></div><div className="flex gap-2"><select value={selected} onChange={(event) => setSelected(event.target.value as PlatformCode | "all")} className="rounded-lg border border-[#d7dde7] bg-white px-3 py-2 text-sm"><option value="all">全部平台</option>{platforms.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select><Button onClick={() => setEditing(true)}><Plus className="h-4 w-4" />新增规则版本</Button></div></div>
      <div className="grid grid-cols-2 gap-px bg-[#e3e7ee] md:grid-cols-5">{platforms.map((item) => <button key={item.code} onClick={() => setSelected(item.code)} className={cn("bg-white p-4 text-left", selected === item.code && "bg-[#fff5f1]")}><span className="font-bold">{item.name}</span><span className="utility-face mt-2 block text-[10px] text-[#8a94a6]">{rules.filter((rule) => rule.platform === item.code).length} VERSIONS</span></button>)}</div>
      <div className="overflow-x-auto"><table className="w-full min-w-[1000px] text-left text-sm"><thead className="bg-[#f7f9fc] text-[10px] uppercase tracking-wider text-[#8490a3]"><tr>{["作用域", "槽位", "尺寸 / 比例", "上限", "文字", "水印", "版本", "生效日期"].map((label) => <th key={label} className="px-5 py-3">{label}</th>)}</tr></thead><tbody className="divide-y divide-[#e8ebf0]">{visible.map((rule) => <tr key={rule.id} className="hover:bg-[#fafbfd]"><td className="px-5 py-4"><strong className="capitalize">{rule.platform.replace("_", " ")}</strong><div className="mt-1 text-xs text-[#7b8698]">{rule.market} / {rule.category}</div></td><td className="px-5 py-4"><Badge>{rule.image_slot}</Badge></td><td className="utility-face px-5 py-4 text-xs">{rule.min_width} × {rule.min_height} · {rule.ratio}</td><td className="px-5 py-4">{rule.max_size ? `${Math.round(rule.max_size / 1048576)} MB` : "—"}</td><Policy value={rule.text_allowed} /><Policy value={rule.watermark_allowed} /><td className="utility-face px-5 py-4 font-bold">v{rule.version}</td><td className="px-5 py-4 text-[#667085]">{rule.effective_date}</td></tr>)}</tbody></table></div>
    </Card>
    {message && <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{message}</div>}
    {editing && <div className="fixed inset-0 z-50 grid place-items-center bg-[#151c2c]/55 p-4"><Card className="w-full max-w-2xl p-0"><div className="flex items-center justify-between border-b border-[#e3e7ee] px-5 py-4"><div><p className="utility-face text-[10px] text-[#8a94a6]">APPEND-ONLY VERSION</p><h3 className="display-face text-xl font-bold">新增规则版本</h3></div><button onClick={() => setEditing(false)}><X className="h-5 w-5" /></button></div><form onSubmit={submit} className="grid gap-4 p-5 sm:grid-cols-2"><Field label="平台"><select name="platform" defaultValue={selected === "all" ? "temu" : selected}>{platforms.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></Field><Field label="市场"><input name="market" defaultValue="US" required /></Field><Field label="类目"><input name="category" defaultValue="*" required /></Field><Field label="图片槽位"><select name="image_slot">{slots.map((slot) => <option key={slot}>{slot}</option>)}</select></Field><Field label="版本"><input name="version" defaultValue="1.0.0" required /></Field><Field label="生效日期"><input name="effective_date" type="date" defaultValue="2026-08-10" required /></Field><Field label="最小宽度"><input name="min_width" type="number" defaultValue="1600" required /></Field><Field label="最小高度"><input name="min_height" type="number" defaultValue="1600" required /></Field><Field label="比例"><input name="ratio" defaultValue="1:1" required /></Field><Field label="文件上限 MB"><input name="max_size" type="number" defaultValue="5" required /></Field><label className="flex items-center gap-2 text-sm"><input name="text_allowed" type="checkbox" />允许文字</label><div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" variant="secondary" onClick={() => setEditing(false)}>取消</Button><Button type="submit">创建版本</Button></div></form></Card></div>}
  </div>;
}

function Metric({label, value, note, icon}: {label: string; value: number; note: string; icon: React.ReactNode}) {return <Card className="flex justify-between"><div><p className="text-xs text-[#7c8799]">{label}</p><div className="display-face mt-2 text-3xl font-bold">{String(value).padStart(2, "0")}</div><p className="mt-2 text-xs text-[#8a94a6]">{note}</p></div><div className="h-fit rounded-lg bg-[#fff2ed] p-2 text-[#e65327] [&_svg]:h-4 [&_svg]:w-4">{icon}</div></Card>}
function Policy({value}: {value: boolean}) {return <td className="px-5 py-4">{value ? <span className="inline-flex items-center gap-1 text-emerald-700"><Check className="h-3.5 w-3.5" />允许</span> : <span className="inline-flex items-center gap-1 text-[#9a6570]"><CircleOff className="h-3.5 w-3.5" />禁止</span>}</td>}
function Field({label, children}: {label: string; children: React.ReactNode}) {return <label className="grid gap-1.5 text-xs font-bold text-[#667085]">{label}<div className="[&_input]:w-full [&_input]:rounded-lg [&_input]:border [&_input]:border-[#d7dde7] [&_input]:px-3 [&_input]:py-2.5 [&_select]:w-full [&_select]:rounded-lg [&_select]:border [&_select]:border-[#d7dde7] [&_select]:bg-white [&_select]:px-3 [&_select]:py-2.5">{children}</div></label>}
