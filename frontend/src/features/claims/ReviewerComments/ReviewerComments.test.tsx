import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeClaim, makeRound, mockReview } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";

import { ReviewerComments } from "./ReviewerComments";

function makeDecidedRound(id: string, comment: string, createdAt: string) {
  return makeRound({
    proposal_id: id,
    proposal: null,
    decision: {
      id: `${id.slice(0, -1)}0`,
      proposal_id: id,
      reviewer_sub: "reviewer-1",
      decision: "needs_info",
      comment,
      corrected_fields: null,
      created_at: createdAt,
    },
  });
}

describe("ReviewerComments", () => {
  it("lists the rounds oldest first and marks the latest", async () => {
    mockReview([
      makeDecidedRound("22222222-2222-4222-8222-222222222222", "Sorry, need to decline this again", "2026-11-19T16:45:00Z"),
      makeDecidedRound("11111111-1111-4111-8111-111111111111", "List attendees please", "2026-11-16T15:09:00Z"),
    ]);

    renderWithClient(<ReviewerComments claim={makeClaim({ status: "needs_info" })} />);

    const items = await screen.findAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining("List attendees please"),
      expect.stringContaining("Sorry, need to decline this again"),
    ]);
    expect(within(items[1]).getByText("Latest")).toBeInTheDocument();
    expect(within(items[0]).queryByText("Latest")).not.toBeInTheDocument();
    expect(items[1]).toHaveClass("border-primary");
    expect(items[0]).not.toHaveClass("border-primary");
  });

  it("shows its children inside the latest round", async () => {
    mockReview([
      makeDecidedRound("22222222-2222-4222-8222-222222222222", "Newest request", "2026-11-19T16:45:00Z"),
      makeDecidedRound("11111111-1111-4111-8111-111111111111", "Older request", "2026-11-16T15:09:00Z"),
    ]);

    renderWithClient(
      <ReviewerComments claim={makeClaim({ status: "needs_info" })}>
        <p>The answer form</p>
      </ReviewerComments>,
    );

    const items = await screen.findAllByRole("listitem");
    expect(within(items[1]).getByText("The answer form")).toBeInTheDocument();
    expect(within(items[0]).queryByText("The answer form")).not.toBeInTheDocument();
  });

  it("marks nothing on a single round", async () => {
    mockReview([
      makeDecidedRound("11111111-1111-4111-8111-111111111111", "List attendees please", "2026-11-16T15:09:00Z"),
    ]);

    renderWithClient(<ReviewerComments claim={makeClaim({ status: "needs_info" })} />);

    const [item] = await screen.findAllByRole("listitem");
    expect(screen.queryByText("Latest")).not.toBeInTheDocument();
    expect(item).not.toHaveClass("border-primary");
  });

  it("shows nothing before a reviewer has decided", async () => {
    mockReview([makeRound()]);

    const { container } = renderWithClient(
      <ReviewerComments claim={makeClaim({ status: "in_review" })} />,
    );

    await expect.poll(() => container.querySelector("[role=status]")).toBeNull();
    expect(screen.queryByText("Reviewer comments")).not.toBeInTheDocument();
  });
});
