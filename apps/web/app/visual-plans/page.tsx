import { Badge, Button } from "@ecommerce-visual-workbench/ui";
import { ScrollText } from "lucide-react";
import Link from "next/link";

import { VisualPlanBuilder } from "@/components/visual-plan-builder";
import { WorkspaceShell } from "@/components/workspace-shell";
import { loadVisualPlanCenter } from "@/lib/api";

export default async function VisualPlansPage({searchParams}: {searchParams: Promise<{product?: string}>}) {
  const {product} = await searchParams;
  const {products, platforms, rules, plans, templates, demo} = await loadVisualPlanCenter(product);
  return (
    <WorkspaceShell
      active="plan"
      eyebrow="PRODUCT BRIEF · RULE-PINNED OUTPUTS"
      title="商品视觉方案"
      actions={<>{demo && <Badge className="border-amber-200 bg-amber-50 text-amber-700">演示数据</Badge>}<Button variant="secondary" asChild><Link href="/platform-rules"><ScrollText className="h-4 w-4" />查看平台规则</Link></Button></>}
    >
      <VisualPlanBuilder products={products} platforms={platforms} rules={rules} templates={templates} initialPlans={plans} initialProductId={product} demo={demo} />
    </WorkspaceShell>
  );
}
