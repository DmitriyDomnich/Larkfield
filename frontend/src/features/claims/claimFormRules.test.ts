import { describe, expect, it } from "vitest";

import { getAttendeesProblem } from "./claimFormRules";

const ATTENDEE = { name: "J. Weber", company: "Meridian Health" };

describe("getAttendeesProblem", () => {
  it("accepts up to 50 attendees", () => {
    expect(getAttendeesProblem(Array(50).fill(ATTENDEE))).toBeNull();
  });

  it("refuses more than 50, as the API does", () => {
    expect(getAttendeesProblem(Array(51).fill(ATTENDEE))).toBe("List at most 50 attendees.");
  });
});
