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
