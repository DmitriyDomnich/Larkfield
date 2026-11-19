import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { ClaimStatus } from "@/api/types";

import { claimQueryKeys } from "./claimQueryKeys";

export const CLAIMS_PAGE_SIZE = 20;

export function useClaims(offset: number, statuses: readonly ClaimStatus[] = []) {
  return useQuery({
    queryKey: claimQueryKeys.list(statuses, offset),
    queryFn: () =>
      unwrap(
        api.GET("/claims", {
          params: { query: { limit: CLAIMS_PAGE_SIZE, offset, status: [...statuses] } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
