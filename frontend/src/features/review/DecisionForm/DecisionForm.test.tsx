import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { Decision } from "@/api/types";
import { CLAIM_ID, makeClaim } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { rememberQueuePath } from "../queueReturnPath";
import { DecisionForm } from "./DecisionForm";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));

const DECIDED = {
  id: "44444444-4444-4444-8444-444444444444",
  proposal_id: "66666666-6666-4666-8666-666666666666",
  reviewer_sub: "reviewer-1",
  decision: "approve" as Decision,
  comment: null,
  corrected_fields: null,
  created_at: "2026-11-11T10:00:00Z",
};

function mockDecision() {
  const bodies: unknown[] = [];
  server.use(
    http.post("/claims/{claim_id}/decision", async ({ request, response }) => {
      bodies.push(await request.json());
      return response(201).json(DECIDED);
    }),
  );
  return bodies;
}

function renderForm(proposedDecision: Decision) {
  renderWithClient(<DecisionForm claimId={CLAIM_ID} proposedDecision={proposedDecision} />);
}

describe("DecisionForm", () => {
  it("sends the corrected fields with the decision", async () => {
    const bodies = mockDecision();
    renderWithClient(
      <DecisionForm
        claimId={CLAIM_ID}
        proposedDecision="approve"
        correctedFields={{ total: "99.99", category: "other" }}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies).toEqual([
      { decision: "approve", comment: null, corrected_fields: { total: "99.99", category: "other" } },
    ]);
  });

  it("returns to the queue with the filters it was left with after saving", async () => {
    mockDecision();
    rememberQueuePath("status=all&from=2026-11-01");
    renderForm("approve");

    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/review?status=all&from=2026-11-01"));
  });

  it("sends nothing while a corrected field is invalid", async () => {
    const bodies = mockDecision();
    renderWithClient(
      <DecisionForm claimId={CLAIM_ID} proposedDecision="approve" correctedFields={{ total: "0" }} correctionsInvalid />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    expect(screen.getByText("Fix the corrected fields above before saving.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("is preset to the proposal and needs no comment to agree with it", async () => {
    const bodies = mockDecision();
    renderForm("approve");

    expect(screen.getByRole("radio", { name: /Approve/ })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/review"));
    expect(bodies).toEqual([{ decision: "approve", comment: null }]);
  });

  it("requires a comment when the decision differs from the proposal", async () => {
    const bodies = mockDecision();
    const user = userEvent.setup();
    renderForm("approve");

    await user.click(screen.getByRole("radio", { name: /Reject/ }));
    await user.click(screen.getByRole("button", { name: "Save decision" }));
    expect(screen.getByText(/Add a comment/)).toBeInTheDocument();
    expect(bodies).toEqual([]);

    await user.type(screen.getByLabelText(/Comment to the employee/), "Alcohol is not covered.");
    await user.click(screen.getByRole("button", { name: "Save decision" }));
    await expect.poll(() => bodies).toEqual([{ decision: "reject", comment: "Alcohol is not covered." }]);
  });

  it.each<Decision>(["reject", "needs_info"])("requires a comment for %s even when the agent proposed it", async (proposed) => {
    const bodies = mockDecision();
    renderForm(proposed);

    expect(screen.getByLabelText(/Comment to the employee \(required\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    expect(screen.getByText(/Add a comment/)).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("refuses a comment over 2000 characters before sending", async () => {
    const bodies = mockDecision();
    const user = userEvent.setup();
    renderForm("approve");

    await user.click(screen.getByLabelText(/Comment to the employee/));
    await user.paste("x".repeat(2001));
    await user.click(screen.getByRole("button", { name: "Save decision" }));

    expect(screen.getByText("Keep the comment to 2000 characters.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("shows the server's 422 detail", async () => {
    const detail = "A comment is required for reject and needs_info, and when the decision differs from the proposal";
    server.use(http.post("/claims/{claim_id}/decision", ({ response }) => response(422).json({ detail })));
    renderForm("approve");

    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    expect(await screen.findByText(detail)).toBeInTheDocument();
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("says the claim was already decided on a 409, and reloads the claim", async () => {
    server.use(
      http.post("/claims/{claim_id}/decision", async ({ response }) => {
        await delay(50);
        return response(409).json({ detail: "The claim cannot move from approved to approved" });
      }),
    );
    const { queryClient } = renderWithClient(
      <DecisionForm claimId={CLAIM_ID} proposedDecision="approve" />,
    );
    queryClient.setQueryData(["claims", CLAIM_ID], makeClaim());

    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(await screen.findByText(/already been decided/)).toBeInTheDocument();
    expect(navigation.push).not.toHaveBeenCalled();
    expect(queryClient.getQueryState(["claims", CLAIM_ID])?.isInvalidated).toBe(true);
  });
});
