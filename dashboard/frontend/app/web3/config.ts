"use client";

import { http, createConfig } from "wagmi";
import { baseSepolia, sepolia, arbitrumSepolia } from "wagmi/chains";
import { injected, walletConnect } from "wagmi/connectors";
import { type Chain } from "viem";

// ── Arc Testnet chain definition ──────────────────────────────────────────────

export const arcTestnet: Chain = {
  id: 5042002,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 6 },
  rpcUrls: {
    default: {
      http: [
        process.env.NEXT_PUBLIC_ARC_TESTNET_RPC_URL ||
          "https://rpc-testnet.arc.network",
      ],
    },
  },
  blockExplorers: {
    default: {
      name: "Arc Explorer",
      url: "https://explorer-testnet.arc.network",
    },
  },
  testnet: true,
};

// ── Contract addresses ────────────────────────────────────────────────────────

export const CONTRACTS = {
  REGISTRY: (process.env.NEXT_PUBLIC_REGISTRY_ADDRESS ||
    "0x0000000000000000000000000000000000000000") as `0x${string}`,
  USDC: (process.env.NEXT_PUBLIC_USDC_ADDRESS ||
    "0x3600000000000000000000000000000000000000") as `0x${string}`,
} as const;

// ── Supported chains ────────────────────────────────────────────────────────

export const SUPPORTED_CHAINS = [
  arcTestnet,
  baseSepolia,
  sepolia,
  arbitrumSepolia,
] as const;

// ── Bridge Kit chain name mapping ──────────────────────────────────────────

/** Maps ENS payout_chain text record values → Bridge Kit chain identifiers */
export const PAYOUT_CHAIN_MAP: Record<string, string> = {
  arc: "Arc_Testnet",
  "arc-testnet": "Arc_Testnet",
  base: "Base_Sepolia",
  "base-sepolia": "Base_Sepolia",
  ethereum: "Ethereum_Sepolia",
  sepolia: "Ethereum_Sepolia",
  arbitrum: "Arbitrum_Sepolia",
  "arbitrum-sepolia": "Arbitrum_Sepolia",
};

/** Human-readable chain labels for the UI */
export const CHAIN_LABELS: Record<string, string> = {
  arc: "Arc",
  base: "Base",
  ethereum: "Ethereum",
  arbitrum: "Arbitrum",
};

// ── Wagmi config ────────────────────────────────────────────────────────────

const projectId = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || "";

export const wagmiConfig = createConfig({
  chains: SUPPORTED_CHAINS,
  connectors: [
    injected(),
    ...(projectId ? [walletConnect({ projectId })] : []),
  ],
  transports: {
    [arcTestnet.id]: http(),
    [baseSepolia.id]: http(),
    [sepolia.id]: http(),
    [arbitrumSepolia.id]: http(),
  },
});
