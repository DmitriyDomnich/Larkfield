"use client";

import type { ExtractionRead } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FormError } from "@/components/widgets/FormError/FormError";
import { formatEnumValue, formatQuantity, formatUnitPrice } from "@/lib/format";

import {
  CORRECTABLE_FIELDS,
  fieldValuesOf,
  isSameValue,
  type CorrectableField,
  type FieldKind,
  type FieldProblems,
  type FieldValues,
} from "../corrections";
import { CorrectionFieldInput } from "../CorrectionFieldInput/CorrectionFieldInput";

type ExtractionPanelProps = {
  extraction: ExtractionRead;
  correctedValues: FieldValues;
  problems?: FieldProblems;
  editing?: boolean;
  canEdit?: boolean;
  onEditingChange?: (editing: boolean) => void;
  onChange?: (field: CorrectableField, value: string) => void;
};

export function ExtractionPanel({
  extraction,
  correctedValues: values,
  problems = {},
  editing = false,
  canEdit = false,
  onEditingChange,
  onChange,
}: ExtractionPanelProps) {
  const extracted = fieldValuesOf(extraction);
  const display = (kind: FieldKind, value: string, currency: string) => {
    if (!value) return "—";
    if (kind === "money") return `${value} ${currency}`;
    if (kind === "document_type" || kind === "category") return formatEnumValue(value);
    return value;
  };

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-medium">Fields</h2>
        {canEdit && (
          <Button variant="outline" size="sm" onClick={() => onEditingChange?.(!editing)}>
            {editing ? "Done editing" : "Edit fields"}
          </Button>
        )}
      </div>
      {extraction.warnings.map((warning) => (
        <Alert key={warning.code} className="border-amber-500 text-amber-900 dark:text-amber-200">
          <AlertTitle>Check this</AlertTitle>
          <AlertDescription>{warning.message}</AlertDescription>
        </Alert>
      ))}
      <dl className="grid grid-cols-[max-content_1fr] items-baseline gap-x-6 gap-y-1 text-sm">
        {CORRECTABLE_FIELDS.map(({ name, label, kind, required }) => {
          const corrected = !isSameValue(kind, extracted[name], values[name]);
          const mark = corrected && (
            <CorrectedMark extracted={display(kind, extracted[name], extracted.currency)} />
          );
          return (
            <div key={name} className="contents">
              <dt className="text-muted-foreground">
                {editing ? <Label htmlFor={`field-${name}`}>{label}</Label> : label}
              </dt>
              <dd className="flex flex-col gap-1">
                {editing ? (
                  <>
                    <CorrectionFieldInput
                      name={name}
                      kind={kind}
                      required={required}
                      value={values[name]}
                      invalid={Boolean(problems[name])}
                      onChange={(value) => onChange?.(name, value)}
                    />
                    <FormError message={problems[name]} />
                    {mark}
                  </>
                ) : (
                  <span className="flex flex-wrap items-center gap-2">
                    {display(kind, values[name], values.currency)}
                    {mark}
                  </span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
      {extraction.line_items.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Item</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Unit price</TableHead>
              <TableHead className="text-right">Amount</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {extraction.line_items.map((item, index) => (
              <TableRow key={index}>
                <TableCell className="whitespace-normal">{item.description}</TableCell>
                <TableCell className="text-right">{formatQuantity(item.quantity)}</TableCell>
                <TableCell className="text-right">{item.unit_price === null ? "—" : formatUnitPrice(item.unit_price)}</TableCell>
                <TableCell className="text-right">{item.amount}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}

function CorrectedMark({ extracted }: { extracted: string }) {
  return (
    <span className="flex flex-wrap items-center gap-2">
      <Badge variant="secondary">Corrected</Badge>
      <span className="text-muted-foreground text-xs">
        extracted: <s>{extracted}</s>
      </span>
    </span>
  );
}
