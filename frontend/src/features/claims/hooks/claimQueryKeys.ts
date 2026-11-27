import type { ClaimStatus } from "@/api/types";

export const claimQueryKeys = {
  list: (statuses: readonly ClaimStatus[], offset: number) => ["claims", "list", statuses, offset],
  queue: (query: object) => ["claims", "queue", query],
  claim: (claimId: string) => ["claims", claimId],
  fileLink: (claimId: string) => ["claims", claimId, "file"],
  extraction: (claimId: string) => ["claims", claimId, "extraction"],
  review: (claimId: string, status: ClaimStatus) => ["claims", claimId, "review", status],
};
