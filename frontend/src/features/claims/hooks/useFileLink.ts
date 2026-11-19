import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";

import { claimQueryKeys } from "./claimQueryKeys";

// The presigned link expires after 5 minutes; a cached one is replaced after 4.
const LINK_FRESH_MS = 4 * 60 * 1000;

export function useFileLink(claimId: string, fileVerified: boolean) {
  return useQuery({
    queryKey: claimQueryKeys.fileLink(claimId),
    queryFn: () =>
      unwrap(api.GET("/claims/{claim_id}/file", { params: { path: { claim_id: claimId } } })),
    enabled: fileVerified,
    staleTime: LINK_FRESH_MS,
    refetchInterval: LINK_FRESH_MS,
  });
}
