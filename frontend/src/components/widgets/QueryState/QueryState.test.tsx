import { useQuery } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { api } from "@/api/client";
import { GENERIC_ERROR, unwrap } from "@/api/errors";
import { renderWithClient } from "@/test/render";
import { http, server } from "@/test/server";

import { QueryState } from "./QueryState";

const ME = { sub: "user-1", email: "user@example.com", role: "employee" } as const;

function Me() {
  const query = useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/me")) });
  return <QueryState query={query}>{(me) => <p>Signed in as {me.email}</p>}</QueryState>;
}

describe("QueryState", () => {
  it("shows a spinner while loading, then the data", async () => {
    server.use(http.get("/me", ({ response }) => response(200).json(ME)));

    renderWithClient(<Me />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByText("Signed in as user@example.com")).toBeInTheDocument();
  });

  it("shows the API's detail for a 4xx", async () => {
    server.use(http.get("/me", ({ response }) => response.untyped(HttpResponse.json({ detail: "No role assigned" }, { status: 403 }))));

    renderWithClient(<Me />);

    expect(await screen.findByText("No role assigned")).toBeInTheDocument();
  });

  it("shows a generic message for a 5xx, never the server's text", async () => {
    server.use(
      http.get("/me", ({ response }) => response.untyped(HttpResponse.text("Traceback …", { status: 500 }))),
    );

    renderWithClient(<Me />);

    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
  });

  it("shows a generic message for a network failure", async () => {
    server.use(http.get("/me", ({ response }) => response.untyped(HttpResponse.error())));

    renderWithClient(<Me />);

    expect(await screen.findByText(GENERIC_ERROR)).toBeInTheDocument();
  });

  it("refetches on Try again", async () => {
    let calls = 0;
    server.use(
      http.get("/me", ({ response }) => {
        calls += 1;
        return calls === 1
          ? response.untyped(HttpResponse.text("", { status: 500 }))
          : response(200).json(ME);
      }),
    );

    renderWithClient(<Me />);
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Signed in as user@example.com")).toBeInTheDocument();
  });
});
