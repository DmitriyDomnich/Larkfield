import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { ApiError, unwrap } from "@/api/errors";
import type { components } from "@/api/schema";
import { claimQueryKeys } from "@/features/claims/hooks/claimQueryKeys";

type DecisionCreate = components["schemas"]["DecisionCreate"];

export function useDecideClaim(claimId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DecisionCreate) =>
      unwrap(
        api.POST("/claims/{claim_id}/decision", { params: { path: { claim_id: claimId } }, body }),
      ),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: claimQueryKeys.claim(claimId) });
      }
    },
  });
}
