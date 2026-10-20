import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Overview } from "./overview";

export const metadata = { title: "Graphical Overview · SAR Analyzer" };

export default function OverviewPage() {
  return (
    // useSearchParams() (?file=) needs a Suspense boundary with Cache Components
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <Overview />
    </Suspense>
  );
}
