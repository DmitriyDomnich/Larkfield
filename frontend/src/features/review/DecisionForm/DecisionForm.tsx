"use client";

import { useRouter } from "next/navigation";
import { useState, type SubmitEvent } from "react";

import { ApiError, getErrorMessage } from "@/api/errors";
import type { Decision } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { FormError } from "@/components/widgets/FormError/FormError";

import { DECISION_LABELS } from "../decisionLabels";
import { useDecideClaim } from "../hooks/useDecideClaim";

const DECISIONS: Decision[] = ["approve", "reject", "needs_info"];
// the employee never sees the agent's proposal, so these always need the reviewer's reason
const COMMENT_REQUIRED_DECISIONS: Decision[] = ["reject", "needs_info"];
const COMMENT_MISSING =
  "Add a comment for the employee: it is required to reject, to request information, or to differ from the proposal.";
const ALREADY_DECIDED = "This claim has already been decided. The page now shows its current state.";

type DecisionFormProps = { claimId: string; proposedDecision: Decision | null };

export function DecisionForm({ claimId, proposedDecision }: DecisionFormProps) {
  const router = useRouter();
  const decideClaim = useDecideClaim(claimId);
  const [decision, setDecision] = useState<Decision>(proposedDecision ?? "approve");
  const [comment, setComment] = useState("");
  const [commentProblem, setCommentProblem] = useState<string | null>(null);
  const commentRequired = decision !== proposedDecision || COMMENT_REQUIRED_DECISIONS.includes(decision);

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault();
    const problem = commentRequired && !comment.trim() ? COMMENT_MISSING : null;
    setCommentProblem(problem);
    if (problem) return;
    decideClaim.mutate(
      { decision, comment: comment.trim() || null },
      { onSuccess: () => router.push("/review") },
    );
  }

  const submitError =
    decideClaim.error instanceof ApiError && decideClaim.error.status === 409
      ? ALREADY_DECIDED
      : decideClaim.error && getErrorMessage(decideClaim.error);

  return (
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-lg border p-4">
      <h2 className="font-medium">Your decision</h2>
      <RadioGroup
        value={decision}
        onValueChange={(value) => setDecision(value as Decision)}
        aria-label="Decision"
      >
        {DECISIONS.map((option) => (
          <div key={option} className="flex items-center gap-2">
            <RadioGroupItem value={option} id={`decision-${option}`} />
            <Label htmlFor={`decision-${option}`}>
              {DECISION_LABELS[option]}
              {option === proposedDecision && (
                <span className="text-muted-foreground font-normal">(proposed)</span>
              )}
            </Label>
          </div>
        ))}
      </RadioGroup>
      <div className="flex flex-col gap-1">
        <Label htmlFor="decision-comment">
          Comment to the employee{commentRequired ? " (required)" : " (optional)"}
        </Label>
        <Textarea
          id="decision-comment"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
        <FormError message={commentProblem} />
      </div>
      <FormError message={submitError} />
      <Button type="submit" className="self-start" disabled={decideClaim.isPending}>
        {decideClaim.isPending ? "Saving…" : "Save decision"}
      </Button>
    </form>
  );
}
