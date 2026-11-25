"use client";

import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import type { ClaimRead, ClaimStatus, Decision, ReviewRound } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { BackLink } from "@/components/widgets/BackLink/BackLink";
import { NotFoundNotice } from "@/components/widgets/NotFoundNotice/NotFoundNotice";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { StatusBadge } from "@/components/widgets/StatusBadge/StatusBadge";
import { useMe } from "@/features/auth/hooks/useMe";
import { useClaim } from "@/features/claims/hooks/useClaim";
import { useClaimReview } from "@/features/claims/hooks/useClaimReview";
import { formatDateTime } from "@/lib/format";

import { fieldValuesOf } from "../corrections";
import { DecisionForm } from "../DecisionForm/DecisionForm";
import { DocumentViewer } from "../DocumentViewer/DocumentViewer";
import { ExtractionPanel } from "../ExtractionPanel/ExtractionPanel";
import { useCorrections } from "../hooks/useCorrections";
import { useExtraction } from "../hooks/useExtraction";
import { useQueuePath } from "../queueReturnPath";
import { ProposalPanel } from "../ProposalPanel/ProposalPanel";

export function ReviewClaim() {
  const claimId = useSearchParams().get("id");
  if (!claimId) return <NotFoundNotice />;
  return <ReviewPanels claimId={claimId} />;
}

function ReviewPanels({ claimId }: { claimId: string }) {
  const claim = useClaim(claimId);
  const queuePath = useQueuePath();
  return (
    <div className="flex flex-col gap-4">
      <BackLink href={queuePath}>Review queue</BackLink>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="lg:sticky lg:top-4 lg:self-start">
          {claim.data && <DocumentViewer claim={claim.data} />}
        </div>
        <div className="flex flex-col gap-6">
          <QueryState query={claim}>{(data) => <ClaimPanel claim={data} />}</QueryState>
          {claim.data && <ReviewWork key={claim.data.id} claim={claim.data} />}
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
            ? "—"
            : claim.attendees.map(({ name, company }) => `${name} (${company})`).join(", ")}
        </dd>
        <dt className="text-muted-foreground">Pre-approval</dt>
        <dd>{claim.preapproval_ref ?? "—"}</dd>
      </dl>
    </section>
  );
}

const DECIDED_STATUSES: readonly ClaimStatus[] = ["approved", "rejected", "needs_info"];

function isDecidable(claim: ClaimRead, rounds: ReviewRound[] | undefined, mySub: string | undefined) {
  const newest = rounds?.[0];
  return (
    claim.status === "in_review" &&
    mySub !== undefined &&
    mySub !== claim.employee_sub &&
    Boolean(newest?.proposal) &&
    !newest?.decision
  );
}

function ReviewWork({ claim }: { claim: ClaimRead }) {
  const me = useMe();
  const extraction = useExtraction(claim.id);
  const review = useClaimReview(claim.id, claim.status);
  const rounds = review.data?.rounds;
  const editable = isDecidable(claim, rounds, me.data?.sub);
  const corrections = useCorrections({ extraction: extraction.data, rounds, editable });

  return (
    <>
      <QueryState query={extraction}>
        {(data) => (
          <ExtractionPanel
            extraction={data}
            correctedValues={corrections.values ?? fieldValuesOf(data)}
            problems={corrections.problems}
            editing={corrections.editing}
            canEdit={editable}
            onEditingChange={corrections.setEditing}
            onChange={corrections.changeField}
          />
        )}
      </QueryState>
      <ProposalPanel claim={claim} correctedSinceProposal={corrections.correctedSinceProposal} />
      <DecisionSection
        claim={claim}
        isOwnClaim={me.data?.sub === claim.employee_sub}
        reviewQuery={review}
      >
        {(proposedDecision) => (
          <DecisionForm
            key={corrections.proposalId}
            claimId={claim.id}
            proposedDecision={proposedDecision}
            correctedFields={corrections.correctedFields}
            correctionsInvalid={corrections.isInvalid}
          />
        )}
      </DecisionSection>
    </>
  );
}

type DecisionSectionProps = {
  claim: ClaimRead;
  isOwnClaim: boolean;
  reviewQuery: ReturnType<typeof useClaimReview>;
  children: (proposedDecision: Decision | null) => ReactNode;
};

function DecisionSection({ claim, isOwnClaim, reviewQuery, children }: DecisionSectionProps) {
  if (DECIDED_STATUSES.includes(claim.status)) {
    return (
      <Alert>
        <AlertDescription className="flex items-center gap-2">
          This claim has already been decided: <StatusBadge status={claim.status} />
        </AlertDescription>
      </Alert>
    );
  }
  if (claim.status !== "in_review") return null;
  if (isOwnClaim) {
    return (
      <Alert>
        <AlertDescription>This is your own claim. Another reviewer decides it.</AlertDescription>
      </Alert>
    );
  }
  return (
    <QueryState query={reviewQuery}>
      {({ rounds }) => children(rounds[0]?.proposal?.decision ?? null)}
    </QueryState>
  );
}
