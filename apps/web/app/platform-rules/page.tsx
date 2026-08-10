import {Badge, Button} from "@ecommerce-visual-workbench/ui";
import {ClipboardList} from "lucide-react";
import Link from "next/link";
import {PlatformRuleCenter} from "@/components/platform-rule-center";
import {WorkspaceShell} from "@/components/workspace-shell";
import {loadPlatformRuleCenter} from "@/lib/api";

export default async function PlatformRulesPage() {
  const {platforms, rules, demo} = await loadPlatformRuleCenter();
  return <WorkspaceShell active="rules" eyebrow="PLATFORM GOVERNANCE · 5 CHANNELS" title="跨境平台规则中心" actions={<>{demo && <Badge className="border-amber-200 bg-amber-50 text-amber-700">演示数据</Badge>}<Button variant="secondary" asChild><Link href="/visual-plans"><ClipboardList className="h-4 w-4" />进入视觉方案</Link></Button></>}><PlatformRuleCenter platforms={platforms} initialRules={rules} demo={demo} /></WorkspaceShell>;
}
