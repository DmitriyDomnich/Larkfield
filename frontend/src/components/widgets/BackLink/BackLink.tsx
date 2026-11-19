import Link from "next/link";
import type { ReactNode } from "react";

export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-muted-foreground self-start text-sm hover:underline">
      ← {children}
    </Link>
  );
}
