import { Badge, Button } from "@ecommerce-visual-workbench/ui";
import { Boxes } from "lucide-react";
import Link from "next/link";

import { ReviewConsole } from "@/components/review-console";
import { WorkspaceShell } from "@/components/workspace-shell";
import { loadProductWorkspace } from "@/lib/api";

export default async function ReviewsPage({
  searchParams,
}: {
  searchParams: Promise<{product?: string; version?: string}>;
}) {
  const {product: productId = "demo-kettle", version} = await searchParams;
  const {assets, demo} = await loadProductWorkspace(productId);
  return (
    <WorkspaceShell
      active="review"
      eyebrow="HUMAN REVIEW · ASSET VERSIONS"
      title="图片审核工作台"
      actions={
        <>
          {demo && <Badge className="border-amber-200 bg-amber-50 text-amber-700">演示数据</Badge>}
          <Button variant="secondary" asChild><Link href="/products/demo-kettle"><Boxes className="h-4 w-4" />返回商品</Link></Button>
        </>
      }
    >
      <ReviewConsole initialAssets={assets} initialVersionId={version} demo={demo} />
    </WorkspaceShell>
  );
}
