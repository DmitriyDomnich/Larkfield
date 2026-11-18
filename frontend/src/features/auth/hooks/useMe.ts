import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap } from "@/api/errors";

export const ME_QUERY_KEY = ["me"];

export function useMe() {
  return useQuery({ queryKey: ME_QUERY_KEY, queryFn: () => unwrap(api.GET("/me")) });
}
