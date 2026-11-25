import { useMemo, useState } from "react";

import type { ExtractionRead, ReviewRound } from "@/api/types";

import {
  changedFieldLabels,
  fieldValuesOf,
  findFieldProblems,
  toCorrectedFields,
  withCorrections,
  type CorrectableField,
  type FieldValues,
} from "../corrections";

function newestCorrections(rounds: ReviewRound[] | undefined) {
  return rounds?.find((round) => round.decision)?.decision?.corrected_fields ?? null;
}

function valuesSeenByNewestProposal(extracted: FieldValues, rounds: ReviewRound[] | undefined) {
  return withCorrections(extracted, rounds?.[1]?.decision?.corrected_fields);
}

type CorrectionsSource = {
  extraction: ExtractionRead | undefined;
  rounds: ReviewRound[] | undefined;
  editable: boolean;
};

export function useCorrections({ extraction, rounds, editable }: CorrectionsSource) {
  const proposalId = rounds?.[0]?.proposal_id ?? null;
  const [draft, setDraft] = useState<{ proposalId: string | null; values: FieldValues } | null>(null);
  const [editingProposalId, setEditingProposalId] = useState<string | null>(null);

  const extracted = useMemo(() => extraction && fieldValuesOf(extraction), [extraction]);
  const savedCorrections = newestCorrections(rounds);
  const draftValues = draft?.proposalId === proposalId ? draft.values : null;
  const values = draftValues ?? (extracted ? withCorrections(extracted, savedCorrections) : null);
  const problems = values ? findFieldProblems(values) : {};

  return {
    proposalId,
    values,
    problems,
    isInvalid: Object.keys(problems).length > 0,
    editing: editable && editingProposalId === proposalId,
    setEditing: (start: boolean) => setEditingProposalId(start ? proposalId : null),
    changeField: (field: CorrectableField, value: string) => {
      if (values) setDraft({ proposalId, values: { ...values, [field]: value } });
    },
    correctedFields: extracted && values ? toCorrectedFields(extracted, values) : savedCorrections,
    correctedSinceProposal:
      extracted && values ? changedFieldLabels(valuesSeenByNewestProposal(extracted, rounds), values) : [],
  };
}
