import { Suspense } from "react";
import { MissionView } from "@/components/workspace/mission-view";
import { LoadingState } from "@/components/ui/states";

export const metadata = {
  title: "Mission journey",
};

export default function Page() {
  return (
    <Suspense fallback={<LoadingState label="Loading mission…" />}>
      <MissionView />
    </Suspense>
  );
}
