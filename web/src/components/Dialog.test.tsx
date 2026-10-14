import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { Dialog } from "./ui";

/* Regression: an inline onClose (new function every render) used to re-run the dialog's focus effect on each
   keystroke, moving focus to the close button so the next space closed the dialog. */
function Harness({ onClosed }: { onClosed: () => void }) {
  const [open, setOpen] = useState(true);
  const [text, setText] = useState("");
  return open ? (
    <Dialog title="إثبات الإنجاز" onClose={() => { setOpen(false); onClosed(); }}>
      <label htmlFor="t">ماذا أُنجز؟</label>
      <textarea id="t" value={text} onChange={(e) => setText(e.target.value)} />
    </Dialog>
  ) : null;
}

test("typing in a dialog keeps focus in the field and does not close it", () => {
  let closed = 0;
  render(<Harness onClosed={() => { closed += 1; }} />);
  const field = screen.getByLabelText("ماذا أُنجز؟") as HTMLTextAreaElement;
  expect(document.activeElement).toBe(field); // first field focused, not the close button

  const text = "تم تفريغ الحاوية";
  for (let i = 1; i <= text.length; i++) {
    act(() => { fireEvent.change(field, { target: { value: text.slice(0, i) } }); });
    expect(document.activeElement).toBe(field);
  }
  expect(field.value).toBe(text);
  expect(screen.getByRole("dialog")).toBeInTheDocument();

  fireEvent.keyDown(window, { key: "Escape" }); // the latest onClose still runs
  expect(closed).toBe(1);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
