import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import type { ClaimRead } from "@/api/types";
import { makeClaim } from "@/test/fixtures";
import { currentPath, router, setUrl } from "@/test/navigation";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { ReviewQueue } from "./ReviewQueue";

vi.mock("next/navigation", () => import("@/test/navigation"));

const USERS = [
  { sub: "employee-1", email: "anna@example.com" },
  { sub: "employee-2", email: "ben@example.com" },
];

function mockQueue(items: ClaimRead[] = [makeClaim()], total = items.length) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get("/claims", ({ request, response }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      return response(200).json({ items, total, limit: 20, offset: Number(query.get("offset")) });
    }),
    http.get("/users", ({ response }) => response(200).json(USERS)),
  );
  return queries;
}

describe("ReviewQueue", () => {
  beforeEach(() => setUrl("/review"));

  it("lists the claims in review with employee and status, each linking to its review page", async () => {
    const claim = makeClaim();
    const queries = mockQueue([claim]);

    renderWithClient(<ReviewQueue />);

    expect(await screen.findByRole("link", { name: claim.purpose })).toHaveAttribute(
      "href",
      `/review/claim?id=${claim.id}`,
    );
    const row = screen.getByRole("row", { name: /receipt\.pdf/ });
    expect(await within(row).findByText("anna@example.com")).toBeInTheDocument();
    expect(within(row).getByText("In review")).toBeInTheDocument();
    expect(queries.map((query) => query.toString())).toEqual(["status=in_review&limit=20&offset=0"]);

    await userEvent.click(screen.getByText("receipt.pdf"));
    expect(router.push).toHaveBeenCalledWith(`/review/claim?id=${claim.id}`);
  });

  it("shows a submitter missing from the user list as unknown", async () => {
    mockQueue([makeClaim({ employee_sub: "employee-gone" })]);

    renderWithClient(<ReviewQueue />);

    expect(await screen.findByText("Unknown user")).toBeInTheDocument();
  });

  it("reads the filters from the URL, so a reload shows the same queue", async () => {
    setUrl("/review?status=all&from=2026-11-01&to=2026-11-02&employee=employee-2");
    const queries = mockQueue();

    renderWithClient(<ReviewQueue />);

    await waitFor(() => expect(screen.getByLabelText("Employee")).toHaveDisplayValue("ben@example.com"));
    expect(screen.getByLabelText("Status")).toHaveDisplayValue("All statuses");
    expect(screen.getByLabelText("From")).toHaveValue("2026-11-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-11-02");
    const [query] = queries;
    expect(query.getAll("status")).toEqual([]);
    expect(query.get("employee_sub")).toBe("employee-2");
    expect(query.get("submitted_after")).toBe(new Date(2026, 10, 1).toISOString());
    expect(query.get("submitted_before")).toBe(new Date(2026, 10, 3).toISOString());
  });

  it("puts a filter change in the URL and asks for the first page with it", async () => {
    setUrl("/review?page=2");
    const queries = mockQueue([makeClaim()], 25);
    renderWithClient(<ReviewQueue />);
    await screen.findByRole("option", { name: "ben@example.com" });

    await userEvent.selectOptions(screen.getByLabelText("Employee"), "ben@example.com");

    expect(currentPath()).toBe("/review?employee=employee-2");
    expect(router.push).not.toHaveBeenCalled();
    const last = queries.at(-1)!;
    expect([last.get("employee_sub"), last.get("offset")]).toEqual(["employee-2", "0"]);
  });

  it("pages through the queue with the page in the URL", async () => {
    setUrl("/review?status=all");
    const queries = mockQueue([makeClaim()], 25);
    renderWithClient(<ReviewQueue />);

    await userEvent.click(await screen.findByRole("button", { name: "Next" }));

    expect(currentPath()).toBe("/review?status=all&page=2");
    expect(queries.at(-1)!.get("offset")).toBe("20");
  });

  it("says when nothing is waiting, or when nothing matches the filters", async () => {
    mockQueue([]);
    const { unmount } = renderWithClient(<ReviewQueue />);
    expect(await screen.findByText("No claims are waiting for review.")).toBeInTheDocument();
    unmount();

    setUrl("/review?from=2026-11-01");
    renderWithClient(<ReviewQueue />);
    expect(await screen.findByText("No claims match these filters.")).toBeInTheDocument();
  });

  it("shows a spinner while loading, and an error when the queue fails", async () => {
    server.use(
      http.get("/claims", ({ response }) => response.untyped(HttpResponse.text("", { status: 500 }))),
      http.get("/users", ({ response }) => response(200).json(USERS)),
    );

    renderWithClient(<ReviewQueue />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
  });
});
