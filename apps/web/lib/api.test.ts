import { describe, expect, it } from "vitest";

import {
  demoAssets,
  demoJobs,
  demoPlatforms,
  demoRules,
  demoVisualPlans,
  latestVersion,
  rejectReasons,
  summarizeJobs,
  type GenerationJob,
} from "./api";

describe("summarizeJobs", () => {
  it("counts every production state", () => {
    const jobs = ["pending", "processing", "completed", "completed", "failed"].map(
      (status, index) => ({
        id: String(index),
        platform: "temu",
        image_slot: "MAIN",
        status,
        created_at: "2026-08-10T00:00:00Z",
      }),
    ) as GenerationJob[];

    expect(summarizeJobs(jobs)).toEqual({pending: 1, processing: 1, completed: 2, failed: 1});
  });
});

describe("latestVersion", () => {
  it("returns the highest immutable version number", () => {
    const asset = demoAssets.find((item) => item.versions.length > 1);

    expect(asset).toBeDefined();
    expect(latestVersion(asset!)?.version_number).toBe(2);
  });
});

describe("phase two planning fixtures", () => {
  it("covers all five platform rule frameworks", () => {
    expect(demoPlatforms.map((platform) => platform.code)).toEqual([
      "temu",
      "amazon",
      "tiktok_shop",
      "shopee",
      "aliexpress",
    ]);
    expect(new Set(demoRules.map((rule) => rule.platform))).toHaveLength(5);
  });

  it("keeps requested output quantities on the visual plan", () => {
    expect(demoVisualPlans[0].requested_outputs).toMatchObject({MAIN: 5, DETAIL: 6, DIMENSION: 2});
    expect(demoVisualPlans[0].slots.map((slot) => slot.code)).toContain("DIMENSION_FRONT");
  });
});

describe("phase 3.5 fidelity records", () => {
  it("exposes references, mode and the complete quality gate", () => {
    const record = demoJobs[0];
    expect(record.generation_mode).toBe("STRICT");
    expect(record.reference_asset_version_ids).toHaveLength(2);
    expect(record.quality_check?.resolution.status).toBe("passed");
    expect(record.quality_check?.product_similarity.status).toBe("unavailable");
  });

  it("keeps the rejection reason taxonomy stable", () => {
    expect(rejectReasons).toContain("PRODUCT_CHANGED");
    expect(rejectReasons).toContain("PACKAGING_ERROR");
    expect(rejectReasons).toHaveLength(10);
  });
});
