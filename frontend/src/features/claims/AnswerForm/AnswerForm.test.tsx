import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay } from "msw";
import { describe, expect, it } from "vitest";

import type { ClaimStatus } from "@/api/types";
import { makeClaim } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { AnswerForm } from "./AnswerForm";

const ANSWER = {
  id: "55555555-5555-4555-8555-555555555555",
  reviewer_decision_id: "44444444-4444-4444-8444-444444444444",
  message: "Both attendees were from Meridian Health.",
  changed_fields: {},
  created_at: "2026-11-12T10:00:00Z",
};

describe("AnswerForm", () => {
  it.each<ClaimStatus>(["in_review", "approved", "rejected", "extracted", "failed"])(
    "is hidden for a claim in %s",
    (status) => {
      renderWithClient(<AnswerForm claim={makeClaim({ status })} />);

      expect(screen.queryByRole("button", { name: "Send answer" })).not.toBeInTheDocument();
    },
  );

  it("posts the message with the corrected attendees and pre-approval reference", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post("/claims/{claim_id}/answer", async ({ request, response }) => {
        bodies.push(await request.json());
        return response(201).json(ANSWER);
      }),
    );
    const user = userEvent.setup();
    renderWithClient(<AnswerForm claim={makeClaim({ status: "needs_info" })} />);

    await user.type(screen.getByLabelText("Your answer"), ANSWER.message);
    await user.click(screen.getByRole("button", { name: "Add attendee" }));
    await user.type(screen.getByLabelText("Attendee 2 name"), "A. Novak");
    await user.type(screen.getByLabelText("Attendee 2 company"), "Meridian Health");
    await user.type(screen.getByLabelText("Pre-approval reference"), "PA-2026-114");
    await user.click(screen.getByRole("button", { name: "Send answer" }));

    await expect.poll(() => bodies).toEqual([
      {
        message: ANSWER.message,
        attendees: [
          { name: "J. Weber", company: "Meridian Health" },
          { name: "A. Novak", company: "Meridian Health" },
        ],
        preapproval_ref: "PA-2026-114",
      },
    ]);
  });

  it("asks for a message before sending", async () => {
    renderWithClient(<AnswerForm claim={makeClaim({ status: "needs_info" })} />);

    await userEvent.click(screen.getByRole("button", { name: "Send answer" }));

    expect(screen.getByText(/Write your answer/)).toBeInTheDocument();
  });

  it("disables the button while sending and shows the API's 409 message", async () => {
    const conflict = "The claim cannot move from in_review to extracted";
    server.use(
      http.post("/claims/{claim_id}/answer", async ({ response }) => {
        await delay(50);
        return response(409).json({ detail: conflict });
      }),
    );
    const user = userEvent.setup();
    renderWithClient(<AnswerForm claim={makeClaim({ status: "needs_info" })} />);

    await user.type(screen.getByLabelText("Your answer"), "Here it is");
    await user.click(screen.getByRole("button", { name: "Send answer" }));

    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    expect(await screen.findByText(conflict)).toBeInTheDocument();
  });
});
