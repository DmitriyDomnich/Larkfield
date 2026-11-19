import type { ClaimStatus } from "@/api/types";

export const claimQueryKeys = {
  list: (statuses: readonly ClaimStatus[], offset: number) => ["claims", "list", statuses, offset],
  claim: (claimId: string) => ["claims", claimId],
  fileLink: (claimId: string) => ["claims", claimId, "file"],
  review: (claimId: string, status: ClaimStatus) => ["claims", claimId, "review", status],
};
