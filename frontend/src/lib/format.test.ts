import { describe, expect, it } from "vitest";

import { formatEnumValue } from "./format";

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
