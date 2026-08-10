import { cn } from "@ecommerce-visual-workbench/ui";
import { Box, Maximize2, PackageOpen, Ruler, ScanLine, Sparkles } from "lucide-react";

import { assetContentUrl, type AssetType } from "@/lib/api";

const iconByType = {
  ORIGINAL: ScanLine,
  CUTOUT: Maximize2,
  MAIN: Sparkles,
  DETAIL: Maximize2,
  DIMENSION: Ruler,
  SCENE: Box,
  USAGE: Sparkles,
  PACKAGE: PackageOpen,
  CLOSEUP: Maximize2,
  COMPARE: Sparkles,
} satisfies Record<AssetType, typeof ScanLine>;

const toneByType: Record<AssetType, string> = {
  ORIGINAL: "from-[#dbe8de] to-[#bccdbf]",
  CUTOUT: "from-[#eef1f5] to-white",
  MAIN: "from-[#ffe4d9] to-[#fff8f4]",
  DETAIL: "from-[#dfe6ef] to-[#f7f9fc]",
  DIMENSION: "from-[#fff0c9] to-[#fffaf0]",
  SCENE: "from-[#dce9ed] to-[#eff7f7]",
  USAGE: "from-[#e9e2f2] to-[#faf7fd]",
  PACKAGE: "from-[#eadfce] to-[#f8f3ec]",
  CLOSEUP: "from-[#d7e5dd] to-[#f3f8f5]",
  COMPARE: "from-[#e3e7f5] to-[#f7f8fd]",
};

export function AssetArtwork({
  type,
  versionId,
  demo,
  className,
}: {
  type: AssetType;
  versionId: string;
  demo: boolean;
  className?: string;
}) {
  const Icon = iconByType[type];
  if (!demo) {
    return (
      // Object storage content is served by the authenticated API in production.
      <img
        src={assetContentUrl(versionId)}
        alt={`${type} asset`}
        className={cn("h-full w-full object-cover", className)}
      />
    );
  }
  return (
    <div
      className={cn(
        "relative grid h-full min-h-40 place-items-center overflow-hidden bg-gradient-to-br",
        toneByType[type],
        className,
      )}
    >
      <div className="absolute inset-4 crop-corners opacity-60" />
      <div className="grid h-24 w-20 place-items-center rounded-[24px_24px_16px_16px] border border-[#718078]/40 bg-white/35 shadow-[0_18px_28px_rgba(39,55,47,.12)] backdrop-blur-sm">
        <Icon className="h-7 w-7 text-[#536158]" />
      </div>
      <span className="utility-face absolute bottom-4 left-4 text-[9px] tracking-[.14em] text-[#69746d]">
        {type} / 1600²
      </span>
    </div>
  );
}
