import type { components } from "@/api/schema";
import type { ExtractionRead } from "@/api/types";
import { CURRENCY_CODE, ISO_TIME, MONEY, isCalendarDate, normalizeMoney } from "@/core/fieldFormats";

export type ExpenseCorrections = components["schemas"]["ExpenseCorrections"];

export type CorrectableField =
  | "vendor_name"
  | "vendor_tax_id"
  | "document_type"
  | "document_number"
  | "document_date"
  | "document_time"
  | "category"
  | "currency"
  | "subtotal"
  | "tax_amount"
  | "tip_amount"
  | "total";
export type FieldKind = "text" | "document_type" | "category" | "date" | "time" | "currency" | "money";
type FieldSpec = { name: CorrectableField; label: string; kind: FieldKind; required: boolean; maxLength?: number };

export const CORRECTABLE_FIELDS: readonly FieldSpec[] = [
  { name: "vendor_name", label: "Vendor", kind: "text", required: true },
  { name: "vendor_tax_id", label: "Vendor tax id", kind: "text", required: false, maxLength: 64 },
  { name: "document_type", label: "Document type", kind: "document_type", required: true },
  { name: "document_number", label: "Document number", kind: "text", required: false, maxLength: 128 },
  { name: "document_date", label: "Date", kind: "date", required: true },
  { name: "document_time", label: "Time", kind: "time", required: false },
  { name: "category", label: "Category", kind: "category", required: true },
  { name: "currency", label: "Currency", kind: "currency", required: true },
  { name: "subtotal", label: "Subtotal", kind: "money", required: false },
  { name: "tax_amount", label: "Tax", kind: "money", required: false },
  { name: "tip_amount", label: "Tip", kind: "money", required: false },
  { name: "total", label: "Total", kind: "money", required: true },
];

export type FieldValues = Record<CorrectableField, string>;
export type FieldProblems = Partial<Record<CorrectableField, string>>;

/** `20:15:00` → `20:15` */
function normalizeTime(value: string): string {
  return value.endsWith(":00") && value.length === 8 ? value.slice(0, 5) : value;
}

function normalize(kind: FieldKind, value: string): string {
  if (kind === "money") return normalizeMoney(value);
  if (kind === "time") return normalizeTime(value);
  return value.trim();
}

export function isSameValue(kind: FieldKind, a: string, b: string): boolean {
  return normalize(kind, a) === normalize(kind, b);
}

export function fieldValuesOf(extraction: ExtractionRead): FieldValues {
  const values = {} as FieldValues;
  for (const { name, kind } of CORRECTABLE_FIELDS) {
    values[name] = normalize(kind, String(extraction[name] ?? ""));
  }
  return values;
}

export function withCorrections(
  values: FieldValues,
  correctedFields: Record<string, unknown> | null | undefined,
): FieldValues {
  const corrected = { ...values };
  for (const { name, kind } of CORRECTABLE_FIELDS) {
    if (correctedFields && name in correctedFields) {
      const value = correctedFields[name];
      corrected[name] = normalize(kind, value === null || value === undefined ? "" : String(value));
    }
  }
  return corrected;
}

export function toCorrectedFields(extracted: FieldValues, values: FieldValues): ExpenseCorrections | null {
  const corrections: Record<string, string | null> = {};
  for (const { name, kind } of CORRECTABLE_FIELDS) {
    if (!isSameValue(kind, extracted[name], values[name])) {
      const value = normalize(kind, values[name]);
      corrections[name] = value === "" ? null : value;
    }
  }
  return Object.keys(corrections).length > 0 ? (corrections as ExpenseCorrections) : null;
}

export function changedFieldLabels(before: FieldValues, after: FieldValues): string[] {
  return CORRECTABLE_FIELDS.filter(({ name, kind }) => !isSameValue(kind, before[name], after[name])).map(
    ({ label }) => label,
  );
}

function findProblem({ kind, required, maxLength }: FieldSpec, rawValue: string): string | null {
  const value = rawValue.trim();
  if (!value) return required ? "This field is required." : null;
  if (maxLength && value.length > maxLength) return `Keep it to ${maxLength} characters.`;
  switch (kind) {
    case "currency":
      return CURRENCY_CODE.test(value) ? null : "Use a three-letter code in capitals, e.g. EUR.";
    case "date":
      return isCalendarDate(value) ? null : "Enter a valid date.";
    case "time":
      return ISO_TIME.test(value) ? null : "Enter a valid time.";
    case "money":
      return MONEY.test(value) ? null : "Use an amount with at most 10 digits and 2 decimals, e.g. 28.50.";
    default:
      return null;
  }
}

export function findFieldProblems(values: FieldValues): FieldProblems {
  const problems: FieldProblems = {};
  for (const spec of CORRECTABLE_FIELDS) {
    const problem = findProblem(spec, values[spec.name]);
    if (problem) problems[spec.name] = problem;
  }
  const total = normalizeMoney(values.total);
  if (!problems.total && (total.startsWith("-") || /^0+\.00$/.test(total))) {
    problems.total = "The total must be more than 0.";
  }
  return problems;
}
