"use client";

import { signOut } from "aws-amplify/auth";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { LogoMark } from "@/components/widgets/LogoMark/LogoMark";
import { PageGate } from "@/features/auth/PageGate/PageGate";
import { canOpenPage } from "@/features/auth/pageAccess";
import { useMe } from "@/features/auth/hooks/useMe";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/claims", label: "Claims" },
  { href: "/review", label: "Review queue" },
];

function isCurrentSection(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe();
  const pathname = usePathname();
  const role = me.data?.role;
  const links = role ? NAV_LINKS.filter((link) => canOpenPage(role, link.href)) : [];

  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <LogoMark />
            Larkfield
          </Link>
          {links.length > 0 && <div className="bg-border h-6 w-px" aria-hidden />}
          <nav aria-label="Main" className="flex gap-1 text-sm">
            {links.map((link) => {
              const current = isCurrentSection(pathname, link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={current ? "page" : undefined}
                  className={cn(
                    "text-muted-foreground hover:bg-muted hover:text-foreground rounded-md px-3 py-1.5 transition-colors",
                    current && "bg-muted text-foreground font-medium",
                  )}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            {me.data && <span className="text-muted-foreground">{me.data.email}</span>}
            <Button variant="outline" size="sm" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <PageGate>{children}</PageGate>
      </main>
    </>
  );
}
