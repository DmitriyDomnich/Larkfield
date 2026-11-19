import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./errors";

const MAX_RETRIES = 2;

// retry for 5xx status codes
function shouldRetry(failureCount: number, error: Error): boolean {
  const refused = error instanceof ApiError && error.status < 500;
  return !refused && failureCount < MAX_RETRIES;
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: shouldRetry } } });
}
