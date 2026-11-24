import { useMemo, useSyncExternalStore } from "react";
import { vi } from "vitest";

/**
 * next/navigation with a URL that router.replace/push really change, so a page re-renders as in the
 * app. In a test file: vi.mock("next/navigation", () => import("@/test/navigation"));
 */
let currentUrl = new URL("http://test/");
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Where the test opens the page, e.g. setUrl("/review?status=all") */
export function setUrl(path: string) {
  currentUrl = new URL(path, "http://test/");
  listeners.forEach((listener) => listener());
}

export function currentPath() {
  return `${currentUrl.pathname}${currentUrl.search}`;
}

export const router = { push: vi.fn(), replace: vi.fn() };

export function useRouter() {
  return {
    push: (path: string) => {
      router.push(path);
      setUrl(path);
    },
    replace: (path: string, options?: object) => {
      router.replace(path, options);
      setUrl(path);
    },
  };
}

export function useSearchParams() {
  const search = useSyncExternalStore(subscribe, () => currentUrl.search);
  return useMemo(() => new URLSearchParams(search), [search]);
}

export function usePathname() {
  return useSyncExternalStore(subscribe, () => currentUrl.pathname);
}
