"use client";

import type {EcommerceTemplate} from "@ecommerce-visual-workbench/templates";
import {Badge, Button, Card, cn} from "@ecommerce-visual-workbench/ui";
import {ArrowUpRight, Box, Copy, Grid3X3, Layers3, Ruler, ScanLine} from "lucide-react";
import Link from "next/link";

const labels = {
  MAIN: "主图",
  DETAIL: "详情",
  DIMENSION: "尺寸",
  SELLING_POINT: "卖点",
  PARAMETER: "参数",
  PACKAGE: "包装",
  COMPARE: "对比",
};

const icons = {MAIN: ScanLine, DETAIL: Grid3X3, DIMENSION: Ruler, SELLING_POINT: Layers3, PARAMETER: Grid3X3, PACKAGE: Box, COMPARE: Copy};

export function TemplateCenter({templates, demo}: {templates: EcommerceTemplate[]; demo: boolean}) {
  return (
    <div className="mx-auto max-w-[1560px] space-y-5 p-5 lg:p-8">
      <section className="grid gap-4 lg:grid-cols-[1fr_330px]">
        <Card className="crop-corners relative overflow-hidden bg-[#172033] p-6 text-white lg:p-8">
          <div className="relative z-10 max-w-2xl">
            <p className="utility-face text-[10px] tracking-[.16em] text-[#ff8a65]">CALIBRATED TEMPLATE LIBRARY</p>
            <h2 className="display-face mt-4 text-3xl font-bold leading-tight lg:text-4xl">把审核通过的商品图，装配成精确成品</h2>
            <p className="mt-4 max-w-xl text-sm leading-6 text-[#abb5c6]">模板只处理排版、尺寸线和真实商品参数。商品颜色、纹理、形状、Logo 与包装文字保持原样。</p>
          </div>
          <div className="absolute -bottom-24 -right-16 h-72 w-72 rounded-full border border-white/10" />
          <div className="absolute -bottom-10 -right-4 h-44 w-44 rounded-full border border-[#ff6433]/60" />
        </Card>
        <Card className="flex flex-col justify-between p-6">
          <div>
            <div className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">LIBRARY HEALTH</div>
            <div className="mt-4 flex items-end gap-3"><span className="display-face text-5xl font-bold">{String(templates.length).padStart(2, "0")}</span><span className="pb-1 text-sm text-[#7a8598]">个版本化模板</span></div>
          </div>
          <div className="mt-8 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-[#f3f6fa] p-3"><strong className="block text-lg">{templates.filter((item) => item.status === "ACTIVE").length}</strong>已发布</div>
            <div className="rounded-lg bg-[#fff4ef] p-3"><strong className="block text-lg text-[#d94e22]">{templates.reduce((sum, item) => sum + item.versions.length, 0)}</strong>历史版本</div>
          </div>
        </Card>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {templates.map((template) => {
          const Icon = icons[template.template_type];
          const version = template.latest_version;
          return (
            <Card key={template.id} className="group overflow-hidden p-0">
              <div className="relative grid aspect-[16/9] place-items-center overflow-hidden border-b border-[#e1e6ed] bg-[#edf1f6]">
                <div className="absolute inset-0 opacity-50 [background-image:linear-gradient(#dce2ea_1px,transparent_1px),linear-gradient(90deg,#dce2ea_1px,transparent_1px)] [background-size:24px_24px]" />
                <div className="relative grid h-36 w-36 place-items-center bg-white shadow-[0_18px_45px_rgba(23,32,51,.12)] transition-transform group-hover:scale-[1.03]">
                  <Icon className="h-10 w-10 text-[#ff6433]" />
                  <span className="utility-face absolute bottom-3 text-[8px] tracking-[.14em] text-[#8a94a6]">{template.code}</span>
                </div>
                <Badge className={cn("absolute left-4 top-4", template.status === "ACTIVE" && "border-emerald-200 bg-emerald-50 text-emerald-700")}>{template.status}</Badge>
              </div>
              <div className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div><span className="utility-face text-[10px] text-[#8a94a6]">{labels[template.template_type]} · V{version?.version ?? 0}</span><h3 className="mt-1 font-bold">{template.name}</h3></div>
                  <Button variant="secondary" size="sm" asChild><Link href={`/templates/${template.id}/edit`} aria-label={`编辑${template.name}`}><ArrowUpRight className="h-4 w-4" /></Link></Button>
                </div>
                <div className="mt-4 flex items-center justify-between border-t border-[#e8ebf0] pt-4 text-xs text-[#7d8899]"><span>{version?.canvas_width} × {version?.canvas_height}px</span><code>{template.code}</code></div>
              </div>
            </Card>
          );
        })}
      </section>
      {demo && <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">当前展示首批 6 个内置模板；API 可用后会自动读取数据库中的模板与版本。</div>}
    </div>
  );
}
