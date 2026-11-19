import { describe, expect, it } from "vitest";

import { formatEnumValue, formatQuantity, formatUnitPrice } from "./format";

describe("formatEnumValue", () => {
  it.each([
    ["meal", "Meal"],
    ["taxi", "Taxi"],
    ["client_entertainment", "Client entertainment"],
    ["card_slip", "Card slip"],
  ])("%s → %s", (value, label) => {
    expect(formatEnumValue(value)).toBe(label);
  });
});

describe("formatQuantity", () => {
  it.each([
    ["1.000", "1"],
    ["2", "2"],
    ["1.500", "1.5"],
    ["0.250", "0.25"],
    ["10.000", "10"],
  ])("%s → %s", (value, shown) => {
    expect(formatQuantity(value)).toBe(shown);
  });
});

describe("formatUnitPrice", () => {
  it.each([
    ["14.5000", "14.50"],
    ["45.0000", "45.00"],
    ["0.0450", "0.045"],
    ["3.1234", "3.1234"],
    ["3", "3.00"],
  ])("%s → %s", (value, shown) => {
    expect(formatUnitPrice(value)).toBe(shown);
  });
});
