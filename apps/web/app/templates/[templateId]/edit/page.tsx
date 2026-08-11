import {TemplateEditorWorkbench} from "@/components/template-editor-workbench";
import {loadTemplateEditor} from "@/lib/api";

export default async function TemplateEditPage({params}: {params: Promise<{templateId: string}>}) {
  const {templateId} = await params;
  const data = await loadTemplateEditor(templateId);
  return <TemplateEditorWorkbench {...data} />;
}
