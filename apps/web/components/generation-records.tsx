"use client";

import { Badge, Card, cn } from "@ecommerce-visual-workbench/ui";
import { Check, Clock3, Image as ImageIcon, ShieldAlert, X } from "lucide-react";
import { useMemo, useState } from "react";

import { AssetArtwork } from "@/components/asset-artwork";
import type { GenerationJob, QualityResult } from "@/lib/api";

const modeTone = {
  STRICT: "border-[#ff7448] bg-[#fff3ee] text-[#a43a18]",
  BALANCED: "border-[#4e7cad] bg-[#eef5fb] text-[#29577f]",
  CREATIVE: "border-[#8c70bd] bg-[#f5f0fb] text-[#654493]",
};

const qualityLabels = {
  product_similarity: "商品相似度",
  resolution: "分辨率",
  aspect_ratio: "图片比例",
  file_size: "文件大小",
  format: "文件格式",
  text_risk: "文字风险",
  watermark_risk: "水印风险",
};

function QualityCell({label, result}: {label: string; result?: QualityResult}) {
  const status = result?.status ?? "unavailable";
  const Icon = status === "passed" ? Check : status === "failed" ? X : ShieldAlert;
  return (
    <div className="border-b border-r border-[#e3e7ee] p-3 last:border-r-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-[#4f5b70]">{label}</span>
        <Icon className={cn("h-4 w-4", status === "passed" ? "text-emerald-600" : status === "failed" ? "text-rose-600" : "text-amber-600")} />
      </div>
      <p className="utility-face mt-2 text-[10px] uppercase tracking-[.08em] text-[#8b95a6]">{status}</p>
    </div>
  );
}

export function GenerationRecords({jobs, demo}: {jobs: GenerationJob[]; demo: boolean}) {
  const [selectedId, setSelectedId] = useState(jobs[0]?.id ?? "");
  const selected = useMemo(
    () => jobs.find((job) => job.id === selectedId) ?? jobs[0],
    [jobs, selectedId],
  );
  const quality = selected?.quality_check;

  return (
    <div className="mx-auto grid max-w-[1580px] gap-5 p-5 lg:grid-cols-[330px_1fr] lg:p-8">
      <Card className="h-fit overflow-hidden p-0">
        <div className="border-b border-[#e2e6ed] p-5">
          <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">GENERATION LEDGER</p>
          <div className="mt-1 flex items-center justify-between">
            <h2 className="display-face text-xl font-bold">生成记录</h2>
            <Badge>{jobs.length} 条</Badge>
          </div>
        </div>
        <div className="divide-y divide-[#e7eaf0]">
          {jobs.map((job) => (
            <button
              key={job.id}
              onClick={() => setSelectedId(job.id)}
              className={cn(
                "w-full p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#ff6433]",
                selected?.id === job.id ? "bg-[#fff6f2]" : "hover:bg-[#f8fafc]",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="utility-face text-xs font-bold">{job.image_slot}</span>
                <span className={cn("rounded border px-2 py-0.5 text-[9px] font-bold", modeTone[job.generation_mode ?? "STRICT"])}>{job.generation_mode ?? "STRICT"}</span>
              </div>
              <p className="mt-2 truncate text-xs text-[#657187]">{job.provider ?? "—"} / {job.provider_model ?? "default"}</p>
              <div className="mt-2 flex items-center justify-between text-[10px] text-[#929baa]">
                <span>{job.status}</span>
                <span>{job.retry_count ?? 0} retries</span>
              </div>
            </button>
          ))}
        </div>
      </Card>

      {selected ? (
        <div className="space-y-5">
          <Card className="overflow-hidden p-0">
            <div className="grid gap-0 border-b border-[#dfe4ec] lg:grid-cols-[1fr_auto]">
              <div className="p-5 lg:p-6">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn("rounded border px-2.5 py-1 text-[10px] font-bold", modeTone[selected.generation_mode ?? "STRICT"])}>{selected.generation_mode ?? "STRICT"} FIDELITY</span>
                  <Badge>{selected.platform}</Badge>
                  <Badge>{selected.image_slot}</Badge>
                </div>
                <h2 className="display-face mt-3 text-3xl font-bold">{selected.provider ?? "未分配 Provider"}</h2>
                <p className="utility-face mt-2 text-[11px] text-[#7c8799]">REQUEST / {selected.provider_request_id ?? "pending"}</p>
              </div>
              <div className="grid grid-cols-2 border-t border-[#dfe4ec] lg:border-l lg:border-t-0">
                <div className="min-w-32 p-5">
                  <Clock3 className="h-4 w-4 text-[#ff6433]" />
                  <p className="utility-face mt-2 text-xl font-bold">{selected.duration_ms ? `${(selected.duration_ms / 1000).toFixed(1)}s` : "—"}</p>
                  <p className="text-[10px] text-[#8a94a6]">总耗时</p>
                </div>
                <div className="min-w-32 border-l border-[#dfe4ec] p-5">
                  <ShieldAlert className="h-4 w-4 text-[#ff6433]" />
                  <p className="utility-face mt-2 text-xl font-bold">{selected.retry_count ?? 0}</p>
                  <p className="text-[10px] text-[#8a94a6]">重试次数</p>
                </div>
              </div>
            </div>

            <div className="grid lg:grid-cols-[210px_1fr]">
              <aside className="border-b border-[#dfe4ec] bg-[#f8fafc] p-5 lg:border-b-0 lg:border-r">
                <p className="utility-face text-[10px] tracking-[.12em] text-[#8a94a6]">REFERENCE ANGLES</p>
                <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-1">
                  {(selected.reference_asset_version_ids ?? []).map((versionId, index) => (
                    <div key={versionId} className="overflow-hidden rounded-lg border border-[#dce2ea] bg-white">
                      <AssetArtwork type="ORIGINAL" versionId={versionId} demo={demo} className="min-h-24" />
                      <p className="utility-face truncate px-2 py-1.5 text-[9px] text-[#7f899a]">REF {String(index + 1).padStart(2, "0")} / {versionId}</p>
                    </div>
                  ))}
                  {!selected.reference_asset_version_ids?.length && <p className="text-xs text-[#8b95a6]">未记录参考图</p>}
                </div>
              </aside>

              <div className="relative p-5 lg:p-6">
                <div className="absolute bottom-6 left-[31px] top-6 w-px bg-[#d9dfe8]" aria-hidden />
                <div className="relative space-y-5">
                  <TraceStep label="01 / ORIGINAL PROMPT" text={selected.prompt ?? "未记录 Prompt"} />
                  <TraceStep label="02 / REVISED PROMPT" text={selected.revised_prompt ?? "没有修订；当前任务使用原始 Prompt。"} muted={!selected.revised_prompt} />
                  <TraceStep label="03 / OUTPUT VERSION" text={selected.output_version_id ?? "等待输出 AssetVersion"} mono />
                  <TraceStep label="04 / REVIEW" text={selected.review_result ? `${selected.review_result.decision}${selected.review_result.reason ? ` · ${selected.review_result.reason}` : ""}${selected.review_result.comment ? ` — ${selected.review_result.comment}` : ""}` : "等待人工审核"} />
                </div>
              </div>
            </div>
          </Card>

          <Card className="overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-[#dfe4ec] px-5 py-4">
              <div>
                <p className="utility-face text-[10px] tracking-[.12em] text-[#8a94a6]">QUALITY GATE</p>
                <h3 className="display-face mt-1 text-xl font-bold">真实性与平台质量检查</h3>
              </div>
              <Badge className={quality?.review_required ? "border-amber-200 bg-amber-50 text-amber-700" : ""}>{quality?.review_required ? "需要人工审核" : "等待检查"}</Badge>
            </div>
            <div className="grid grid-cols-2 border-l border-t border-[#e3e7ee] sm:grid-cols-4 lg:grid-cols-7">
              {Object.entries(qualityLabels).map(([key, label]) => <QualityCell key={key} label={label} result={quality?.[key as keyof typeof qualityLabels] as QualityResult | undefined} />)}
            </div>
          </Card>
        </div>
      ) : (
        <Card className="grid min-h-[520px] place-items-center text-sm text-[#7d8798]">尚无生成记录。</Card>
      )}
    </div>
  );
}

function TraceStep({label, text, muted, mono}: {label: string; text: string; muted?: boolean; mono?: boolean}) {
  return (
    <section className="relative pl-11">
      <span className="absolute left-0 top-0 grid h-5 w-5 place-items-center rounded-full border-2 border-white bg-[#ff6433] shadow-[0_0_0_1px_#ccd3dd]">
        <ImageIcon className="h-2.5 w-2.5 text-white" />
      </span>
      <p className="utility-face text-[10px] tracking-[.12em] text-[#8a94a6]">{label}</p>
      <p className={cn("mt-2 whitespace-pre-wrap text-sm leading-6 text-[#3f4b60]", muted && "text-[#929baa]", mono && "utility-face text-xs")}>{text}</p>
    </section>
  );
}
