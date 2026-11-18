"use client";

import "@aws-amplify/ui-react/styles.css";

import { Authenticator, useAuthenticator } from "@aws-amplify/ui-react";
import { useQueryClient } from "@tanstack/react-query";
import { Amplify } from "aws-amplify";
import { useEffect, type ReactNode } from "react";

import { LoadingSpinner } from "@/components/widgets/LoadingSpinner/LoadingSpinner";

import { amplifyConfig } from "../amplifyConfig";

Amplify.configure(amplifyConfig);

export function AuthGate({ children }: { children: ReactNode }) {
  return (
    <Authenticator.Provider>
      <SignedInContent>{children}</SignedInContent>
    </Authenticator.Provider>
  );
}

function SignedInContent({ children }: { children: ReactNode }) {
  const { authStatus } = useAuthenticator((context) => [context.authStatus]);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (authStatus === "unauthenticated") {
      queryClient.clear();
    }
  }, [authStatus, queryClient]);

  if (authStatus === "configuring") {
    return <LoadingSpinner />;
  }

  if (authStatus !== "authenticated") {
    return (
      <main className="flex flex-1 items-center justify-center p-8">
        <Authenticator />
      </main>
    );
  }

  return children;
}
