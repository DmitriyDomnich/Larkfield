const DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(isoDate: string): string {
  return DATE_TIME.format(new Date(isoDate));
}

/** `client_entertainment` → `Client entertainment` */
export function formatEnumValue(value: string): string {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
