import { cn } from "@ecommerce-visual-workbench/ui";
import { Archive, Boxes, ClipboardList, Image as ImageIcon, ScanLine, ScrollText, ShieldCheck, Waypoints } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

const links = [
  {href: "/", label: "生产台", icon: ScanLine},
  {href: "/products/demo-kettle", label: "商品工作区", icon: Boxes},
  {href: "/products/demo-kettle#assets", label: "图片资产", icon: ImageIcon},
  {href: "/platform-rules", label: "平台规则", icon: ScrollText},
  {href: "/visual-plans", label: "视觉方案", icon: ClipboardList},
  {href: "/generation-jobs", label: "生成记录", icon: Waypoints},
  {href: "/reviews", label: "审核工作台", icon: ShieldCheck},
  {href: "/#exports", label: "导出记录", icon: Archive},
];

export function WorkspaceShell({
  active,
  eyebrow,
  title,
  actions,
  children,
}: {
  active: "production" | "product" | "review" | "rules" | "plan" | "generation";
  eyebrow: string;
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[238px_1fr]">
      <aside className="bg-[#151c2c] px-4 py-5 text-white lg:sticky lg:top-0 lg:h-screen">
        <Link href="/" className="flex items-center gap-3 px-2">
          <div className="crop-corners grid h-10 w-10 place-items-center bg-white/5">
            <ScanLine className="h-5 w-5 text-[#ff7448]" />
          </div>
          <div>
            <div className="display-face text-lg font-bold leading-none">FRAMEFLOW</div>
            <div className="utility-face mt-1 text-[9px] tracking-[.16em] text-[#8994aa]">
              VISUAL OPS / CN
            </div>
          </div>
        </Link>
        <nav className="mt-8 grid grid-cols-2 gap-2 lg:block lg:space-y-1">
          {links.map(({href, label, icon: Icon}) => {
            const selected =
              (active === "production" && href === "/") ||
              (active === "product" && label === "商品工作区") ||
              (active === "review" && label === "审核工作台") ||
              (active === "rules" && label === "平台规则") ||
              (active === "plan" && label === "视觉方案") ||
              (active === "generation" && label === "生成记录");
            return (
              <Link
                key={label}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                  selected
                    ? "bg-white text-[#172033]"
                    : "text-[#9ba6ba] hover:bg-white/5 hover:text-white",
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-8 hidden border-t border-white/10 pt-5 text-xs text-[#8994aa] lg:block">
          <p className="utility-face tracking-[.12em]">PHASE 3.5 · FIDELITY</p>
          <p className="mt-2 leading-5">多角度参考、真实性追踪与人工质量门。</p>
        </div>
      </aside>
      <main className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#dfe4ec] bg-white px-5 py-4 lg:px-8">
          <div>
            <div className="utility-face text-[10px] tracking-[.12em] text-[#8a94a6]">
              {eyebrow}
            </div>
            <h1 className="display-face mt-1 text-2xl font-bold">{title}</h1>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
        {children}
      </main>
    </div>
  );
}
