import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";
import type { FileLink } from "@/api/types";

import { claimQueryKeys } from "./claimQueryKeys";

const REFRESH_BEFORE_EXPIRY_MS = 30_000;
const MIN_REFRESH_MS = 1_000;

function getMsUntilRefresh(link: FileLink | undefined): number {
  if (!link) return 0;
  return Math.max(0, Date.parse(link.expires_at) - Date.now() - REFRESH_BEFORE_EXPIRY_MS);
}

export function useFileLink(
  claimId: string,
  fileVerified: boolean,
  { refetchOnWindowFocus = false } = {},
) {
  return useQuery({
    queryKey: claimQueryKeys.fileLink(claimId),
    queryFn: () =>
      unwrap(api.GET("/claims/{claim_id}/file", { params: { path: { claim_id: claimId } } })),
    enabled: fileVerified,
    staleTime: (query) => getMsUntilRefresh(query.state.data),
    refetchInterval: refetchOnWindowFocus
      ? (query) => Math.max(getMsUntilRefresh(query.state.data), MIN_REFRESH_MS)
      : false,
    refetchOnWindowFocus,
  });
}
