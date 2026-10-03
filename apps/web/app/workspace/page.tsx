import { Suspense } from "react";
import { OverviewView } from "@/components/workspace/overview-view";
import { LoadingState } from "@/components/ui/states";

export const metadata = {
  title: "Overview",
};

export default function Page() {
  return (
    <Suspense fallback={<LoadingState label="Loading workspace…" />}>
      <OverviewView />
    </Suspense>
  );
}
