import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { components } from "@/api/schema";

import { claimQueryKeys } from "./claimQueryKeys";

type AnswerCreate = components["schemas"]["AnswerCreate"];

export function useAnswerClaim(claimId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AnswerCreate) =>
      unwrap(
        api.POST("/claims/{claim_id}/answer", { params: { path: { claim_id: claimId } }, body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: claimQueryKeys.claim(claimId) }),
  });
}
