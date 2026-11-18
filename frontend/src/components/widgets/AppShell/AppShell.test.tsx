import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { signOut } from "aws-amplify/auth";
import { describe, expect, it, vi } from "vitest";

import { mockMe } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";

import { AppShell } from "./AppShell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/claims",
  useRouter: () => ({ replace: vi.fn() }),
}));

async function getNavLinks() {
  const nav = screen.getByRole("navigation", { name: "Main" });
  await screen.findByText(/@example\.com/);
  return within(nav)
    .queryAllByRole("link")
    .map((link) => link.textContent);
}

describe("AppShell", () => {
  it.each([
    ["employee", ["Claims", "New claim"]],
    ["reviewer", ["Claims", "New claim", "Review queue"]],
    ["admin", []],
  ] as const)("shows an %s the links %j", async (role, links) => {
    mockMe(role);

    renderWithClient(<AppShell>page</AppShell>);

    expect(await getNavLinks()).toEqual(links);
  });

  it("marks the current page and signs out", async () => {
    mockMe("employee");

    renderWithClient(<AppShell>page</AppShell>);
    await getNavLinks();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(screen.getByRole("link", { name: "Claims" })).toHaveAttribute("aria-current", "page");
    expect(signOut).toHaveBeenCalledOnce();
  });
});
