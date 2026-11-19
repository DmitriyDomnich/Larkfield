import { act, screen } from "@testing-library/react";
import { HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import { CLAIM_ID, makeClaim, mockClaim, mockFileLink, mockReview } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { POLL_INTERVAL_MS } from "../hooks/useClaim";
import { ClaimDetail } from "./ClaimDetail";

const navigation = vi.hoisted(() => ({ id: "11111111-1111-4111-8111-111111111111" as string | null }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.id ? { id: navigation.id } : {}),
}));

afterEach(() => {
  vi.useRealTimers();
  server.events.removeAllListeners();
  navigation.id = CLAIM_ID;
});

function countClaimRequests() {
  const counter = { calls: 0 };
  server.events.on("request:start", ({ request }) => {
    if (new URL(request.url).pathname === `/claims/${CLAIM_ID}`) counter.calls += 1;
  });
  return counter;
}

describe("ClaimDetail", () => {
  it("polls while the document is processed and stops once it waits for a reviewer", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const requests = countClaimRequests();
    mockClaim(
      makeClaim({ status: "extracting", document: { ...makeClaim().document!, size_bytes: 2048 } }),
      makeClaim({ status: "in_review" }),
    );
    mockFileLink();
    mockReview();

    renderWithClient(<ClaimDetail />);
    expect(await screen.findByText("Reading document")).toBeInTheDocument();
    expect(screen.getByText(/being processed/)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(await screen.findByText("In review")).toBeInTheDocument();
    expect(screen.queryByText(/being processed/)).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3));
    expect(requests.calls).toBe(2);
  });

  it("shows the file link, the reviewer's comments and the failure reason", async () => {
    mockClaim(makeClaim({ status: "rejected", failure_reason: null }));
    mockFileLink();
    mockReview([
      {
        proposal_id: "33333333-3333-4333-8333-333333333333",
        proposal: null,
        decision: {
          id: "44444444-4444-4444-8444-444444444444",
          proposal_id: "33333333-3333-4333-8333-333333333333",
          reviewer_sub: "reviewer-1",
          decision: "reject",
          comment: "Alcohol is not reimbursable (policy 3.2).",
          corrected_fields: null,
          created_at: "2026-11-11T10:00:00Z",
        },
        answer: null,
      },
    ]);

    renderWithClient(<ClaimDetail />);

    expect(await screen.findByRole("link", { name: "receipt.pdf" })).toHaveAttribute(
      "href",
      "https://documents.test/claims/receipt.pdf?signature=abc",
    );
    expect(await screen.findByText("Alcohol is not reimbursable (policy 3.2).")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Claims" })).toHaveAttribute("href", "/claims");
    expect(screen.getByText("Rejected", { selector: "p" })).toBeInTheDocument();
  });

  it("shows why a claim failed", async () => {
    mockClaim(makeClaim({ status: "failed", failure_reason: "The document could not be read." }));
    mockFileLink();
    mockReview();

    renderWithClient(<ClaimDetail />);

    expect(await screen.findByText("The document could not be read.")).toBeInTheDocument();
  });

  it("shows the not-found notice without an id", () => {
    navigation.id = null;

    renderWithClient(<ClaimDetail />);

    expect(screen.getByText("Page not found")).toBeInTheDocument();
  });

  it("shows the API's detail for a missing claim", async () => {
    server.use(
      http.get("/claims/{claim_id}", ({ response }) => response(404).json({ detail: "Claim not found" })),
    );

    renderWithClient(<ClaimDetail />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByText("Claim not found")).toBeInTheDocument();
  });

  it("shows a generic error when the claim can't be loaded", async () => {
    server.use(
      http.get("/claims/{claim_id}", ({ response }) => response.untyped(HttpResponse.text("", { status: 500 }))),
    );

    renderWithClient(<ClaimDetail />);

    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
  });
});
