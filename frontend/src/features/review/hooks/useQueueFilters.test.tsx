import { act, renderHook } from "@testing-library/react";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { router, setUrl } from "@/test/navigation";

import {
  applyFilterChanges,
  parseQueueFilters,
  toClaimsQuery,
  toSearchParams,
  useQueueFilters,
  type QueueFilters,
} from "./useQueueFilters";

vi.mock("next/navigation", () => import("@/test/navigation"));

const DEFAULTS: QueueFilters = { statuses: ["in_review"], from: null, to: null, employee: null, page: 1 };

function parse(search: string) {
  return parseQueueFilters(new URLSearchParams(search));
}

describe("parseQueueFilters", () => {
  it("defaults to today's queue: claims in review, first page", () => {
    expect(parse("")).toEqual(DEFAULTS);
  });

  it("reads every filter", () => {
    expect(
      parse("status=needs_info&status=approved&from=2026-11-01&to=2026-11-03&employee=sub-a&page=2"),
    ).toEqual({
      statuses: ["needs_info", "approved"],
      from: "2026-11-01",
      to: "2026-11-03",
      employee: "sub-a",
      page: 2,
    });
    expect(parse("status=all").statuses).toBe("all");
  });

  it.each([
    ["status=bogus", { statuses: ["in_review"] }],
    ["status=bogus&status=approved", { statuses: ["approved"] }],
    ["from=2026-13-01&to=yesterday", { from: null, to: null }],
    ["from=2026-02-30", { from: null }],
    ["from=2026-11-05&to=2026-11-01", { from: null, to: null }],
    ["page=0", { page: 1 }],
    ["page=-2", { page: 1 }],
    ["page=2.5", { page: 1 }],
    ["page=abc", { page: 1 }],
    [`employee=${"x".repeat(129)}`, { employee: null }],
  ])("falls back to the default for %s", (search, expected) => {
    expect(parse(search)).toEqual({ ...DEFAULTS, ...expected });
  });
});

describe("toSearchParams", () => {
  it("writes nothing for the defaults and every other value as read back", () => {
    const filters: QueueFilters = {
      statuses: "all",
      from: "2026-11-01",
      to: "2026-11-02",
      employee: "sub-a",
      page: 3,
    };

    expect(toSearchParams(DEFAULTS).toString()).toBe("");
    expect(toSearchParams(filters).toString()).toBe(
      "status=all&from=2026-11-01&to=2026-11-02&employee=sub-a&page=3",
    );
    expect(parseQueueFilters(toSearchParams(filters))).toEqual(filters);
  });
});

describe("toClaimsQuery", () => {
  const timeZone = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = "Europe/Kyiv";
  });
  afterAll(() => {
    process.env.TZ = timeZone;
  });

  it("sends local midnight of `from` and of the day after `to`", () => {
    const query = toClaimsQuery({ ...DEFAULTS, from: "2026-11-01", to: "2026-11-01" });

    expect(query.submitted_after).toBe("2026-10-31T22:00:00.000Z");
    expect(query.submitted_before).toBe("2026-11-01T22:00:00.000Z");
  });

  it("maps the statuses, employee and page", () => {
    expect(toClaimsQuery({ ...DEFAULTS, employee: "sub-a", page: 3 })).toEqual({
      status: ["in_review"],
      employee_sub: "sub-a",
      limit: 20,
      offset: 40,
    });
    expect(toClaimsQuery({ ...DEFAULTS, statuses: "all" })).toEqual({ limit: 20, offset: 0 });
  });
});

describe("applyFilterChanges", () => {
  const range: QueueFilters = { ...DEFAULTS, from: "2026-11-02", to: "2026-11-04", page: 4 };

  it("resets the page", () => {
    expect(applyFilterChanges(range, { employee: "sub-a" })).toEqual({ ...range, employee: "sub-a", page: 1 });
  });

  it("clears the other end of the range when it would be reversed", () => {
    expect(applyFilterChanges(range, { from: "2026-11-05" })).toMatchObject({ from: "2026-11-05", to: null });
    expect(applyFilterChanges(range, { to: "2026-11-01" })).toMatchObject({ from: null, to: "2026-11-01" });
  });
});

describe("useQueueFilters", () => {
  beforeEach(() => setUrl("/review?status=all&page=3"));

  it("reads the filters from the URL", () => {
    const { result } = renderHook(() => useQueueFilters());

    expect(result.current.filters).toEqual({ ...DEFAULTS, statuses: "all", page: 3 });
  });

  it("replaces the URL on a filter change, back on the first page", () => {
    const { result } = renderHook(() => useQueueFilters());

    act(() => result.current.changeFilters({ employee: "sub-a" }));

    expect(router.replace).toHaveBeenCalledWith("/review?status=all&employee=sub-a", { scroll: false });
    expect(result.current.filters).toMatchObject({ employee: "sub-a", page: 1 });
    expect(router.push).not.toHaveBeenCalled();
  });

  it("keeps the filters when the page changes", () => {
    const { result } = renderHook(() => useQueueFilters());

    act(() => result.current.changePage(4));

    expect(router.replace).toHaveBeenCalledWith("/review?status=all&page=4", { scroll: false });
  });

  it("goes back to the bare path for the default filters", () => {
    const { result } = renderHook(() => useQueueFilters());

    act(() => result.current.changeFilters({ statuses: ["in_review"] }));

    expect(router.replace).toHaveBeenCalledWith("/review", { scroll: false });
  });
});
