/** 1234567890.12 */
export const MONEY = /^(-?)(\d{1,10})(?:\.(\d{1,2}))?$/;
/** EUR */
export const CURRENCY_CODE = /^[A-Z]{3}$/;
/** YYYY-MM-DD */
export const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
/** HH:MM or HH:MM:SS */
export const ISO_TIME = /^\d{2}:\d{2}(:\d{2})?$/;

export function isCalendarDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
}

/** `28.5` → `28.50` */
export function normalizeMoney(value: string): string {
  const match = MONEY.exec(value.trim());
  if (!match) return value.trim();
  const [, sign, whole, fraction = ""] = match;
  return `${sign}${whole.replace(/^0+(?=\d)/, "")}.${fraction.padEnd(2, "0")}`;
}
