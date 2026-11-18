import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { TEST_ACCESS_TOKEN } from "./env";
import { server } from "./server";

vi.mock("aws-amplify/auth", () => ({
  fetchAuthSession: vi.fn(async () => ({
    tokens: { accessToken: { toString: () => TEST_ACCESS_TOKEN } },
  })),
  signOut: vi.fn(async () => undefined),
}));

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  vi.clearAllMocks();
});
afterAll(() => server.close());
