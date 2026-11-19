import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import { makeClaim } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { ClaimList } from "./ClaimList";

const FAILED = makeClaim({
  id: "22222222-2222-4222-8222-222222222222",
  status: "failed",
  purpose: "Taxi to the airport",
  failure_reason: "The document could not be read: blurry. Please submit a new claim.",
});
const IN_REVIEW = makeClaim();

function mockClaimPages(total: number) {
  const offsets: (string | null)[] = [];
  server.use(
    http.get("/claims", ({ request, response }) => {
      const offset = Number(new URL(request.url).searchParams.get("offset"));
      offsets.push(new URL(request.url).searchParams.get("offset"));
      const items = offset === 0 ? [IN_REVIEW, FAILED] : [makeClaim({ purpose: "Hotel in Vienna" })];
      return response(200).json({ items, total, limit: 20, offset });
    }),
  );
  return offsets;
}

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));

describe("ClaimList", () => {
  it("lists the claims with their status and failure reason", async () => {
    mockClaimPages(2);

    renderWithClient(<ClaimList />);

    expect(await screen.findByRole("link", { name: IN_REVIEW.purpose })).toHaveAttribute(
      "href",
      `/claims/view?id=${IN_REVIEW.id}`,
    );
    expect(screen.getByText("In review")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(FAILED.failure_reason!)).toBeInTheDocument();
    expect(screen.getByText("1–2 of 2")).toBeInTheDocument();
  });

  it("opens a claim by clicking anywhere on its row", async () => {
    mockClaimPages(2);
    renderWithClient(<ClaimList />);

    await userEvent.click(await screen.findByText("Failed"));

    expect(navigation.push).toHaveBeenCalledWith(`/claims/view?id=${FAILED.id}`);
  });

  it("pages through 20 claims at a time", async () => {
    const offsets = mockClaimPages(21);
    renderWithClient(<ClaimList />);

    await userEvent.click(await screen.findByRole("button", { name: "Next" }));

    expect(await screen.findByText("Hotel in Vienna")).toBeInTheDocument();
    expect(screen.getByText("21–21 of 21")).toBeInTheDocument();
    expect(offsets).toEqual(["0", "20"]);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("says when there are no claims", async () => {
    server.use(
      http.get("/claims", ({ response }) => response(200).json({ items: [], total: 0, limit: 20, offset: 0 })),
    );

    renderWithClient(<ClaimList />);

    expect(await screen.findByText("No claims yet.")).toBeInTheDocument();
  });

  it("shows a spinner while loading, and an error when the list fails", async () => {
    server.use(http.get("/claims", ({ response }) => response.untyped(HttpResponse.text("", { status: 500 }))));

    renderWithClient(<ClaimList />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
  });
});
