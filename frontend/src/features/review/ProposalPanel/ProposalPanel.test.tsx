import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import { makeClaim, makeProposal, makeRound, mockReview } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { ProposalPanel } from "./ProposalPanel";

const INJECTED = '<img src=x onerror="alert(1)"> **bold**';

describe("ProposalPanel", () => {
  it("shows the decision, each clause with its quote and explanation, and what is missing", async () => {
    mockReview([
      makeRound({
        proposal: makeProposal({
          decision: "needs_info",
          missing_information: ["The names and companies of all attendees"],
          duplicate_of: "88888888-8888-4888-8888-888888888888",
        }),
      }),
    ]);

    renderWithClient(<ProposalPanel claim={makeClaim()} />);

    expect(await screen.findByText("Request information")).toBeInTheDocument();
    expect(screen.getByText("Clause 3.1")).toBeInTheDocument();
    expect(screen.getByText("Client meals are reimbursable up to EUR 80 per person.")).toBeInTheDocument();
    expect(screen.getByText("Two attendees, EUR 120 in total, within the limit.")).toBeInTheDocument();
    expect(screen.getByText("The names and companies of all attendees")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "this claim" })).toHaveAttribute(
      "href",
      "/review/claim?id=88888888-8888-4888-8888-888888888888",
    );
  });

  it("renders model-written quotes and explanations as text, never as HTML", async () => {
    mockReview([
      makeRound({
        proposal: makeProposal({
          reasons: [{ clause_id: "3.1", quote: INJECTED, explanation: INJECTED }],
        }),
      }),
    ]);

    const { container } = renderWithClient(<ProposalPanel claim={makeClaim()} />);

    expect(await screen.findAllByText(INJECTED)).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("strong:not(:first-child)")).toBeNull();
  });

  it("keeps earlier rounds collapsed until opened", async () => {
    mockReview([
      makeRound(),
      makeRound({
        proposal: makeProposal({ id: "99999999-9999-4999-8999-999999999999", decision: "needs_info" }),
        answer: {
          id: "55555555-5555-4555-8555-555555555555",
          reviewer_decision_id: "44444444-4444-4444-8444-444444444444",
          message: "Both attendees were from Meridian Health.",
          changed_fields: {},
          created_at: "2026-11-12T10:00:00Z",
        },
      }),
    ]);
    renderWithClient(<ProposalPanel claim={makeClaim()} />);

    const trigger = await screen.findByRole("button", { name: /Earlier rounds \(1\)/ });
    expect(screen.queryByText(/Both attendees were from Meridian Health/)).not.toBeInTheDocument();
    await userEvent.click(trigger);

    expect(screen.getByText(/Both attendees were from Meridian Health/)).toBeInTheDocument();
  });

  it("shows a spinner while loading, and an error when the history fails", async () => {
    server.use(
      http.get("/claims/{claim_id}/review", ({ response }) => response.untyped(HttpResponse.text("", { status: 500 }))),
    );

    renderWithClient(<ProposalPanel claim={makeClaim()} />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
  });
});
