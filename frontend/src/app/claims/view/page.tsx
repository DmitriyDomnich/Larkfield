import { Suspense } from "react";

import { LoadingSpinner } from "@/components/widgets/LoadingSpinner/LoadingSpinner";
import { ClaimDetail } from "@/features/claims/ClaimDetail/ClaimDetail";

export default function ClaimViewPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <ClaimDetail />
    </Suspense>
  );
}
