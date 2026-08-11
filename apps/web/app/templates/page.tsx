import {Badge, Button} from "@ecommerce-visual-workbench/ui";
import {Plus} from "lucide-react";

import {TemplateCenter} from "@/components/template-center";
import {WorkspaceShell} from "@/components/workspace-shell";
import {loadTemplateCenter} from "@/lib/api";

export default async function TemplatesPage() {
  const {templates, demo} = await loadTemplateCenter();
  return (
    <WorkspaceShell
      active="templates"
      eyebrow="TEMPLATE SYSTEM · 6 DEMOS"
      title="电商图片模板中心"
      actions={<>{demo && <Badge className="border-amber-200 bg-amber-50 text-amber-700">演示数据</Badge>}<Button><Plus className="h-4 w-4" />新建模板</Button></>}
    >
      <TemplateCenter templates={templates} demo={demo} />
    </WorkspaceShell>
  );
}
