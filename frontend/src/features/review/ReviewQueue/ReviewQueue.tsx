"use client";

import Link from "next/link";
import { useMemo } from "react";

import type { ClaimRead } from "@/api/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LinkRow } from "@/components/widgets/LinkRow/LinkRow";
import { Pager } from "@/components/widgets/Pager/Pager";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { StatusBadge } from "@/components/widgets/StatusBadge/StatusBadge";
import { formatDateTime } from "@/lib/format";

import { QueueFilters } from "../QueueFilters/QueueFilters";
import { useQueueClaims } from "../hooks/useQueueClaims";
import {
  QUEUE_PAGE_SIZE,
  isDefaultStatuses,
  toClaimsQuery,
  useQueueFilters,
} from "../hooks/useQueueFilters";
import { useUsers } from "../hooks/useUsers";

const NOTHING_WAITING = "No claims are waiting for review.";
const NOTHING_MATCHES = "No claims match these filters.";
const UNKNOWN_USER = "Unknown user";

export function ReviewQueue() {
  const { filters, changeFilters, changePage } = useQueueFilters();
  const query = useMemo(() => toClaimsQuery(filters), [filters]);
  const claims = useQueueClaims(query);
  const users = useUsers();
  const emails = useMemo(
    () => new Map(users.data?.map((user) => [user.sub, user.email])),
    [users.data],
  );
  const isTodaysQueue =
    isDefaultStatuses(filters.statuses) && !filters.from && !filters.to && !filters.employee;

  const employeeOf = (claim: ClaimRead) =>
    users.isPending ? "…" : (emails.get(claim.employee_sub) ?? UNKNOWN_USER);

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Review queue</h1>
      <QueueFilters filters={filters} users={users.data} onChange={changeFilters} />
      <QueryState query={claims}>
        {(page) =>
          page.items.length === 0 ? (
            <p className="text-muted-foreground">{isTodaysQueue ? NOTHING_WAITING : NOTHING_MATCHES}</p>
          ) : (
            <>
              <QueueTable claims={page.items} employeeOf={employeeOf} />
              <Pager
                offset={page.offset}
                limit={QUEUE_PAGE_SIZE}
                total={page.total}
                onOffsetChange={(offset) => changePage(offset / QUEUE_PAGE_SIZE + 1)}
              />
            </>
          )
        }
      </QueryState>
    </section>
  );
}

type QueueTableProps = { claims: ClaimRead[]; employeeOf: (claim: ClaimRead) => string };

function QueueTable({ claims, employeeOf }: QueueTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Submitted</TableHead>
          <TableHead>Employee</TableHead>
          <TableHead>Purpose</TableHead>
          <TableHead>Document</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {claims.map((claim) => (
          <LinkRow key={claim.id} href={`/review/claim?id=${claim.id}`}>
            <TableCell className="whitespace-nowrap">{formatDateTime(claim.submitted_at)}</TableCell>
            <TableCell className="max-w-48 truncate">{employeeOf(claim)}</TableCell>
            <TableCell className="max-w-md truncate">
              <Link href={`/review/claim?id=${claim.id}`} className="underline-offset-4 hover:underline">
                {claim.purpose}
              </Link>
            </TableCell>
            <TableCell className="max-w-48 truncate">{claim.document?.original_filename}</TableCell>
            <TableCell>
              <StatusBadge status={claim.status} />
            </TableCell>
          </LinkRow>
        ))}
      </TableBody>
    </Table>
  );
}
