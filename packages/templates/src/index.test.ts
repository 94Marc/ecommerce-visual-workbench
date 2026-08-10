import { describe, expect, it } from "vitest";

import { findTemplate, imageSlots } from "./index";

describe("platform templates", () => {
  it("provides all phase-one output slots", () => {
    expect(imageSlots).toHaveLength(8);
    expect(findTemplate("DIMENSION").label).toBe("尺寸图");
  });
});

