import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Table, TableBody, TableCell } from "@/components/ui/table";

import { LinkRow } from "./LinkRow";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));

function renderRow() {
  render(
    <Table>
      <TableBody>
        <LinkRow href="/claims/view?id=1">
          <TableCell>
            <a href="/claims/view?id=1">Dinner</a>
          </TableCell>
          <TableCell>In review</TableCell>
        </LinkRow>
      </TableBody>
    </Table>,
  );
}

describe("LinkRow", () => {
  it("opens the link when any cell is clicked", async () => {
    renderRow();

    await userEvent.click(screen.getByText("In review"));

    expect(navigation.push).toHaveBeenCalledWith("/claims/view?id=1");
  });

  it("leaves a click on the link itself to the link", async () => {
    renderRow();

    await userEvent.click(screen.getByRole("link", { name: "Dinner" }));

    expect(navigation.push).not.toHaveBeenCalled();
  });
});
