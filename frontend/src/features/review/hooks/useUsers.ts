import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";

const USERS_STALE_TIME_MS = 5 * 60 * 1000;

export function useUsers() {
  return useQuery({
    queryKey: ["users"],
    queryFn: () => unwrap(api.GET("/users")),
    staleTime: USERS_STALE_TIME_MS,
  });
}
