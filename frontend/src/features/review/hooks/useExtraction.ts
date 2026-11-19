import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";

export function useExtraction(claimId: string) {
  return useQuery({
    queryKey: ["claims", claimId, "extraction"],
    queryFn: () =>
      unwrap(api.GET("/claims/{claim_id}/extraction", { params: { path: { claim_id: claimId } } })),
  });
}
