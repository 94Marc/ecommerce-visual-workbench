import { describe, expect, it } from "vitest";

import { demoAssets, latestVersion, summarizeJobs, type GenerationJob } from "./api";

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
