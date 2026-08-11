import {describe, expect, it} from "vitest";

import {
  commitDocument,
  createEditorHistory,
  duplicateLayer,
  moveLayer,
  redoDocument,
  removeLayer,
  undoDocument,
} from "./state";

const document = {
  schemaVersion: "1.0" as const,
  layers: [
    {id: "a", type: "SHAPE" as const, x: 0, y: 0, width: 10, height: 10, rotation: 0, opacity: 1, visible: true, locked: false, zIndex: 0},
    {id: "b", type: "TEXT" as const, x: 10, y: 10, width: 80, height: 20, rotation: 0, opacity: 1, visible: true, locked: false, zIndex: 1, text: "B"},
  ],
};

describe("template editor state", () => {
  it("supports undo and redo without mutating historical schemas", () => {
    const next = removeLayer(document, "a");
    const committed = commitDocument(createEditorHistory(document), next);
    expect(undoDocument(committed).present.layers).toHaveLength(2);
    expect(redoDocument(undoDocument(committed)).present.layers).toHaveLength(1);
  });

  it("duplicates and reorders layers", () => {
    const duplicated = duplicateLayer(document, "a");
    expect(duplicated.layers).toHaveLength(3);
    expect(duplicated.layers[2].id).not.toBe("a");
    expect(moveLayer(document, "a", "forward").layers.find((layer) => layer.id === "a")?.zIndex).toBe(1);
  });
});
