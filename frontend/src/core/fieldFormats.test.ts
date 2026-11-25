import { describe, expect, it } from "vitest";

import { isCalendarDate, normalizeMoney } from "./fieldFormats";

describe("isCalendarDate", () => {
  it.each(["2026-11-01", "2028-02-29"])("accepts %s", (value) => {
    expect(isCalendarDate(value)).toBe(true);
  });

  it.each(["2026-02-30", "2026-13-01", "2026-11-1", "yesterday", ""])("refuses %s", (value) => {
    expect(isCalendarDate(value)).toBe(false);
  });
});

describe("normalizeMoney", () => {
  it.each([
    ["28.5", "28.50"],
    ["007", "7.00"],
    [" 120.00 ", "120.00"],
    ["-3.1", "-3.10"],
    ["1.234", "1.234"],
  ])("%s → %s", (value, expected) => {
    expect(normalizeMoney(value)).toBe(expected);
  });
});
