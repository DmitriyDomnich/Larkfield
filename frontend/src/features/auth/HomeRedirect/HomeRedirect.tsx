"use client";

import { signOut } from "aws-amplify/auth";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoadingSpinner } from "@/components/widgets/LoadingSpinner/LoadingSpinner";
import { QueryState } from "@/components/widgets/QueryState/QueryState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { getHomePath } from "../pageAccess";
import { useMe } from "../hooks/useMe";

export function HomeRedirect() {
  const me = useMe();
  const router = useRouter();
  const homePath = me.data ? getHomePath(me.data.role) : null;

  useEffect(() => {
    if (homePath) {
      router.replace(homePath);
    }
  }, [homePath, router]);

  return (
    <QueryState query={me}>
      {(user) => (user.role === "admin" ? <AdminNotice /> : <LoadingSpinner />)}
    </QueryState>
  );
}

function AdminNotice() {
  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>Administrator pages are coming soon</CardTitle>
        <CardDescription>We are building the tools for administrators. Check back soon.</CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="outline" onClick={() => void signOut()}>
          Sign out
        </Button>
      </CardContent>
    </Card>
  );
}
