"use client";

import { Loader2Icon } from "lucide-react";
import { useSearchParams } from "next/navigation";

import type { ClaimRead } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BackLink } from "@/components/widgets/BackLink/BackLink";
import { NotFoundNotice } from "@/components/widgets/NotFoundNotice/NotFoundNotice";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { StatusBadge } from "@/components/widgets/StatusBadge/StatusBadge";
import { formatDateTime } from "@/lib/format";

import { AnswerForm } from "../AnswerForm/AnswerForm";
import { ClaimFileLink } from "../ClaimFileLink/ClaimFileLink";
import { isProcessing, useClaim } from "../hooks/useClaim";
import { ReviewerComments } from "../ReviewerComments/ReviewerComments";


export function ClaimDetail() {
  const claimId = useSearchParams().get("id");
  if (!claimId) return <NotFoundNotice />;
  return <ClaimDetailQuery claimId={claimId} />;
}

function ClaimDetailQuery({ claimId }: { claimId: string }) {
  const claim = useClaim(claimId);
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <BackLink href="/claims">Claims</BackLink>
      <QueryState query={claim}>{(data) => <ClaimSummary claim={data} />}</QueryState>
    </div>
  );
}

function ClaimSummary({ claim }: { claim: ClaimRead }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <CardTitle className="whitespace-pre-wrap">{claim.purpose}</CardTitle>
          <StatusBadge status={claim.status} />
        </div>
        <CardDescription>Submitted {formatDateTime(claim.submitted_at)}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {isProcessing(claim.status) && (
          <p role="status" className="text-muted-foreground flex items-center gap-2 text-sm">
            <Loader2Icon className="size-4 animate-spin" aria-hidden />
            Your document is being processed
          </p>
        )}
        {claim.failure_reason && (
          <Alert variant="destructive">
            <AlertTitle>The claim could not be processed</AlertTitle>
            <AlertDescription>{claim.failure_reason}</AlertDescription>
          </Alert>
        )}
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Document</dt>
          <dd>
            <ClaimFileLink claim={claim} />
          </dd>
          <dt className="text-muted-foreground">Attendees</dt>
          <dd>
            {claim.attendees.length === 0
              ? "—"
              : claim.attendees.map(({ name, company }) => `${name} (${company})`).join(", ")}
          </dd>
          <dt className="text-muted-foreground">Pre-approval</dt>
          <dd>{claim.preapproval_ref ?? "—"}</dd>
        </dl>
        <ReviewerComments claim={claim}>
          <AnswerForm claim={claim} />
        </ReviewerComments>
      </CardContent>
    </Card>
  );
}
