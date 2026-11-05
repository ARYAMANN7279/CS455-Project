import { KeyboardEvent, PointerEvent, useRef } from "react";

type Props = {
  label: string;
  /** "x" sits between side-by-side panels; "y" between stacked ones. */
  axis: "x" | "y";
  size: number;
  min: number;
  max: number;
  /** The panel is after the handle, so dragging left or up makes it bigger. */
  invert?: boolean;
  onResize: (size: number) => void;
};

const KEY_STEP = 16;

/** A draggable divider that also resizes with the arrow keys. */
export default function ResizeHandle({ label, axis, size, min, max, invert = false, onResize }: Props) {
  const drag = useRef<{ from: number; size: number } | null>(null);
  const clamp = (n: number) => Math.min(max, Math.max(min, n));
  const position = (e: PointerEvent) => (axis === "x" ? e.clientX : e.clientY);

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    e.preventDefault(); // no text selection while dragging
    // Keeps the drag going over the editor and outside the window.
    e.currentTarget.setPointerCapture?.(e.pointerId);
    drag.current = { from: position(e), size };
  }

  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const moved = position(e) - drag.current.from;
    onResize(clamp(drag.current.size + (invert ? -moved : moved)));
  }

  const stop = () => { drag.current = null; };

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const [less, more] = axis === "x" ? ["ArrowLeft", "ArrowRight"] : ["ArrowUp", "ArrowDown"];
    if (e.key !== less && e.key !== more) return;
    e.preventDefault();
    onResize(clamp(size + ((e.key === more) === invert ? -KEY_STEP : KEY_STEP)));
  }

  return (
    <div
      className={`resize-handle ${axis}`}
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-orientation={axis === "x" ? "vertical" : "horizontal"}
      aria-valuenow={Math.round(size)}
      aria-valuemin={min}
      aria-valuemax={max}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stop}
      onPointerCancel={stop}
      onKeyDown={onKeyDown}
    />
  );
}
