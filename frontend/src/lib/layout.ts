// How big the user dragged the workspace panels, remembered in this browser
// (a convenience: losing it just means the default sizes).

export type PanelSizes = { left: number; right: number; bottom: number };

export const DEFAULT_SIZES: PanelSizes = { left: 240, right: 300, bottom: 220 };
export const MIN_SIZES: PanelSizes = { left: 160, right: 220, bottom: 100 };

const KEY = "concord:layout";

/** The largest a panel may get, so the editor always keeps some room. */
export function maxSize(panel: keyof PanelSizes): number {
  const limit = panel === "bottom" ? window.innerHeight * 0.7 : window.innerWidth * 0.35;
  return Math.max(MIN_SIZES[panel], Math.floor(limit));
}

export function loadSizes(): PanelSizes {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<PanelSizes>;
    const size = (panel: keyof PanelSizes) => {
      const n = saved[panel];
      return typeof n === "number" && n >= MIN_SIZES[panel] ? n : DEFAULT_SIZES[panel];
    };
    return { left: size("left"), right: size("right"), bottom: size("bottom") };
  } catch {
    return DEFAULT_SIZES;
  }
}

export function saveSizes(sizes: PanelSizes): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(sizes));
  } catch {
    /* private mode or storage full: sizes just aren't remembered */
  }
}
