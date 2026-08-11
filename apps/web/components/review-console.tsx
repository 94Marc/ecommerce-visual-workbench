"use client";

import { Badge, Button, Card, cn } from "@ecommerce-visual-workbench/ui";
import { Check, RotateCcw, X } from "lucide-react";
import { useMemo, useState } from "react";

import { AssetArtwork } from "@/components/asset-artwork";
import {
  latestVersion,
  rejectReasons,
  submitReview,
  type Asset,
  type AssetStatus,
  type RejectReason,
} from "@/lib/api";

const reasonLabels: Record<RejectReason, string> = {
  PRODUCT_CHANGED: "商品主体改变",
  WRONG_COLOR: "颜色错误",
  WRONG_TEXTURE: "纹理错误",
  WRONG_SHAPE: "形状错误",
  UNREALISTIC_USAGE: "使用方式不真实",
  AI_ARTIFACT: "AI 瑕疵",
  TEXT_ERROR: "文字错误",
  SIZE_ERROR: "尺寸错误",
  PACKAGING_ERROR: "包装错误",
  OTHER: "其他",
};

const statusLabels: Record<AssetStatus, string> = {
  DRAFT: "草稿",
  PROCESSING: "处理中",
  REVIEW: "待审核",
  APPROVED: "已通过",
  REJECTED: "已拒绝",
};

export function ReviewConsole({
  initialAssets,
  initialVersionId,
  demo,
}: {
  initialAssets: Asset[];
  initialVersionId?: string;
  demo: boolean;
}) {
  const reviewable = useMemo(
    () => initialAssets.filter((asset) => ["REVIEW", "REJECTED"].includes(latestVersion(asset).status)),
    [initialAssets],
  );
  const [statuses, setStatuses] = useState<Record<string, AssetStatus>>(
    Object.fromEntries(reviewable.map((asset) => [latestVersion(asset).id, latestVersion(asset).status])),
  );
  const initialSelection =
    reviewable.find((asset) => latestVersion(asset).id === initialVersionId)?.id ??
    reviewable[0]?.id ??
    "";
  const [selectedId, setSelectedId] = useState(initialSelection);
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState<RejectReason>("PRODUCT_CHANGED");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const selected = reviewable.find((asset) => asset.id === selectedId) ?? reviewable[0];

  async function decide(decision: "approved" | "rejected" | "regenerate") {
    if (!selected) return;
    const version = latestVersion(selected);
    setBusy(true);
    try {
      if (decision !== "approved" && !comment.trim()) {
        setMessage("拒绝或重新处理时必须填写修改意见。");
        return;
      }
      if (!demo) {
        await submitReview(
          version.id,
          decision,
          comment,
          decision === "approved" ? undefined : reason,
        );
      }
      const nextStatus: AssetStatus =
        decision === "approved" ? "APPROVED" : "REJECTED";
      setStatuses((current) => ({...current, [version.id]: nextStatus}));
      setMessage(
        decision === "approved"
          ? "图片已通过，可进入平台导出。"
          : decision === "regenerate"
            ? "已创建重新处理任务，原版本仍保留。"
            : "图片已拒绝，原因已写入审核记录。",
      );
      setComment("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "审核操作失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto grid max-w-[1560px] gap-5 p-5 lg:grid-cols-[320px_1fr] lg:p-8">
      <Card className="h-fit overflow-hidden p-0">
        <div className="border-b border-[#e2e6ed] p-5">
          <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">REVIEW QUEUE</p>
          <div className="mt-1 flex items-center justify-between">
            <h2 className="display-face text-xl font-bold">待审图片</h2>
            <Badge>{reviewable.length} 项</Badge>
          </div>
        </div>
        <div className="divide-y divide-[#e7eaf0]">
          {reviewable.map((asset) => {
            const version = latestVersion(asset);
            const status = statuses[version.id];
            return (
              <button
                key={asset.id}
                onClick={() => setSelectedId(asset.id)}
                className={cn(
                  "flex w-full items-center gap-3 p-4 text-left transition-colors",
                  selected?.id === asset.id ? "bg-[#fff6f2]" : "hover:bg-[#f8fafc]",
                )}
              >
                <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg">
                  <AssetArtwork type={asset.asset_type} versionId={version.id} demo={demo} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="utility-face text-xs font-bold">{asset.asset_type}</span>
                    <span className={cn("h-2 w-2 rounded-full", status === "REVIEW" ? "bg-blue-500" : status === "PROCESSING" ? "signal-pulse bg-orange-500" : status === "APPROVED" ? "bg-emerald-500" : "bg-rose-500")} />
                  </div>
                  <p className="mt-1 truncate text-xs text-[#778296]">{asset.label}</p>
                  <span className="mt-1 block text-[10px] text-[#9aa3b2]">{statusLabels[status]} · V{version.version_number}</span>
                </div>
              </button>
            );
          })}
        </div>
      </Card>

      <Card className="overflow-hidden p-0">
        {selected ? (
          <div className="grid xl:grid-cols-[1fr_350px]">
            <div className="min-h-[620px] bg-[#e7ebf1] p-5 lg:p-8">
              <div className="mx-auto h-full max-w-[720px] overflow-hidden rounded-xl bg-white shadow-[0_24px_70px_rgba(28,36,52,.12)]">
                <AssetArtwork type={selected.asset_type} versionId={latestVersion(selected).id} demo={demo} className="min-h-[620px]" />
              </div>
            </div>
            <aside className="border-l border-[#e1e5ec] bg-white p-5 lg:p-6">
              <p className="utility-face text-[10px] tracking-[.14em] text-[#8a94a6]">DECISION PANEL</p>
              <h2 className="display-face mt-2 text-2xl font-bold">{selected.asset_type} · V{latestVersion(selected).version_number}</h2>
              <p className="mt-2 text-sm leading-6 text-[#6d788c]">检查主体完整度、背景、文字安全区和平台规则，然后给出明确结论。</p>

              <div className="mt-6 grid grid-cols-2 gap-2">
                {[
                  ["主体完整", true],
                  ["背景合规", true],
                  ["比例 1:1", true],
                  ["无水印", true],
                ].map(([label]) => (
                  <div key={String(label)} className="flex items-center gap-2 rounded-lg bg-[#f4f7fa] px-3 py-2.5 text-xs font-bold text-[#536078]">
                    <Check className="h-3.5 w-3.5 text-emerald-600" />{label as string}
                  </div>
                ))}
              </div>

              <label className="mt-6 block text-xs font-bold text-[#4d596d]" htmlFor="reject-reason">拒绝原因</label>
              <select
                id="reject-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value as RejectReason)}
                className="mt-2 w-full rounded-xl border border-[#dce1e9] bg-[#f9fafc] px-3 py-2.5 text-sm outline-none transition focus:border-[#ff6433] focus:ring-2 focus:ring-[#ff6433]/10"
              >
                {rejectReasons.map((item) => (
                  <option key={item} value={item}>{reasonLabels[item]}</option>
                ))}
              </select>
              <label className="mt-4 block text-xs font-bold text-[#4d596d]" htmlFor="review-comment">审核说明</label>
              <textarea
                id="review-comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="拒绝或重新处理时，说明需要调整的位置。"
                className="mt-2 min-h-28 w-full resize-none rounded-xl border border-[#dce1e9] bg-[#f9fafc] p-3 text-sm outline-none transition focus:border-[#ff6433] focus:ring-2 focus:ring-[#ff6433]/10"
              />
              {message && <div className="mt-3 rounded-lg bg-[#f2f5f8] px-3 py-2.5 text-xs leading-5 text-[#59667a]">{message}</div>}

              <div className="mt-6 grid gap-2">
                <Button disabled={busy} onClick={() => void decide("approved")}><Check className="h-4 w-4" />通过</Button>
                <Button disabled={busy} variant="secondary" onClick={() => void decide("rejected")}><X className="h-4 w-4" />拒绝</Button>
                <Button disabled={busy} variant="secondary" onClick={() => void decide("regenerate")}><RotateCcw className="h-4 w-4" />重新处理</Button>
              </div>
              <p className="mt-4 text-[11px] leading-5 text-[#8a94a6]">重新处理会创建新任务和新版本，不覆盖当前图片。</p>
            </aside>
          </div>
        ) : (
          <div className="grid min-h-[560px] place-items-center text-sm text-[#788397]">当前没有待审核图片。</div>
        )}
      </Card>
    </div>
  );
}
