import { act, screen } from "@testing-library/react";
import { getCurrentUser } from "aws-amplify/auth";
import { Hub } from "aws-amplify/utils";
import { describe, expect, it, vi } from "vitest";

import { renderWithClient } from "@/test/render";

import { AuthGate } from "./AuthGate";

// Amplify only accepts events on its protected "auth" channel with this symbol
const AMPLIFY_SYMBOL = Symbol.for("amplify_default");

function renderGate() {
  return renderWithClient(
    <AuthGate>
      <p>The app</p>
    </AuthGate>,
  );
}

describe("AuthGate", () => {
  it("shows Amplify's sign-in form when signed out", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new Error("UserUnAuthenticatedException"));

    renderGate();

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText("The app")).not.toBeInTheDocument();
  });

  it("shows the app when signed in", async () => {
    renderGate();

    expect(await screen.findByText("The app")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });
});

describe("AuthGate on sign-out", () => {
  it("drops the previous user's cached data", async () => {
    const { queryClient } = renderGate();
    await screen.findByText("The app");
    queryClient.setQueryData(["me"], { sub: "user-1", email: "user@example.com", role: "reviewer" });

    act(() => Hub.dispatch("auth", { event: "signedOut" }, "Auth", AMPLIFY_SYMBOL));

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(queryClient.getQueryData(["me"])).toBeUndefined();
  });
});
