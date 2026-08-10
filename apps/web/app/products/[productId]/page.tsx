import { Badge, Button } from "@ecommerce-visual-workbench/ui";
import { ChevronLeft, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { ProductWorkspace } from "@/components/product-workspace";
import { WorkspaceShell } from "@/components/workspace-shell";
import { loadProductWorkspace } from "@/lib/api";

export default async function ProductWorkspacePage({
  params,
}: {
  params: Promise<{productId: string}>;
}) {
  const {productId} = await params;
  const {product, assets, demo} = await loadProductWorkspace(productId);
  return (
    <WorkspaceShell
      active="product"
      eyebrow="PRODUCT WORKSPACE · TEMU US"
      title="商品视觉工作区"
      actions={
        <>
          {demo && <Badge className="border-amber-200 bg-amber-50 text-amber-700">演示数据</Badge>}
          <Button variant="secondary" asChild><Link href="/"><ChevronLeft className="h-4 w-4" />返回生产台</Link></Button>
          <Button asChild><Link href="/reviews"><ShieldCheck className="h-4 w-4" />打开审核</Link></Button>
        </>
      }
    >
      <ProductWorkspace product={product} initialAssets={assets} demo={demo} />
    </WorkspaceShell>
  );
}
