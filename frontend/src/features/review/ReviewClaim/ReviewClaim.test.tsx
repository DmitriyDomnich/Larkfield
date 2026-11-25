import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import {
  makeClaim,
  makeExtraction,
  makeProposal,
  makeRound,
  mockClaim,
  mockExtraction,
  mockFileLink,
  mockMe,
  mockReview,
} from "@/test/fixtures";
import { useMe } from "@/features/auth/hooks/useMe";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { rememberQueuePath } from "../queueReturnPath";
import { ReviewClaim } from "./ReviewClaim";

const navigation = vi.hoisted(() => ({ id: "11111111-1111-4111-8111-111111111111", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams({ id: navigation.id }),
  useRouter: () => ({ push: navigation.push }),
}));

const FILE_URL = "https://documents.test/claims/receipt.pdf?signature=abc";

function mockDecisions() {
  const bodies: unknown[] = [];
  server.use(
    http.post("/claims/{claim_id}/decision", async ({ request, response }) => {
      bodies.push(await request.json());
      return response(201).json({
        id: "44444444-4444-4444-8444-444444444444",
        proposal_id: "66666666-6666-4666-8666-666666666666",
        reviewer_sub: "reviewer-1",
        decision: "approve",
        comment: null,
        corrected_fields: null,
        created_at: "2026-11-11T10:00:00Z",
      });
    }),
  );
  return bodies;
}

function fieldRow(label: string) {
  return screen.getByText(label, { selector: "dt, label" }).closest("div")!;
}

const EARLIER_ROUND = makeRound({
  proposal_id: "55555555-5555-4555-8555-555555555555",
  proposal: makeProposal({ id: "55555555-5555-4555-8555-555555555555", decision: "needs_info" }),
  decision: {
    id: "33333333-3333-4333-8333-333333333333",
    proposal_id: "55555555-5555-4555-8555-555555555555",
    reviewer_sub: "reviewer-1",
    decision: "needs_info",
    comment: "Who attended?",
    corrected_fields: { total: "82.50" },
    created_at: "2026-11-10T10:00:00Z",
  },
});

function mockAllPanels() {
  mockMe("reviewer");
  mockClaim(makeClaim());
  mockFileLink();
  mockExtraction();
  mockReview([makeRound()]);
}

describe("ReviewClaim", () => {
  afterEach(() => {
    navigation.id = "11111111-1111-4111-8111-111111111111";
  });

  it("starts a fresh decision form when another claim opens", async () => {
    mockAllPanels();
    const otherId = "88888888-8888-4888-8888-888888888888";
    server.use(
      http.get("/claims/{claim_id}", ({ params, response }) =>
        response(200).json(makeClaim({ id: params.claim_id, purpose: `Claim ${params.claim_id}` })),
      ),
    );
    const user = userEvent.setup();
    const { rerender, queryClient } = renderWithClient(<ReviewClaim />);
    await user.click(await screen.findByRole("radio", { name: /Reject/ }));
    await user.type(screen.getByLabelText(/Comment to the employee/), "Alcohol is not covered.");
    // already cached (opened before), so the page switches without unmounting the form
    queryClient.setQueryData(["claims", otherId], makeClaim({ id: otherId, purpose: `Claim ${otherId}` }));
    queryClient.setQueryData(["claims", otherId, "review", "in_review"], {
      claim_id: otherId,
      rounds: [makeRound({ proposal_id: "99999999-9999-4999-8999-999999999999" })],
    });

    navigation.id = otherId;
    rerender(<ReviewClaim />);

    expect(await screen.findByRole("heading", { name: `Claim ${otherId}` })).toBeInTheDocument();
    expect(await screen.findByRole("radio", { name: /Approve/ })).toBeChecked();
    expect(screen.getByLabelText(/Comment to the employee/)).toHaveValue("");
  });

  it("renders the claim, the document, the extraction, the proposal and the decision form", async () => {
    mockAllPanels();

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByRole("heading", { name: makeClaim().purpose })).toBeInTheDocument();
    expect(await screen.findByTitle("receipt.pdf")).toHaveAttribute("src", FILE_URL);
    expect(await screen.findByText("Trattoria Roma")).toBeInTheDocument();
    expect(screen.getByText("120.00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Menu del giorno")).toBeInTheDocument();
    expect(screen.getByText("Client entertainment")).toBeInTheDocument();
    expect(screen.getByText("Receipt")).toBeInTheDocument();
    expect(screen.getByText("R-2041")).toBeInTheDocument();
    expect(screen.getByText(/add up to 99.00, the total is 120.00/)).toBeInTheDocument();
    expect(
      await screen.findByText("Client meals are reimbursable up to EUR 80 per person."),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save decision" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Review queue" })).toHaveAttribute("href", "/review");
  });

  it("links back to the queue with the filters it was left with", async () => {
    mockAllPanels();
    rememberQueuePath("status=all&employee=employee-2");

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByRole("link", { name: "← Review queue" })).toHaveAttribute(
      "href",
      "/review?status=all&employee=employee-2",
    );
  });

  it("returns to the filtered queue after saving, though the reloaded claim replaces the form", async () => {
    mockAllPanels();
    mockClaim(makeClaim(), makeClaim({ status: "approved" }));
    mockDecisions();
    // the reloaded extraction lands after the reloaded claim, as over a real network
    let extractionCalls = 0;
    server.use(
      http.get("/claims/{claim_id}/extraction", async ({ response }) => {
        extractionCalls += 1;
        if (extractionCalls > 1) await delay(200);
        return response(200).json(makeExtraction());
      }),
    );
    rememberQueuePath("employee=employee-2");
    const user = userEvent.setup();
    renderWithClient(<ReviewClaim />);

    await user.click(await screen.findByRole("button", { name: "Save decision" }));

    expect(await screen.findByText(/This claim has already been decided/)).toBeInTheDocument();
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/review?employee=employee-2"));
  });

  it("asks for the user and the review history once", async () => {
    mockAllPanels();
    const requests: string[] = [];
    server.events.on("request:start", ({ request }) => {
      requests.push(new URL(request.url).pathname);
    });
    // the app shell asks for the user before the page renders
    function Shell() {
      useMe();
      return <ReviewClaim />;
    }

    renderWithClient(<Shell />);

    expect(await screen.findByRole("button", { name: "Save decision" })).toBeInTheDocument();
    await screen.findByText("Clause 3.1");
    server.events.removeAllListeners("request:start");
    expect(requests.filter((path) => path === "/me")).toHaveLength(1);
    expect(requests.filter((path) => path.endsWith("/review"))).toHaveLength(1);
  });

  it("corrects fields, names them on the proposal and sends only them with the decision", async () => {
    mockAllPanels();
    const bodies = mockDecisions();
    const user = userEvent.setup();
    renderWithClient(<ReviewClaim />);

    await user.click(await screen.findByRole("button", { name: "Edit fields" }));
    await user.clear(screen.getByLabelText("Total"));
    await user.type(screen.getByLabelText("Total"), "99.99");
    await user.selectOptions(screen.getByLabelText("Category"), "Other");

    expect(within(fieldRow("Total")).getByText("Corrected")).toBeInTheDocument();
    expect(
      screen.getByText(/made on the values before your corrections \(Category, Total\)/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies).toEqual([
      { decision: "approve", comment: null, corrected_fields: { total: "99.99", category: "other" } },
    ]);
  });

  it("sends nothing while a corrected field is invalid", async () => {
    mockAllPanels();
    const bodies = mockDecisions();
    const user = userEvent.setup();
    renderWithClient(<ReviewClaim />);

    await user.click(await screen.findByRole("button", { name: "Edit fields" }));
    await user.clear(screen.getByLabelText("Total"));
    await user.type(screen.getByLabelText("Total"), "0");
    await user.click(screen.getByRole("button", { name: "Save decision" }));

    expect(within(fieldRow("Total")).getByText("The total must be more than 0.")).toBeInTheDocument();
    expect(screen.getByText("Fix the corrected fields above before saving.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("starts a second round from the previous corrections and sends them again", async () => {
    mockAllPanels();
    mockReview([makeRound(), EARLIER_ROUND]);
    const bodies = mockDecisions();
    const user = userEvent.setup();
    renderWithClient(<ReviewClaim />);

    const total = await screen.findByText("82.50 EUR");
    expect(within(fieldRow("Total")).getByText("Corrected")).toBeInTheDocument();
    expect(within(fieldRow("Total")).getByText("120.00 EUR").tagName).toBe("S");
    expect(total).toBeInTheDocument();
    expect(screen.queryByText(/before your corrections/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit fields" }));
    expect(screen.getByLabelText("Total")).toHaveValue("82.50");
    await user.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies).toEqual([{ decision: "approve", comment: null, corrected_fields: { total: "82.50" } }]);
  });

  it("shows a decided claim's corrections without a form", async () => {
    mockAllPanels();
    mockClaim(makeClaim({ status: "approved" }));
    mockExtraction(makeExtraction());
    mockReview([
      makeRound({
        decision: { ...EARLIER_ROUND.decision!, decision: "approve", corrected_fields: { total: "99.99", category: "other" } },
      }),
    ]);

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByText("99.99 EUR")).toBeInTheDocument();
    expect(within(fieldRow("Category")).getByText("Corrected")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit fields" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("offers no editing on the reviewer's own claim", async () => {
    mockAllPanels();
    mockClaim(makeClaim({ employee_sub: "reviewer-1" }));

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByText(/This is your own claim/)).toBeInTheDocument();
    expect(await screen.findByText("Trattoria Roma")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit fields" })).not.toBeInTheDocument();
  });

  it("shows an image document as an image", async () => {
    mockAllPanels();
    mockClaim(
      makeClaim({
        document: { original_filename: "receipt.png", content_type: "image/png", size_bytes: 2048 },
      }),
    );

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByRole("img", { name: "receipt.png" })).toHaveAttribute("src", FILE_URL);
  });

  it("fetches a new document link on Reload document", async () => {
    mockAllPanels();
    let linkFetches = 0;
    server.use(
      http.get("/claims/{claim_id}/file", ({ response }) => {
        linkFetches += 1;
        return response(200).json({ url: FILE_URL, expires_at: "2026-11-10T09:10:00Z" });
      }),
    );
    renderWithClient(<ReviewClaim />);
    await screen.findByTitle("receipt.pdf");

    await userEvent.click(screen.getByRole("button", { name: "Reload document" }));

    await expect.poll(() => linkFetches).toBe(2);
  });

  it("shows a notice instead of the form on the reviewer's own claim", async () => {
    mockAllPanels();
    mockClaim(makeClaim({ employee_sub: "reviewer-1" }));
    mockReview([makeRound({ proposal: null })]);

    renderWithClient(<ReviewClaim />);

    expect(
      await screen.findByText("This is your own claim. Another reviewer decides it."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save decision" })).not.toBeInTheDocument();
  });

  it("shows that the claim is decided instead of the form", async () => {
    mockAllPanels();
    mockClaim(makeClaim({ status: "approved" }));

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByText(/This claim has already been decided/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save decision" })).not.toBeInTheDocument();
  });

  it("keeps saying the claim is decided after a 409 reloads it", async () => {
    mockAllPanels();
    mockClaim(makeClaim({ status: "in_review" }), makeClaim({ status: "approved" }));
    server.use(
      http.post("/claims/{claim_id}/decision", ({ response }) =>
        response(409).json({ detail: "The claim cannot move from approved to approved" }),
      ),
    );
    renderWithClient(<ReviewClaim />);

    await userEvent.click(await screen.findByRole("button", { name: "Save decision" }));

    expect(await screen.findByText(/This claim has already been decided/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save decision" })).not.toBeInTheDocument();
  });

  it("keeps the other panels when the extraction fails", async () => {
    mockAllPanels();
    server.use(
      http.get("/claims/{claim_id}/extraction", ({ response }) =>
        response.untyped(HttpResponse.text("", { status: 500 })),
      ),
    );

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
    expect(await screen.findByTitle("receipt.pdf")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save decision" })).toBeInTheDocument();
  });

  it("shows the API's detail when the claim has no extraction yet", async () => {
    mockAllPanels();
    server.use(
      http.get("/claims/{claim_id}/extraction", ({ response }) =>
        response(404).json({ detail: "The claim has no extraction yet" }),
      ),
    );

    renderWithClient(<ReviewClaim />);

    expect(await screen.findByText("The claim has no extraction yet")).toBeInTheDocument();
  });

  it("shows a spinner while the claim loads, and its error when it fails", async () => {
    mockAllPanels();
    server.use(
      http.get("/claims/{claim_id}", ({ response }) =>
        response(404).json({ detail: "Claim not found" }),
      ),
    );

    renderWithClient(<ReviewClaim />);

    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(await screen.findByText("Claim not found")).toBeInTheDocument();
  });
});
