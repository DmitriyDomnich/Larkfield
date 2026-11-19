import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import {
  makeClaim,
  makeRound,
  mockClaim,
  mockExtraction,
  mockFileLink,
  mockMe,
  mockReview,
} from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { ReviewClaim } from "./ReviewClaim";

const navigation = vi.hoisted(() => ({ id: "11111111-1111-4111-8111-111111111111" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams({ id: navigation.id }),
  useRouter: () => ({ push: vi.fn() }),
}));

const FILE_URL = "https://documents.test/claims/receipt.pdf?signature=abc";

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
    expect(screen.getByText("Receipt R-2041")).toBeInTheDocument();
    expect(screen.getByText(/add up to 99.00, the total is 120.00/)).toBeInTheDocument();
    expect(
      await screen.findByText("Client meals are reimbursable up to EUR 80 per person."),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save decision" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Review queue" })).toHaveAttribute("href", "/review");
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
