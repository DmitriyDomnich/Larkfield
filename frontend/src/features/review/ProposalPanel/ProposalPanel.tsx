"use client";

import { ChevronDownIcon } from "lucide-react";
import Link from "next/link";

import type { ClaimRead, ProposalRead, ReviewRound } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { useClaimReview } from "@/features/claims/hooks/useClaimReview";
import { formatDateTime } from "@/lib/format";

import { DECISION_LABELS } from "../decisionLabels";

export function ProposalPanel({ claim }: { claim: ClaimRead }) {
  const review = useClaimReview(claim.id, claim.status);
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-medium">Proposal</h2>
      <QueryState query={review}>
        {({ rounds }) => {
          const [newest, ...earlier] = rounds;
          return (
            <>
              {newest?.proposal ? (
                <ProposalDetails proposal={newest.proposal} />
              ) : (
                <p className="text-muted-foreground text-sm">No proposal to show.</p>
              )}
              {earlier.length > 0 && <EarlierRounds rounds={earlier} />}
            </>
          );
        }}
      </QueryState>
    </section>
  );
}

function ProposalDetails({ proposal }: { proposal: ProposalRead }) {
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p>
        The agent proposes: <strong>{DECISION_LABELS[proposal.decision]}</strong>
      </p>
      <ol className="flex flex-col gap-3">
        {proposal.reasons.map((reason) => (
          <li key={`${reason.clause_id}-${reason.quote}`} className="flex flex-col gap-1">
            <span className="font-medium">Clause {reason.clause_id}</span>
            <blockquote className="border-l-2 pl-3 italic">{reason.quote}</blockquote>
            <p>{reason.explanation}</p>
          </li>
        ))}
      </ol>
      {proposal.missing_information.length > 0 && (
        <div>
          <p className="font-medium">Missing information</p>
          <ul className="list-disc pl-5">
            {proposal.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {proposal.duplicate_of && (
        <p>
          Possible duplicate of{" "}
          <Link href={`/review/claim?id=${proposal.duplicate_of}`} className="underline">
            this claim
          </Link>
        </p>
      )}
    </div>
  );
}

function EarlierRounds({ rounds }: { rounds: ReviewRound[] }) {
  return (
    <Collapsible>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="group self-start">
          Earlier rounds ({rounds.length})
          <ChevronDownIcon className="transition-transform group-data-[state=open]:rotate-180" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-3 pt-2">
        {rounds.map(({ proposal_id, proposal, decision, answer }) => (
          <div key={proposal_id} className="flex flex-col gap-2 rounded-lg border p-3 text-sm">
            {proposal && <ProposalDetails proposal={proposal} />}
            {decision && (
              <p>
                Reviewer: <strong>{DECISION_LABELS[decision.decision]}</strong> ·{" "}
                {formatDateTime(decision.created_at)}
                {decision.comment && <span className="block whitespace-pre-wrap">{decision.comment}</span>}
              </p>
            )}
            {answer && <p className="whitespace-pre-wrap">Employee answered: {answer.message}</p>}
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
