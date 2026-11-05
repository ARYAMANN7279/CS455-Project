import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ResizeHandle from "./ResizeHandle";

// jsdom's PointerEvent support varies; a MouseEvent of the same name carries the coordinates.
const pointer = (el: Element, type: string, at: { clientX?: number; clientY?: number }) =>
  fireEvent(el, new MouseEvent(type, { bubbles: true, cancelable: true, ...at }));

function setup(props: Partial<React.ComponentProps<typeof ResizeHandle>> = {}) {
  const onResize = vi.fn();
  render(<ResizeHandle label="Resize" axis="x" size={240} min={160} max={400} onResize={onResize} {...props} />);
  return { onResize, handle: screen.getByRole("separator", { name: "Resize" }) };
}

describe("ResizeHandle", () => {
  it("grows the panel as you drag, from where the drag began", () => {
    const { onResize, handle } = setup();
    pointer(handle, "pointerdown", { clientX: 100 });
    pointer(handle, "pointermove", { clientX: 130 });
    expect(onResize).toHaveBeenLastCalledWith(270);
    pointer(handle, "pointermove", { clientX: 90 });
    expect(onResize).toHaveBeenLastCalledWith(230);
  });

  it("a panel after the handle grows when dragged the other way, on the y axis too", () => {
    const { onResize, handle } = setup({ axis: "y", invert: true });
    pointer(handle, "pointerdown", { clientY: 500 });
    pointer(handle, "pointermove", { clientY: 450 });
    expect(onResize).toHaveBeenLastCalledWith(290);
  });

  it("stays within its limits", () => {
    const { onResize, handle } = setup();
    pointer(handle, "pointerdown", { clientX: 100 });
    pointer(handle, "pointermove", { clientX: 900 });
    expect(onResize).toHaveBeenLastCalledWith(400);
    pointer(handle, "pointermove", { clientX: -900 });
    expect(onResize).toHaveBeenLastCalledWith(160);
  });

  it("ignores the mouse moving when no drag is on, and after release", () => {
    const { onResize, handle } = setup();
    pointer(handle, "pointermove", { clientX: 130 });
    pointer(handle, "pointerdown", { clientX: 100 });
    pointer(handle, "pointerup", { clientX: 100 });
    pointer(handle, "pointermove", { clientX: 130 });
    expect(onResize).not.toHaveBeenCalled();
  });

  it("resizes with the arrow keys, and leaves other keys alone", () => {
    const { onResize, handle } = setup({ invert: true });
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(onResize).toHaveBeenLastCalledWith(256);
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(onResize).toHaveBeenLastCalledWith(224);
    onResize.mockClear();
    fireEvent.keyDown(handle, { key: "Enter" });
    fireEvent.keyDown(handle, { key: "ArrowUp" });
    expect(onResize).not.toHaveBeenCalled();
  });

  it("tells assistive technology what it is", () => {
    const { handle } = setup({ axis: "y" });
    expect(handle).toHaveAttribute("aria-orientation", "horizontal");
    expect(handle).toHaveAttribute("aria-valuenow", "240");
  });
});
