import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { signOut } from "aws-amplify/auth";
import { describe, expect, it, vi } from "vitest";

import { mockMe } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";

import { HomeRedirect } from "./HomeRedirect";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

describe("HomeRedirect", () => {
  it.each([
    ["employee", "/claims"],
    ["reviewer", "/review"],
  ] as const)("sends an %s to %s", async (role, path) => {
    mockMe(role);

    renderWithClient(<HomeRedirect />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith(path));
  });

  it("shows admins a notice with sign-out instead", async () => {
    mockMe("admin");

    renderWithClient(<HomeRedirect />);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(screen.getByText("Administrator pages are coming soon")).toBeInTheDocument();
    expect(signOut).toHaveBeenCalledOnce();
    expect(replace).not.toHaveBeenCalled();
  });
});
