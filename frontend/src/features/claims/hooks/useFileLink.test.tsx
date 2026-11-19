import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CLAIM_ID } from "@/test/fixtures";
import { http, server } from "@/test/server";

import { useFileLink } from "./useFileLink";

const LINK_LIFETIME_MS = 5 * 60 * 1000;

afterEach(() => vi.useRealTimers());

function mockLinks() {
  const fetches = { count: 0 };
  server.use(
    http.get("/claims/{claim_id}/file", ({ response }) => {
      fetches.count += 1;
      return response(200).json({
        url: `https://documents.test/receipt.pdf?signature=${fetches.count}`,
        expires_at: new Date(Date.now() + LINK_LIFETIME_MS).toISOString(),
      });
    }),
  );
  return fetches;
}

function renderLink(refetchOnWindowFocus: boolean) {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useFileLink(CLAIM_ID, true, { refetchOnWindowFocus }), { wrapper });
}

describe("useFileLink", () => {
  it("never swaps the link of an open document", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetches = mockLinks();
    const { result } = renderLink(false);
    await waitFor(() => expect(result.current.data).toBeDefined());

    await act(() => vi.advanceTimersByTimeAsync(2 * LINK_LIFETIME_MS));

    expect(fetches.count).toBe(1);
  });

  it("fetches a new link for an anchor before the old one expires", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetches = mockLinks();
    const { result } = renderLink(true);
    await waitFor(() => expect(result.current.data).toBeDefined());

    await act(() => vi.advanceTimersByTimeAsync(LINK_LIFETIME_MS - 20_000));

    await waitFor(() => expect(fetches.count).toBe(2));
    expect(result.current.data?.url).toContain("signature=2");
  });
});
