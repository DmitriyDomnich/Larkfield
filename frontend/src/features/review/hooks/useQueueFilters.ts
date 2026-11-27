"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";

import type { paths } from "@/api/schema";
import type { ClaimStatus } from "@/api/types";
import { STATUS_BADGES } from "@/components/widgets/StatusBadge/StatusBadge";
import { isCalendarDate } from "@/core/fieldFormats";

import { rememberQueuePath } from "../queueReturnPath";

export const QUEUE_PAGE_SIZE = 20;
export const ALL_STATUSES = "all";
export const DEFAULT_STATUSES: readonly ClaimStatus[] = ["in_review"];
export const CLAIM_STATUSES = Object.keys(STATUS_BADGES) as ClaimStatus[];
const MAX_EMPLOYEE_LENGTH = 128;

export type QueueFilters = {
  statuses: readonly ClaimStatus[] | typeof ALL_STATUSES;
  /** YYYY-MM-DD */
  from: string | null;
  to: string | null;
  employee: string | null;
  page: number;
};
export type FilterChanges = Partial<Omit<QueueFilters, "page">>;
export type ClaimsQuery = NonNullable<paths["/claims"]["get"]["parameters"]["query"]>;

function isClaimStatus(value: string): value is ClaimStatus {
  return (CLAIM_STATUSES as string[]).includes(value);
}

function parseDate(value: string | null): string | null {
  return value && isCalendarDate(value) ? value : null;
}

function parseStatuses(values: string[]): QueueFilters["statuses"] {
  if (values.includes(ALL_STATUSES)) return ALL_STATUSES;
  const statuses = [...new Set(values.filter(isClaimStatus))];
  return statuses.length > 0 ? statuses : DEFAULT_STATUSES;
}

export const TODAYS_QUEUE: QueueFilters = {
  statuses: DEFAULT_STATUSES,
  from: null,
  to: null,
  employee: null,
  page: 1,
};

export function isDefaultStatuses(statuses: QueueFilters["statuses"]): boolean {
  return statuses !== ALL_STATUSES && statuses.length === 1 && statuses[0] === DEFAULT_STATUSES[0];
}

export function isTodaysQueue(filters: QueueFilters): boolean {
  return isDefaultStatuses(filters.statuses) && !filters.from && !filters.to && !filters.employee;
}

export function parseQueueFilters(params: URLSearchParams): QueueFilters {
  let from = parseDate(params.get("from"));
  let to = parseDate(params.get("to"));
  if (from && to && from > to) {
    from = null;
    to = null;
  }
  const employee = params.get("employee");
  const page = Number(params.get("page") ?? 1);
  return {
    statuses: parseStatuses(params.getAll("status")),
    from,
    to,
    employee: employee && employee.length <= MAX_EMPLOYEE_LENGTH ? employee : null,
    page: Number.isSafeInteger(page) && page >= 1 ? page : 1,
  };
}

export function toSearchParams(filters: QueueFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.statuses === ALL_STATUSES) {
    params.append("status", ALL_STATUSES);
  } else if (!isDefaultStatuses(filters.statuses)) {
    filters.statuses.forEach((status) => params.append("status", status));
  }
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.employee) params.set("employee", filters.employee);
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

function localMidnight(isoDate: string, daysLater = 0): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day + daysLater).toISOString();
}

export function toClaimsQuery(filters: QueueFilters): ClaimsQuery {
  return {
    ...(filters.statuses !== ALL_STATUSES ? { status: [...filters.statuses] } : {}),
    ...(filters.from ? { submitted_after: localMidnight(filters.from) } : {}),
    ...(filters.to ? { submitted_before: localMidnight(filters.to, 1) } : {}),
    ...(filters.employee ? { employee_sub: filters.employee } : {}),
    limit: QUEUE_PAGE_SIZE,
    offset: (filters.page - 1) * QUEUE_PAGE_SIZE,
  };
}

export function applyFilterChanges(filters: QueueFilters, changes: FilterChanges): QueueFilters {
  const next = { ...filters, ...changes, page: 1 };
  if (next.from && next.to && next.from > next.to) {
    if ("from" in changes) next.to = null;
    else next.from = null;
  }
  return next;
}

export function useQueueFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filters = useMemo(
    () => parseQueueFilters(new URLSearchParams(searchParams.toString())),
    [searchParams],
  );
  useEffect(() => rememberQueuePath(toSearchParams(filters).toString()), [filters]);

  const replaceFilters = useCallback(
    (next: QueueFilters) => {
      const query = toSearchParams(next).toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [router, pathname],
  );
  const changeFilters = useCallback(
    (changes: FilterChanges) => replaceFilters(applyFilterChanges(filters, changes)),
    [filters, replaceFilters],
  );
  const changePage = useCallback(
    (page: number) => replaceFilters({ ...filters, page }),
    [filters, replaceFilters],
  );
  const clearFilters = useCallback(() => replaceFilters(TODAYS_QUEUE), [replaceFilters]);
  return { filters, changeFilters, changePage, clearFilters };
}
