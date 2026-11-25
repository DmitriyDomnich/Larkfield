import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { makeExtraction } from "@/test/fixtures";

import { fieldValuesOf, findFieldProblems, withCorrections, type FieldValues } from "../corrections";
import { ExtractionPanel } from "./ExtractionPanel";

const EXTRACTION = makeExtraction();

function row(label: string) {
  return screen.getByText(label, { selector: "dt, label" }).closest("div")!;
}

function EditableHarness({ initial = fieldValuesOf(EXTRACTION) }: { initial?: FieldValues }) {
  const [values, setValues] = useState(initial);
  const [editing, setEditing] = useState(false);
  return (
    <ExtractionPanel
      extraction={EXTRACTION}
      correctedValues={values}
      problems={findFieldProblems(values)}
      editing={editing}
      canEdit
      onEditingChange={setEditing}
      onChange={(field, value) => setValues({ ...values, [field]: value })}
    />
  );
}

describe("ExtractionPanel", () => {
  it("shows every field, the warnings and the line items", () => {
    render(<ExtractionPanel extraction={EXTRACTION} correctedValues={fieldValuesOf(EXTRACTION)} />);

    expect(within(row("Vendor")).getByText("Trattoria Roma")).toBeInTheDocument();
    expect(within(row("Total")).getByText("120.00 EUR")).toBeInTheDocument();
    expect(within(row("Category")).getByText("Client entertainment")).toBeInTheDocument();
    expect(within(row("Vendor tax id")).getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/add up to 99.00/)).toBeInTheDocument();
    expect(screen.getByText("Menu del giorno")).toBeInTheDocument();
    expect(screen.queryByText("Corrected")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit fields" })).not.toBeInTheDocument();
  });

  it("shows a corrected value inline with the extracted one struck through", () => {
    const values = withCorrections(fieldValuesOf(EXTRACTION), { total: "99.99", category: "other" });

    render(<ExtractionPanel extraction={EXTRACTION} correctedValues={values} />);

    const total = row("Total");
    expect(within(total).getByText("99.99 EUR")).toBeInTheDocument();
    expect(within(total).getByText("Corrected")).toBeInTheDocument();
    expect(within(total).getByText("120.00 EUR").tagName).toBe("S");
    expect(total).toHaveTextContent("extracted: 120.00 EUR");
    expect(within(row("Category")).getByText("Client entertainment").tagName).toBe("S");
    expect(within(row("Vendor")).queryByText("Corrected")).not.toBeInTheDocument();
  });

  it("turns into a form of the twelve fields, without the line items, on Edit fields", async () => {
    render(<EditableHarness />);

    await userEvent.click(screen.getByRole("button", { name: "Edit fields" }));

    // 8 text inputs, 2 selects, a date and a time
    expect(screen.getAllByRole("textbox")).toHaveLength(8);
    expect(screen.getAllByRole("combobox")).toHaveLength(2);
    expect(screen.getByLabelText("Date")).toHaveValue("2026-11-09");
    expect(screen.getByLabelText("Time")).toHaveValue("20:15");
    expect(screen.getByLabelText("Total")).toHaveValue("120.00");
    expect(screen.getByLabelText("Document type")).toHaveDisplayValue("Receipt");
    expect(screen.queryByLabelText(/Menu del giorno/)).not.toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Menu del giorno" })).toBeInTheDocument();
  });

  it("marks an edited field as corrected while editing, and keeps it after Done editing", async () => {
    const user = userEvent.setup();
    render(<EditableHarness />);
    await user.click(screen.getByRole("button", { name: "Edit fields" }));

    await user.clear(screen.getByLabelText("Total"));
    await user.type(screen.getByLabelText("Total"), "99.99");
    await user.selectOptions(screen.getByLabelText("Category"), "Other");

    expect(within(row("Total")).getByText("Corrected")).toBeInTheDocument();
    expect(within(row("Category")).getByText("Corrected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done editing" }));
    expect(within(row("Total")).getByText("99.99 EUR")).toBeInTheDocument();
  });

  it("shows an inline error per invalid field", async () => {
    const user = userEvent.setup();
    render(<EditableHarness />);
    await user.click(screen.getByRole("button", { name: "Edit fields" }));

    await user.clear(screen.getByLabelText("Total"));
    await user.type(screen.getByLabelText("Total"), "0");
    await user.clear(screen.getByLabelText("Currency"));
    await user.type(screen.getByLabelText("Currency"), "eu");
    await user.clear(screen.getByLabelText("Vendor"));

    expect(within(row("Total")).getByText("The total must be more than 0.")).toBeInTheDocument();
    expect(within(row("Currency")).getByText(/three-letter code/)).toBeInTheDocument();
    expect(within(row("Vendor")).getByText("This field is required.")).toBeInTheDocument();
    expect(screen.getByLabelText("Vendor")).toHaveAttribute("aria-invalid", "true");
  });

  it("asks to start editing through its callback", async () => {
    const onEditingChange = vi.fn();
    render(
      <ExtractionPanel
        extraction={EXTRACTION}
        correctedValues={fieldValuesOf(EXTRACTION)}
        canEdit
        onEditingChange={onEditingChange}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Edit fields" }));

    expect(onEditingChange).toHaveBeenCalledWith(true);
  });
});
