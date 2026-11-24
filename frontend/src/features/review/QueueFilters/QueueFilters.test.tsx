import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { QueueFilters as Filters } from "../hooks/useQueueFilters";
import { QueueFilters } from "./QueueFilters";

const FILTERS: Filters = { statuses: ["in_review"], from: null, to: null, employee: null, page: 1 };
const USERS = [
  { sub: "sub-a", email: "a@example.com" },
  { sub: "sub-b", email: "b@example.com" },
];

function renderFilters(filters: Partial<Filters> = {}, users: typeof USERS | undefined = USERS) {
  const onChange = vi.fn();
  render(<QueueFilters filters={{ ...FILTERS, ...filters }} users={users} onChange={onChange} />);
  return onChange;
}

describe("QueueFilters", () => {
  it("shows the current filters", () => {
    renderFilters({ statuses: "all", from: "2026-11-01", to: "2026-11-03", employee: "sub-b" });

    expect(screen.getByLabelText("Status")).toHaveDisplayValue("All statuses");
    expect(screen.getByLabelText("From")).toHaveValue("2026-11-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-11-03");
    expect(screen.getByLabelText("Employee")).toHaveDisplayValue("b@example.com");
  });

  it("changes the status to one status or all", async () => {
    const onChange = renderFilters();

    await userEvent.selectOptions(screen.getByLabelText("Status"), "Waiting for upload");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "All statuses");

    expect(onChange.mock.calls).toEqual([[{ statuses: ["pending_upload"] }], [{ statuses: "all" }]]);
  });

  it("changes the dates and clears one", async () => {
    const onChange = renderFilters({ to: "2026-11-03" });

    await userEvent.type(screen.getByLabelText("From"), "2026-11-01");
    await userEvent.clear(screen.getByLabelText("To"));

    expect(onChange).toHaveBeenCalledWith({ from: "2026-11-01" });
    expect(onChange).toHaveBeenLastCalledWith({ to: null });
  });

  it("picks an employee by email, or all employees", async () => {
    const onChange = renderFilters({ employee: "sub-a" });

    await userEvent.selectOptions(screen.getByLabelText("Employee"), "b@example.com");
    await userEvent.selectOptions(screen.getByLabelText("Employee"), "All employees");

    expect(onChange.mock.calls).toEqual([[{ employee: "sub-b" }], [{ employee: null }]]);
  });

  it("shows an employee who is not in the list as unknown", () => {
    renderFilters({ employee: "sub-gone" });

    expect(screen.getByLabelText("Employee")).toHaveDisplayValue("Unknown user");
  });

  it("shows several statuses from a link as such", () => {
    renderFilters({ statuses: ["approved", "rejected"] });

    expect(screen.getByLabelText("Status")).toHaveDisplayValue("Several statuses");
  });
});
