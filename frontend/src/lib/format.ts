const DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(isoDate: string): string {
  return DATE_TIME.format(new Date(isoDate));
}
