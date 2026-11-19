"use client";

import Link from "next/link";
import { useState } from "react";

import type { ClaimRead } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Pager } from "@/components/widgets/Pager/Pager";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { StatusBadge } from "@/components/widgets/StatusBadge/StatusBadge";
import { formatDateTime } from "@/lib/format";

import { CLAIMS_PAGE_SIZE, useClaims } from "../hooks/useClaims";

export function ClaimList() {
  const [offset, setOffset] = useState(0);
  const claims = useClaims(offset);

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Claims</h1>
        <Button asChild>
          <Link href="/claims/new">New claim</Link>
        </Button>
      </div>
      <QueryState query={claims}>
        {(page) =>
          page.items.length === 0 ? (
            <p className="text-muted-foreground">No claims yet.</p>
          ) : (
            <>
              <ClaimTable claims={page.items} />
              <Pager
                offset={page.offset}
                limit={CLAIMS_PAGE_SIZE}
                total={page.total}
                onOffsetChange={setOffset}
              />
            </>
          )
        }
      </QueryState>
    </section>
  );
}

function ClaimTable({ claims }: { claims: ClaimRead[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Submitted</TableHead>
          <TableHead>Purpose</TableHead>
          <TableHead>Document</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {claims.map((claim) => (
          <TableRow key={claim.id}>
            <TableCell className="whitespace-nowrap">{formatDateTime(claim.submitted_at)}</TableCell>
            <TableCell className="max-w-sm truncate">
              <Link href={`/claims/view?id=${claim.id}`} className="underline-offset-4 hover:underline">
                {claim.purpose}
              </Link>
            </TableCell>
            <TableCell className="max-w-48 truncate">{claim.document?.original_filename}</TableCell>
            <TableCell className="flex flex-col items-start gap-1 whitespace-normal">
              <StatusBadge status={claim.status} />
              {claim.failure_reason && (
                <span className="text-muted-foreground text-xs">{claim.failure_reason}</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
