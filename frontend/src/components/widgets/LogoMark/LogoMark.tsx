import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7", className)}>
      <rect width="32" height="32" rx="7" fill="#171717" />
      <path d="M10 7h4.5v13.5H23V25H10z" fill="#fafafa" />
      <circle cx="22" cy="10" r="3" fill="#f59e0b" />
    </svg>
  );
}
