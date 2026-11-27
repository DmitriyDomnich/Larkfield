import type { components } from "@/api/schema";

import { http, server } from "./server";

type Role = components["schemas"]["Role"];

export function mockMe(role: Role) {
  server.use(
    http.get("/me", ({ response }) =>
      response(200).json({ sub: `${role}-1`, email: `${role}@example.com`, role }),
    ),
  );
}

type ClaimRead = components["schemas"]["ClaimRead"];

export const CLAIM_ID = "11111111-1111-4111-8111-111111111111";

export function makeClaim(changes: Partial<ClaimRead> = {}): ClaimRead {
  return {
    id: CLAIM_ID,
    employee_sub: "employee-1",
    status: "in_review",
    purpose: "Dinner with Meridian Health about the 2027 contract",
    attendees: [{ name: "J. Weber", company: "Meridian Health" }],
    preapproval_ref: null,
    failure_reason: null,
    submitted_at: "2026-11-10T09:00:00Z",
    updated_at: "2026-11-10T09:05:00Z",
    document: { original_filename: "receipt.pdf", content_type: "application/pdf", size_bytes: 2048 },
    ...changes,
  };
}

export function mockClaim(...claims: ClaimRead[]) {
  let call = 0;
  server.use(
    http.get("/claims/{claim_id}", ({ response }) => {
      const claim = claims[Math.min(call, claims.length - 1)];
      call += 1;
      return response(200).json(claim);
    }),
  );
}

export function mockFileLink() {
  server.use(
    http.get("/claims/{claim_id}/file", ({ response }) =>
      response(200).json({
        url: "https://documents.test/claims/receipt.pdf?signature=abc",
        expires_at: "2026-11-10T09:10:00Z",
      }),
    ),
  );
}

export function mockReview(rounds: components["schemas"]["ReviewRound"][] = []) {
  server.use(
    http.get("/claims/{claim_id}/review", ({ response }) =>
      response(200).json({ claim_id: CLAIM_ID, rounds }),
    ),
  );
}

type ProposalRead = components["schemas"]["ProposalRead"];
type ReviewRound = components["schemas"]["ReviewRound"];

export function makeProposal(changes: Partial<ProposalRead> = {}): ProposalRead {
  return {
    id: "66666666-6666-4666-8666-666666666666",
    decision: "approve",
    reasons: [
      {
        clause_id: "3.1",
        quote: "Client meals are reimbursable up to EUR 80 per person.",
        explanation: "Two attendees, EUR 120 in total, within the limit.",
      },
    ],
    missing_information: [],
    duplicate_of: null,
    ai_model: "eu.anthropic.test-review-model",
    retrieved_clauses: ["3.1"],
    created_at: "2026-11-10T09:06:00Z",
    ...changes,
  };
}

export function makeRound(changes: Partial<ReviewRound> = {}): ReviewRound {
  const proposal = changes.proposal === undefined ? makeProposal() : changes.proposal;
  return { proposal_id: proposal?.id ?? "77777777-7777-4777-8777-777777777777", proposal, decision: null, answer: null, ...changes };
}

export function mockExtraction() {
  server.use(
    http.get("/claims/{claim_id}/extraction", ({ response }) =>
      response(200).json({
        document_type: "receipt",
        vendor_name: "Trattoria Roma",
        vendor_tax_id: null,
        document_number: "R-2041",
        document_date: "2026-11-09",
        document_time: "20:15:00",
        currency: "EUR",
        line_items: [
          { description: "Menu del giorno", quantity: "2", unit_price: "45.0000", amount: "90.00" },
        ],
        subtotal: "90.00",
        tax_amount: "9.00",
        tip_amount: null,
        total: "120.00",
        category: "client_entertainment",
        warnings: [
          { code: "sum_mismatch", message: "Items, tax and tip add up to 99.00, the total is 120.00" },
        ],
        ai_model: "eu.anthropic.test-model",
        created_at: "2026-11-10T09:02:00Z",
      }),
    ),
  );
}
