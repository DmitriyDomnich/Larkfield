import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";

export const ME_QUERY_KEY = ["me"];
const ME_STALE_TIME_MS = 15 * 60 * 1000;

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => unwrap(api.GET("/me")),
    staleTime: ME_STALE_TIME_MS,
  });
}
