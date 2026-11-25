import type { DocumentType, ExpenseCategory } from "@/api/types";

export const DOCUMENT_TYPES = ["receipt", "invoice", "card_slip"] as const satisfies readonly DocumentType[];

export const EXPENSE_CATEGORIES = [
  "meal",
  "client_entertainment",
  "team_meal",
  "air_travel",
  "rail_travel",
  "taxi",
  "mileage",
  "hotel",
  "equipment",
  "software",
  "accessories",
  "training",
  "conference",
  "fine",
  "other",
] as const satisfies readonly ExpenseCategory[];
