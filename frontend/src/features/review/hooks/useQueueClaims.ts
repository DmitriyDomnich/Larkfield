import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import { claimQueryKeys } from "@/features/claims/hooks/claimQueryKeys";

import type { ClaimsQuery } from "./useQueueFilters";

export function useQueueClaims(query: ClaimsQuery) {
  return useQuery({
    queryKey: claimQueryKeys.queue(query),
    queryFn: () => unwrap(api.GET("/claims", { params: { query } })),
    placeholderData: keepPreviousData,
  });
}
