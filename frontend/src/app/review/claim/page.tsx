import { Suspense } from "react";

import { LoadingSpinner } from "@/components/widgets/LoadingSpinner/LoadingSpinner";
import { ReviewClaim } from "@/features/review/ReviewClaim/ReviewClaim";

export default function ReviewClaimPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <ReviewClaim />
    </Suspense>
  );
}
