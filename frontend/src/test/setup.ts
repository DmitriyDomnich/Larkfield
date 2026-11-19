import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { TEST_ACCESS_TOKEN } from "./env";
import { server } from "./server";

// Signed in by default; a test signs out with vi.mocked(getCurrentUser).mockRejectedValue(...)
vi.mock("aws-amplify/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("aws-amplify/auth")>()),
  fetchAuthSession: vi.fn(async () => ({
    tokens: { accessToken: { toString: () => TEST_ACCESS_TOKEN } },
  })),
  getCurrentUser: vi.fn(async () => ({ username: "user-1", userId: "user-1" })),
  signOut: vi.fn(async () => undefined),
}));

// jsdom has no ResizeObserver; Radix (radio group) measures elements with it
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  vi.resetAllMocks();
});
afterAll(() => server.close());
