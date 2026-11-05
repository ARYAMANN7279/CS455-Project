import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_SIZES, loadSizes, maxSize, MIN_SIZES, saveSizes } from "./layout";

describe("panel sizes", () => {
  beforeEach(() => localStorage.clear());

  it("uses the defaults when nothing is saved", () => {
    expect(loadSizes()).toEqual(DEFAULT_SIZES);
  });

  it("remembers what was saved", () => {
    saveSizes({ left: 300, right: 400, bottom: 150 });
    expect(loadSizes()).toEqual({ left: 300, right: 400, bottom: 150 });
  });

  it("falls back for corrupt, missing or too-small values", () => {
    localStorage.setItem("concord:layout", "{not json");
    expect(loadSizes()).toEqual(DEFAULT_SIZES);
    localStorage.setItem("concord:layout", JSON.stringify({ left: "wide", right: 1, bottom: 150 }));
    expect(loadSizes()).toEqual({ ...DEFAULT_SIZES, bottom: 150 });
  });

  it("still works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => { throw new Error("blocked"); });
    expect(() => saveSizes(DEFAULT_SIZES)).not.toThrow();
  });

  it("caps panels to the window, but never below their minimum", () => {
    vi.stubGlobal("innerWidth", 1000);
    vi.stubGlobal("innerHeight", 1000);
    expect([maxSize("left"), maxSize("right"), maxSize("bottom")]).toEqual([350, 350, 700]);
    vi.stubGlobal("innerWidth", 300);
    expect(maxSize("right")).toBe(MIN_SIZES.right);
    vi.unstubAllGlobals();
  });
});
