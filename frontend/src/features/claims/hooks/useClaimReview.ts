import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { ClaimStatus } from "@/api/types";

import { claimQueryKeys } from "./claimQueryKeys";

export function useClaimReview(claimId: string, status: ClaimStatus) {
  return useQuery({
    queryKey: claimQueryKeys.review(claimId, status),
    queryFn: () =>
      unwrap(api.GET("/claims/{claim_id}/review", { params: { path: { claim_id: claimId } } })),
  });
}
