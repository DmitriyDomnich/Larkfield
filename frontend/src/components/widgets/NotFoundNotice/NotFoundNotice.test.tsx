import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NotFoundNotice } from "./NotFoundNotice";

describe("NotFoundNotice", () => {
  it("says the page does not exist and links to the start page", () => {
    render(<NotFoundNotice />);

    expect(screen.getByText("Page not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to your start page" })).toHaveAttribute("href", "/");
  });
});
