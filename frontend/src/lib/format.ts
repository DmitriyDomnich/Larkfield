const DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(isoDate: string): string {
  return DATE_TIME.format(new Date(isoDate));
}

/** `client_entertainment` → `Client entertainment` */
export function formatEnumValue(value: string): string {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** `1.000` → `1`, `0.250` → `0.25` */
export function formatQuantity(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

/** `14.5000` → `14.50`, `0.0450` → `0.045` */
export function formatUnitPrice(value: string): string {
  const [whole, fraction = ""] = value.split(".");
  return `${whole}.${fraction.replace(/0+$/, "").padEnd(2, "0")}`;
}
