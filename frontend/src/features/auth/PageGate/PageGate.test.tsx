import { screen, waitFor } from "@testing-library/react";
import { HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import { mockMe } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { PageGate } from "./PageGate";
import type { Role } from "../pageAccess";

const navigation = vi.hoisted(() => ({ pathname: "/claims", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ replace: navigation.replace }),
}));

const CLAIMS_PAGES = ["/claims", "/claims/new", "/claims/view"];
const REVIEW_PAGES = ["/review", "/review/claim"];

const PAGE_ACCESS: [Role, string, boolean][] = [
  ...CLAIMS_PAGES.map((page): [Role, string, boolean] => ["employee", page, true]),
  ...REVIEW_PAGES.map((page): [Role, string, boolean] => ["employee", page, false]),
  ...[...CLAIMS_PAGES, ...REVIEW_PAGES].map((page): [Role, string, boolean] => ["reviewer", page, true]),
  ...[...CLAIMS_PAGES, ...REVIEW_PAGES].map((page): [Role, string, boolean] => ["admin", page, false]),
];

function renderPage(path: string) {
  navigation.pathname = path;
  renderWithClient(
    <PageGate>
      <p>The page</p>
    </PageGate>,
  );
}

describe("PageGate", () => {
  it.each(PAGE_ACCESS)("%s on %s → opens: %s", async (role, page, opens) => {
    mockMe(role);

    renderPage(page);

    if (opens) {
      expect(await screen.findByText("The page")).toBeInTheDocument();
      expect(navigation.replace).not.toHaveBeenCalled();
    } else {
      await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/"));
      expect(screen.queryByText("The page")).not.toBeInTheDocument();
    }
  });

  it.each(["/", "/no-such-page"])("opens %s to every role", async (page) => {
    mockMe("admin");

    renderPage(page);

    expect(await screen.findByText("The page")).toBeInTheDocument();
  });

  it("shows a spinner while the role loads", () => {
    mockMe("employee");

    renderPage("/claims");

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });

  it("shows an error when the role can't be loaded", async () => {
    server.use(
      http.get("/me", ({ response }) => response.untyped(HttpResponse.text("", { status: 500 }))),
    );

    renderPage("/claims");

    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
    expect(screen.queryByText("The page")).not.toBeInTheDocument();
  });
});
