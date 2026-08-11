import { Badge } from "@ecommerce-visual-workbench/ui";

import { GenerationRecords } from "@/components/generation-records";
import { WorkspaceShell } from "@/components/workspace-shell";
import { loadGenerationRecords } from "@/lib/api";

export default async function GenerationJobsPage() {
  const {jobs, demo} = await loadGenerationRecords();
  return (
    <WorkspaceShell
      active="generation"
      eyebrow="FIDELITY TRACE / QUALITY GATE"
      title="商品图片生成记录"
      actions={demo ? <Badge className="border-amber-200 bg-amber-50 text-amber-700">演示数据</Badge> : undefined}
    >
      <GenerationRecords jobs={jobs} demo={demo} />
    </WorkspaceShell>
  );
}
