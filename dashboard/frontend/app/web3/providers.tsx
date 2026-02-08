"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WagmiProvider } from "wagmi";
import { wagmiConfig } from "./config";

// connectkit is optional for local development. If it's not installed, use a passthrough provider.
let ConnectKitProvider: React.FC<{
  children: React.ReactNode;
  theme?: string;
  options?: any;
}> = ({ children }) => <>{children}</>;
try {
  // Use eval('require') to avoid the bundler statically resolving `connectkit`.
  // This keeps the module optional at build time.
  // eslint-disable-next-line no-eval
  // @ts-ignore - runtime require via eval
  const req = eval("require");
  // Build the package name dynamically to avoid bundler static analysis
  const ck = req("con" + "nectkit");
  ConnectKitProvider =
    ck.ConnectKitProvider ?? ck.default ?? ConnectKitProvider;
} catch (err) {
  // If connectkit isn't installed, log a friendly warning and continue
  // eslint-disable-next-line no-console
  console.warn(
    "connectkit not installed; wallet modal disabled for local dev.",
  );
}

const queryClient = new QueryClient();

export function Web3Provider({ children }: { children: React.ReactNode }) {
  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <ConnectKitProvider theme="midnight" options={{ initialChainId: 0 }}>
          {children}
        </ConnectKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
