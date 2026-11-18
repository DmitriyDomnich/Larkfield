import { Loader2Icon } from "lucide-react";

export function LoadingSpinner() {
  return (
    <div role="status" className="text-muted-foreground flex items-center gap-2 p-4 text-sm">
      <Loader2Icon className="size-4 animate-spin" aria-hidden />
      Loading…
    </div>
  );
}
