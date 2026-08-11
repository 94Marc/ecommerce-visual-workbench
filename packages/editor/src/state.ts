import type {TemplateDocument, TemplateLayer} from "@ecommerce-visual-workbench/templates";

export type EditorHistory = {past: TemplateDocument[]; present: TemplateDocument; future: TemplateDocument[]};

export function createEditorHistory(document: TemplateDocument): EditorHistory {
  return {past: [], present: document, future: []};
}

export function commitDocument(history: EditorHistory, document: TemplateDocument): EditorHistory {
  if (JSON.stringify(history.present) === JSON.stringify(document)) return history;
  return {past: [...history.past, history.present], present: document, future: []};
}

export function undoDocument(history: EditorHistory): EditorHistory {
  const previous = history.past.at(-1);
  return previous ? {past: history.past.slice(0, -1), present: previous, future: [history.present, ...history.future]} : history;
}

export function redoDocument(history: EditorHistory): EditorHistory {
  const next = history.future[0];
  return next ? {past: [...history.past, history.present], present: next, future: history.future.slice(1)} : history;
}

export function updateLayer(document: TemplateDocument, layerId: string, changes: Partial<TemplateLayer>): TemplateDocument {
  return {...document, layers: document.layers.map((layer) => layer.id === layerId ? {...layer, ...changes} : layer)};
}

export function duplicateLayer(document: TemplateDocument, layerId: string): TemplateDocument {
  const source = document.layers.find((layer) => layer.id === layerId);
  if (!source) return document;
  return {...document, layers: [...document.layers, {...source, id: `${source.id}_copy_${document.layers.length + 1}`, x: source.x + 24, y: source.y + 24, zIndex: Math.max(0, ...document.layers.map((layer) => layer.zIndex)) + 1}]};
}

export function removeLayer(document: TemplateDocument, layerId: string): TemplateDocument {
  return {...document, layers: document.layers.filter((layer) => layer.id !== layerId)};
}

export function moveLayer(document: TemplateDocument, layerId: string, direction: "forward" | "backward"): TemplateDocument {
  const ordered = [...document.layers].sort((left, right) => left.zIndex - right.zIndex);
  const index = ordered.findIndex((layer) => layer.id === layerId);
  const target = direction === "forward" ? index + 1 : index - 1;
  if (index < 0 || target < 0 || target >= ordered.length) return document;
  [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
  const zIndex = new Map(ordered.map((layer, position) => [layer.id, position]));
  return {...document, layers: document.layers.map((layer) => ({...layer, zIndex: zIndex.get(layer.id) ?? layer.zIndex}))};
}
