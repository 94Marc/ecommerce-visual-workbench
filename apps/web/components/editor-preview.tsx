"use client";

import { findTemplate } from "@ecommerce-visual-workbench/templates";
import dynamic from "next/dynamic";

const ImageTemplateEditor = dynamic(
  () =>
    import("@ecommerce-visual-workbench/editor").then(
      (editor) => editor.ImageTemplateEditor,
    ),
  {
    ssr: false,
    loading: () => <div className="h-[420px] animate-pulse rounded-xl bg-[#e9edf4]" />,
  },
);

export function EditorPreview() {
  return <ImageTemplateEditor guide={findTemplate("MAIN")} />;
}
