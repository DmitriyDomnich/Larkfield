"use client";

import { useSearchParams } from "next/navigation";

import type { ClaimRead } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { BackLink } from "@/components/widgets/BackLink/BackLink";
import { NotFoundNotice } from "@/components/widgets/NotFoundNotice/NotFoundNotice";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { StatusBadge } from "@/components/widgets/StatusBadge/StatusBadge";
import { useMe } from "@/features/auth/hooks/useMe";
import { useClaim } from "@/features/claims/hooks/useClaim";
import { useClaimReview } from "@/features/claims/hooks/useClaimReview";
import { formatDateTime } from "@/lib/format";

import { DecisionForm } from "../DecisionForm/DecisionForm";
import { DocumentViewer } from "../DocumentViewer/DocumentViewer";
import { ExtractionPanel } from "../ExtractionPanel/ExtractionPanel";
import { ProposalPanel } from "../ProposalPanel/ProposalPanel";

export function ReviewClaim() {
  const claimId = useSearchParams().get("id");
  if (!claimId) return <NotFoundNotice />;
  return <ReviewPanels claimId={claimId} />;
}

function ReviewPanels({ claimId }: { claimId: string }) {
  const claim = useClaim(claimId);
  return (
    <div className="flex flex-col gap-4">
      <BackLink href="/review">Review queue</BackLink>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="lg:sticky lg:top-4 lg:self-start">
          {claim.data && <DocumentViewer claim={claim.data} />}
        </div>
        <div className="flex flex-col gap-6">
          <QueryState query={claim}>{(data) => <ClaimPanel claim={data} />}</QueryState>
          <ExtractionPanel claimId={claimId} />
          {claim.data && <ProposalPanel claim={claim.data} />}
          {claim.data && <DecisionSection claim={claim.data} />}
        </div>
      </div>
    </div>
  );
}

function ClaimPanel({ claim }: { claim: ClaimRead }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-lg font-semibold whitespace-pre-wrap">{claim.purpose}</h1>
        <StatusBadge status={claim.status} />
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Submitted</dt>
        <dd>{formatDateTime(claim.submitted_at)}</dd>
        <dt className="text-muted-foreground">Attendees</dt>
        <dd>
          {claim.attendees.length === 0
            ? "None"
            : claim.attendees.map(({ name, company }) => `${name} (${company})`).join(", ")}
        </dd>
        <dt className="text-muted-foreground">Pre-approval</dt>
        <dd>{claim.preapproval_ref ?? "None"}</dd>
      </dl>
    </section>
  );
}

function DecisionSection({ claim }: { claim: ClaimRead }) {
  const me = useMe();
  const review = useClaimReview(claim.id, claim.status);

  if (claim.status !== "in_review") return null;
  if (me.data?.sub === claim.employee_sub) {
    return (
      <Alert>
        <AlertDescription>This is your own claim. Another reviewer decides it.</AlertDescription>
      </Alert>
    );
  }
  return (
    <QueryState query={review}>
      {({ rounds }) => (
        <DecisionForm claimId={claim.id} proposedDecision={rounds[0]?.proposal?.decision ?? null} />
      )}
    </QueryState>
  );
}
