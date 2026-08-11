import {describe, expect, it} from "vitest";

import {
  assetBindingUrl,
  findTemplate,
  formatDimension,
  imageSlots,
  previewDocument,
  resolveBinding,
  type TemplateDocument,
} from "./index";

const preview = {
  product: {name: "旅行水壶", length: "30 cm"},
  sku: {code: "KETTLE-01"},
  selling_point_1: "轻巧便携",
  assets: {cutout: "/cutout.png"},
};

describe("template bindings", () => {
  it("resolves product, sku and selling-point values", () => {
    expect(resolveBinding("{{product.name}} / {{sku.code}} / {{selling_point_1}}", preview)).toBe(
      "旅行水壶 / KETTLE-01 / 轻巧便携",
    );
  });

  it("formats deterministic dimension units", () => {
    expect(formatDimension(300, "mm", "cm")).toBe("30 cm");
    expect(formatDimension(2.54, "cm", "inch")).toBe("1 inch");
  });

  it("builds a preview without mutating the source schema", () => {
    const document: TemplateDocument = {
      schemaVersion: "1.0",
      layers: [{id: "title", type: "TEXT", x: 0, y: 0, width: 200, height: 40, rotation: 0, opacity: 1, visible: true, locked: false, zIndex: 1, text: "{{product.name}}"}],
    };
    expect(previewDocument(document, preview).layers[0].text).toBe("旅行水壶");
    expect(document.layers[0].text).toBe("{{product.name}}");
  });

  it("resolves approved asset URLs supplied by the workspace", () => {
    const layer = {id: "product", type: "IMAGE", x: 0, y: 0, width: 100, height: 100, rotation: 0, opacity: 1, visible: true, locked: false, zIndex: 0, assetSource: "{{asset.cutout}}"} as const;
    expect(assetBindingUrl(layer, preview)).toBe("/cutout.png");
  });
});

describe("platform templates", () => {
  it("provides all visual output slots", () => {
    expect(imageSlots).toHaveLength(8);
    expect(findTemplate("DIMENSION").label).toBe("尺寸图");
  });
});
