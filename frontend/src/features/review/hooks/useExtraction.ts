import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import { claimQueryKeys } from "@/features/claims/hooks/claimQueryKeys";

export function useExtraction(claimId: string) {
  return useQuery({
    queryKey: claimQueryKeys.extraction(claimId),
    queryFn: () =>
      unwrap(api.GET("/claims/{claim_id}/extraction", { params: { path: { claim_id: claimId } } })),
  });
}
