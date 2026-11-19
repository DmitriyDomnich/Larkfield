"use client";

import Link from "next/link";
import { useState } from "react";

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
import { CLAIMS_PAGE_SIZE, useClaims } from "@/features/claims/hooks/useClaims";
import { formatDateTime } from "@/lib/format";

const IN_REVIEW = ["in_review"] as const;

export function ReviewQueue() {
  const [offset, setOffset] = useState(0);
  const claims = useClaims(offset, IN_REVIEW);

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Review queue</h1>
      <QueryState query={claims}>
        {(page) =>
          page.items.length === 0 ? (
            <p className="text-muted-foreground">No claims are waiting for review.</p>
          ) : (
            <>
              <QueueTable claims={page.items} />
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

function QueueTable({ claims }: { claims: ClaimRead[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Submitted</TableHead>
          <TableHead>Purpose</TableHead>
          <TableHead>Document</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {claims.map((claim) => (
          <LinkRow key={claim.id} href={`/review/claim?id=${claim.id}`}>
            <TableCell className="whitespace-nowrap">{formatDateTime(claim.submitted_at)}</TableCell>
            <TableCell className="max-w-md truncate">
              <Link href={`/review/claim?id=${claim.id}`} className="underline-offset-4 hover:underline">
                {claim.purpose}
              </Link>
            </TableCell>
            <TableCell className="max-w-48 truncate">{claim.document?.original_filename}</TableCell>
          </LinkRow>
        ))}
      </TableBody>
    </Table>
  );
}
