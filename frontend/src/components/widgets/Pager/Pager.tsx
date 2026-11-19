import { Button } from "@/components/ui/button";

type PagerProps = {
  offset: number;
  limit: number;
  total: number;
  onOffsetChange: (offset: number) => void;
};

export function Pager({ offset, limit, total, onOffsetChange }: PagerProps) {
  const lastShown = Math.min(offset + limit, total);
  return (
    <div className="flex items-center justify-between gap-4 py-3 text-sm">
      <span className="text-muted-foreground">
        {offset + 1}–{lastShown} of {total}
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={lastShown >= total}
          onClick={() => onOffsetChange(offset + limit)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
