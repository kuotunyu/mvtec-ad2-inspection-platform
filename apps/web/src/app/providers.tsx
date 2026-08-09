import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 5_000 }, mutations: { retry: false } } });

export function Providers({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}><BrowserRouter>{children}</BrowserRouter></QueryClientProvider>;
}
