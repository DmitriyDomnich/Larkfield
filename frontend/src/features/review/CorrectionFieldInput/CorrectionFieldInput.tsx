import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { DOCUMENT_TYPES, EXPENSE_CATEGORIES } from "@/core/expenseValues";
import { formatEnumValue } from "@/lib/format";

import type { CorrectableField, FieldKind } from "../corrections";

type CorrectionFieldInputProps = {
  name: CorrectableField;
  kind: FieldKind;
  required: boolean;
  value: string;
  invalid: boolean;
  onChange: (value: string) => void;
};

export function CorrectionFieldInput({ name, kind, required, value, invalid, onChange }: CorrectionFieldInputProps) {
  const common = { id: `field-${name}`, value, "aria-invalid": invalid || undefined };
  if (kind === "document_type" || kind === "category") {
    const options = kind === "document_type" ? DOCUMENT_TYPES : EXPENSE_CATEGORIES;
    return (
      <NativeSelect {...common} className="w-full max-w-64" onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <NativeSelectOption key={option} value={option}>
            {formatEnumValue(option)}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    );
  }
  const type = kind === "date" ? "date" : kind === "time" ? "time" : "text";
  return (
    <Input
      {...common}
      type={type}
      className="max-w-64"
      inputMode={kind === "money" ? "decimal" : undefined}
      required={required}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
