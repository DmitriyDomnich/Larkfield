import { signOut } from "aws-amplify/auth";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { TEST_ACCESS_TOKEN } from "@/test/env";
import { http, server } from "@/test/server";

import { api } from "./client";
import { ApiError, GENERIC_ERROR, getErrorMessage, unwrap } from "./errors";

const ME = { sub: "user-1", email: "user@example.com", role: "employee" } as const;

describe("api client", () => {
  it("sends the access token as a Bearer header", async () => {
    let authorization: string | null = null;
    server.use(
      http.get("/me", ({ request, response }) => {
        authorization = request.headers.get("Authorization");
        return response(200).json(ME);
      }),
    );

    await expect(unwrap(api.GET("/me"))).resolves.toEqual(ME);
    expect(authorization).toBe(`Bearer ${TEST_ACCESS_TOKEN}`);
  });

  it("signs out on a 401", async () => {
    server.use(http.get("/me", ({ response }) => response.untyped(HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }))));

    await expect(unwrap(api.GET("/me"))).rejects.toBeInstanceOf(ApiError);
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("keeps the session on other errors", async () => {
    server.use(http.get("/me", ({ response }) => response.untyped(HttpResponse.json({ detail: "No role assigned" }, { status: 403 }))));

    await expect(unwrap(api.GET("/me"))).rejects.toMatchObject({
      status: 403,
      detail: "No role assigned",
    });
    expect(signOut).not.toHaveBeenCalled();
  });
});

describe("getErrorMessage", () => {
  it.each([
    [new ApiError(404, "Claim not found"), "Claim not found"],
    [new ApiError(422, undefined), GENERIC_ERROR],
    [new ApiError(500, "Internal error text"), GENERIC_ERROR],
    [new TypeError("Failed to fetch"), GENERIC_ERROR],
  ])("%o → %s", (error, message) => {
    expect(getErrorMessage(error)).toBe(message);
  });
});
