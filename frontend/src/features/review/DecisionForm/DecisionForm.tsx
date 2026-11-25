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

import type { ExpenseCorrections } from "../corrections";
import { DECISION_LABELS } from "../decisionLabels";
import { getQueuePath } from "../queueReturnPath";
import { useDecideClaim } from "../hooks/useDecideClaim";

const DECISIONS: Decision[] = ["approve", "reject", "needs_info"];
// the employee never sees the agent's proposal, so these always need the reviewer's reason
const COMMENT_REQUIRED_DECISIONS: Decision[] = ["reject", "needs_info"];
const MAX_COMMENT_LENGTH = 2000;
const COMMENT_TOO_LONG = `Keep the comment to ${MAX_COMMENT_LENGTH} characters.`;
const COMMENT_MISSING =
  "Add a comment for the employee: it is required to reject, to request information, or to differ from the proposal.";
const ALREADY_DECIDED = "This claim has already been decided. The page now shows its current state.";
const FIX_CORRECTIONS = "Fix the corrected fields above before saving.";

type DecisionFormProps = {
  claimId: string;
  proposedDecision: Decision | null;
  correctedFields?: ExpenseCorrections | null;
  correctionsInvalid?: boolean;
  onCorrectionsInvalid?: () => void;
};

export function DecisionForm({
  claimId,
  proposedDecision,
  correctedFields = null,
  correctionsInvalid = false,
  onCorrectionsInvalid,
}: DecisionFormProps) {
  const router = useRouter();
  const decideClaim = useDecideClaim(claimId);
  const [decision, setDecision] = useState<Decision>(proposedDecision ?? "approve");
  const [comment, setComment] = useState("");
  const [commentProblem, setCommentProblem] = useState<string | null>(null);
  const [correctionsBlocked, setCorrectionsBlocked] = useState(false);
  const commentRequired = decision !== proposedDecision || COMMENT_REQUIRED_DECISIONS.includes(decision);

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault();
    const trimmed = comment.trim();
    const problem =
      commentRequired && !trimmed
        ? COMMENT_MISSING
        : trimmed.length > MAX_COMMENT_LENGTH
          ? COMMENT_TOO_LONG
          : null;
    setCommentProblem(problem);
    setCorrectionsBlocked(correctionsInvalid);
    if (correctionsInvalid) onCorrectionsInvalid?.();
    if (problem || correctionsInvalid) return;
    decideClaim
      .mutateAsync({
        decision,
        comment: comment.trim() || null,
        ...(correctedFields ? { corrected_fields: correctedFields } : {}),
      })
      .then(
        () => router.push(getQueuePath()),
        () => {},
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
      <FormError message={correctionsBlocked && correctionsInvalid ? FIX_CORRECTIONS : null} />
      <FormError message={submitError} />
      <Button type="submit" className="self-start" disabled={decideClaim.isPending}>
        {decideClaim.isPending ? "Saving…" : "Save decision"}
      </Button>
    </form>
  );
}
