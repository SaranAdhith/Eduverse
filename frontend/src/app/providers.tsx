"use client";

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useJournal, useParticipant } from "@/lib/store";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );
  const hydrate = useParticipant((s) => s.hydrate);
  const hydrateJournal = useJournal((s) => s.hydrate);

  // Load the persisted participant code and progress journal once, on the
  // client, to avoid a hydration mismatch (DOC_07 §5).
  useEffect(() => {
    hydrate();
    hydrateJournal();
  }, [hydrate, hydrateJournal]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
