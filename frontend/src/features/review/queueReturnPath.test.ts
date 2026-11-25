import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getQueuePath, rememberQueuePath } from "./queueReturnPath";

describe("queueReturnPath", () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("returns the last filtered queue, or the bare queue before any", () => {
    expect(getQueuePath()).toBe("/review");

    rememberQueuePath("status=all&employee=sub-a");
    expect(getQueuePath()).toBe("/review?status=all&employee=sub-a");

    rememberQueuePath("");
    expect(getQueuePath()).toBe("/review");
  });

  it.each(["https://evil.test/review", "/reviewer", "//evil.test"])("ignores a stored %s", (stored) => {
    sessionStorage.setItem("larkfield.reviewQueuePath", stored);

    expect(getQueuePath()).toBe("/review");
  });

  it("falls back to the bare queue when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(() => rememberQueuePath("status=all")).not.toThrow();
    expect(getQueuePath()).toBe("/review");
  });
});
