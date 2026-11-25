import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CorrectionFieldInput } from "./CorrectionFieldInput";

describe("CorrectionFieldInput", () => {
  it("picks a category from every expense category, labelled", async () => {
    const onChange = vi.fn();
    render(<CorrectionFieldInput name="category" kind="category" required value="meal" invalid={false} onChange={onChange} />);

    const select = screen.getByRole("combobox");
    expect(screen.getAllByRole("option")).toHaveLength(15);
    await userEvent.selectOptions(select, "Client entertainment");

    expect(onChange).toHaveBeenCalledWith("client_entertainment");
  });

  it.each([
    ["date", "date"],
    ["time", "time"],
    ["money", "text"],
  ] as const)("uses a %s field as a %s input", (kind, type) => {
    const { container } = render(
      <CorrectionFieldInput name="total" kind={kind} required value="" invalid={false} onChange={() => {}} />,
    );

    expect(container.querySelector("input")).toHaveAttribute("type", type);
  });

  it("marks an invalid value and reports each change", async () => {
    const onChange = vi.fn();
    render(<CorrectionFieldInput name="currency" kind="currency" required value="" invalid onChange={onChange} />);

    await userEvent.type(screen.getByRole("textbox"), "E");

    expect(screen.getByRole("textbox")).toHaveAttribute("aria-invalid", "true");
    expect(onChange).toHaveBeenCalledWith("E");
  });
});
