import { describe, expect, it } from "vitest";

import { makeExtraction } from "@/test/fixtures";

import {
  changedFieldLabels,
  fieldValuesOf,
  findFieldProblems,
  toCorrectedFields,
  withCorrections,
} from "./corrections";

const EXTRACTED = fieldValuesOf(makeExtraction());

describe("corrections", () => {
  it("reads the extraction as form values", () => {
    expect(EXTRACTED).toMatchObject({ total: "120.00", document_time: "20:15", vendor_tax_id: "" });
  });

  it("compares money as 2-decimal strings", () => {
    expect(toCorrectedFields(EXTRACTED, { ...EXTRACTED, total: "120" })).toBeNull();
  });

  it("sends only the fields that differ from the extraction, a cleared one as null", () => {
    const values = { ...EXTRACTED, total: "82.5", category: "other", document_number: "", vendor_tax_id: "IT123" };

    expect(toCorrectedFields(EXTRACTED, values)).toEqual({
      total: "82.50",
      category: "other",
      document_number: null,
      vendor_tax_id: "IT123",
    });
  });

  it("lays stored corrections over the extraction and drops a field set back to its value", () => {
    const previous = withCorrections(EXTRACTED, { total: "82.50", tip_amount: null, document_number: null });

    expect(previous).toMatchObject({ total: "82.50", document_number: "" });
    expect(toCorrectedFields(EXTRACTED, previous)).toEqual({ total: "82.50", document_number: null });
    expect(toCorrectedFields(EXTRACTED, { ...previous, total: "120.00" })).toEqual({ document_number: null });
  });

  it("names the fields that changed", () => {
    expect(changedFieldLabels(EXTRACTED, { ...EXTRACTED, total: "99.99", category: "other" })).toEqual([
      "Category",
      "Total",
    ]);
  });

  it("checks the values as the API does", () => {
    expect(findFieldProblems(EXTRACTED)).toEqual({});
    expect(
      Object.keys(
        findFieldProblems({
          ...EXTRACTED,
          vendor_name: " ",
          currency: "eu",
          total: "0",
          tax_amount: "1.234",
          tip_amount: "12345678901",
          vendor_tax_id: "x".repeat(65),
          document_number: "x".repeat(129),
          document_date: "2026-02-30",
        }),
      ).sort(),
    ).toEqual(
      ["currency", "document_date", "document_number", "tax_amount", "tip_amount", "total", "vendor_name", "vendor_tax_id"].sort(),
    );
    expect(findFieldProblems({ ...EXTRACTED, total: "-5" }).total).toBe("The total must be more than 0.");
    expect(findFieldProblems({ ...EXTRACTED, total: "" }).total).toBe("This field is required.");
  });
});
