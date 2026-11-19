"use client";

import type { ExtractionRead } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { formatEnumValue } from "@/lib/format";

import { useExtraction } from "../hooks/useExtraction";

export function ExtractionPanel({ claimId }: { claimId: string }) {
  const extraction = useExtraction(claimId);
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-medium">Fields</h2>
      <QueryState query={extraction}>{(data) => <ExtractedFields extraction={data} />}</QueryState>
    </section>
  );
}

function ExtractedFields({ extraction }: { extraction: ExtractionRead }) {
  const { currency } = extraction;
  const money = (amount: string | null) => (amount === null ? "—" : `${amount} ${currency}`);
  const fields: [string, string][] = [
    ["Vendor", extraction.vendor_name],
    ["Vendor tax id", extraction.vendor_tax_id ?? "—"],
    [
      "Document",
      `${formatEnumValue(extraction.document_type)} ${extraction.document_number ?? ""}`.trim(),
    ],
    ["Date", [extraction.document_date, extraction.document_time].filter(Boolean).join(" ")],
    ["Category", formatEnumValue(extraction.category)],
    ["Subtotal", money(extraction.subtotal)],
    ["Tax", money(extraction.tax_amount)],
    ["Tip", money(extraction.tip_amount)],
    ["Total", money(extraction.total)],
  ];

  return (
    <div className="flex flex-col gap-3">
      {extraction.warnings.map((warning) => (
        <Alert key={warning.code} className="border-amber-500 text-amber-900 dark:text-amber-200">
          <AlertTitle>Check this</AlertTitle>
          <AlertDescription>{warning.message}</AlertDescription>
        </Alert>
      ))}
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
        {fields.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
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
                <TableCell className="text-right">{item.quantity}</TableCell>
                <TableCell className="text-right">{item.unit_price ?? "—"}</TableCell>
                <TableCell className="text-right">{item.amount}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
