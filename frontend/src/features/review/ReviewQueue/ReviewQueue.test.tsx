import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { GENERIC_ERROR } from "@/api/errors";
import { makeClaim } from "@/test/fixtures";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { ReviewQueue } from "./ReviewQueue";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));

describe("ReviewQueue", () => {
  it("lists the claims in review, each linking to its review page", async () => {
    const claim = makeClaim();
    const statuses: string[][] = [];
    server.use(
      http.get("/claims", ({ request, response }) => {
        statuses.push(new URL(request.url).searchParams.getAll("status"));
        return response(200).json({ items: [claim], total: 1, limit: 20, offset: 0 });
      }),
    );

    renderWithClient(<ReviewQueue />);

    expect(await screen.findByRole("link", { name: claim.purpose })).toHaveAttribute(
      "href",
      `/review/claim?id=${claim.id}`,
    );
    expect(statuses).toEqual([["in_review"]]);

    await userEvent.click(screen.getByText("receipt.pdf"));
    expect(navigation.push).toHaveBeenCalledWith(`/review/claim?id=${claim.id}`);
  });

  it("says when nothing is waiting", async () => {
    server.use(
      http.get("/claims", ({ response }) => response(200).json({ items: [], total: 0, limit: 20, offset: 0 })),
    );

    renderWithClient(<ReviewQueue />);

    expect(await screen.findByText("No claims are waiting for review.")).toBeInTheDocument();
  });

  it("shows a spinner while loading, and an error when the queue fails", async () => {
    server.use(http.get("/claims", ({ response }) => response.untyped(HttpResponse.text("", { status: 500 }))));

    renderWithClient(<ReviewQueue />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
  });
});
