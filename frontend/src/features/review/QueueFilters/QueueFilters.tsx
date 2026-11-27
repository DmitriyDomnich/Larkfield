"use client";

import type { ClaimStatus, UserRead } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { STATUS_BADGES } from "@/components/widgets/StatusBadge/StatusBadge";

import {
  ALL_STATUSES,
  CLAIM_STATUSES,
  isTodaysQueue,
  type FilterChanges,
  type QueueFilters as Filters,
} from "../hooks/useQueueFilters";

const SEVERAL_STATUSES = "several";
const UNKNOWN_USER = "Unknown user";
const USERS_FAILED = "Couldn't load employees";

type QueueFiltersProps = {
  filters: Filters;
  users: UserRead[] | undefined;
  usersFailed?: boolean;
  onChange: (changes: FilterChanges) => void;
  onClear: () => void;
};

export function QueueFilters({ filters, users, usersFailed = false, onChange, onClear }: QueueFiltersProps) {
  const { statuses, employee } = filters;
  const statusValue =
    statuses === ALL_STATUSES ? ALL_STATUSES : statuses.length === 1 ? statuses[0] : SEVERAL_STATUSES;
  const employeeIsListed = !employee || users?.some((user) => user.sub === employee);
  const unlistedEmployeeLabel = usersFailed ? USERS_FAILED : users ? UNKNOWN_USER : "Loading…";

  function changeStatus(value: string) {
    onChange({ statuses: value === ALL_STATUSES ? ALL_STATUSES : [value as ClaimStatus] });
  }

  return (
    <div className="flex flex-wrap items-end gap-4" role="search" aria-label="Queue filters">
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-status">Status</Label>
        <NativeSelect
          id="filter-status"
          value={statusValue}
          onChange={(event) => changeStatus(event.target.value)}
        >
          {CLAIM_STATUSES.map((status) => (
            <NativeSelectOption key={status} value={status}>
              {STATUS_BADGES[status].label}
            </NativeSelectOption>
          ))}
          <NativeSelectOption value={ALL_STATUSES}>All statuses</NativeSelectOption>
          {statusValue === SEVERAL_STATUSES && (
            <NativeSelectOption value={SEVERAL_STATUSES} disabled>
              Several statuses
            </NativeSelectOption>
          )}
        </NativeSelect>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-from">From</Label>
        <Input
          id="filter-from"
          type="date"
          className="w-40"
          value={filters.from ?? ""}
          max={filters.to ?? undefined}
          onChange={(event) => onChange({ from: event.target.value || null })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-to">To</Label>
        <Input
          id="filter-to"
          type="date"
          className="w-40"
          value={filters.to ?? ""}
          min={filters.from ?? undefined}
          onChange={(event) => onChange({ to: event.target.value || null })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-employee">Employee</Label>
        <NativeSelect
          id="filter-employee"
          className="min-w-56"
          value={employee ?? ""}
          onChange={(event) => onChange({ employee: event.target.value || null })}
        >
          <NativeSelectOption value="">All employees</NativeSelectOption>
          {users?.map((user) => (
            <NativeSelectOption key={user.sub} value={user.sub}>
              {user.email}
            </NativeSelectOption>
          ))}
          {!employeeIsListed && (
            <NativeSelectOption value={employee}>{unlistedEmployeeLabel}</NativeSelectOption>
          )}
          {usersFailed && !employee && (
            <NativeSelectOption value={USERS_FAILED} disabled>
              {USERS_FAILED}
            </NativeSelectOption>
          )}
        </NativeSelect>
      </div>
      {!isTodaysQueue(filters) && (
        <Button variant="outline" onClick={onClear}>
          Clear filters
        </Button>
      )}
    </div>
  );
}
