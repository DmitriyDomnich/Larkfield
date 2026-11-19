import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { ClaimStatus } from "@/api/types";

import { claimQueryKeys } from "./claimQueryKeys";

export const POLL_INTERVAL_MS = 3000;

const PROCESSING_STATUSES: readonly ClaimStatus[] = [
  "pending_upload",
  "uploaded",
  "extracting",
  "extracted",
];

export function isProcessing(status: ClaimStatus): boolean {
  return PROCESSING_STATUSES.includes(status);
}

export function useClaim(claimId: string) {
  return useQuery({
    queryKey: claimQueryKeys.claim(claimId),
    queryFn: () => unwrap(api.GET("/claims/{claim_id}", { params: { path: { claim_id: claimId } } })),
    refetchInterval: (query) =>
      query.state.data && isProcessing(query.state.data.status) ? POLL_INTERVAL_MS : false,
  });
}
