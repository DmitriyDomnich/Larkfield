import { describe, expect, it } from "vitest";

import { TEST_ENV } from "@/test/env";

import { getContentSecurityPolicy } from "./csp";

function getDirective(policy: string, name: string): string[] {
  const found = policy.split("; ").find((entry) => entry.startsWith(`${name} `));
  return found?.split(" ").slice(1) ?? [];
}

describe("getContentSecurityPolicy", () => {
  const production = getContentSecurityPolicy(false);

  it("lets the page connect only to itself, the API, Cognito and the documents bucket", () => {
    expect(getDirective(production, "connect-src")).toEqual([
      "'self'",
      TEST_ENV.NEXT_PUBLIC_API_URL,
      "https://cognito-idp.eu-test-1.amazonaws.com",
      TEST_ENV.NEXT_PUBLIC_DOCUMENTS_ORIGIN,
    ]);
  });

  it("shows documents only from the bucket and loads no plugins", () => {
    expect(getDirective(production, "frame-src")).toEqual(["'self'", TEST_ENV.NEXT_PUBLIC_DOCUMENTS_ORIGIN]);
    expect(getDirective(production, "img-src")).toEqual(["'self'", TEST_ENV.NEXT_PUBLIC_DOCUMENTS_ORIGIN]);
    expect(getDirective(production, "object-src")).toEqual(["'none'"]);
  });

  it("allows eval only in development", () => {
    expect(getDirective(production, "script-src")).not.toContain("'unsafe-eval'");
    expect(getDirective(getContentSecurityPolicy(true), "script-src")).toContain("'unsafe-eval'");
  });
});
