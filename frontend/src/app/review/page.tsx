import { Suspense } from "react";

import { LoadingSpinner } from "@/components/widgets/LoadingSpinner/LoadingSpinner";
import { ReviewQueue } from "@/features/review/ReviewQueue/ReviewQueue";

export default function ReviewPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <ReviewQueue />
    </Suspense>
  );
}
