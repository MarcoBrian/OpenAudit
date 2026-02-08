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
          "https://arc-testnet.g.alchemy.com/v2/0NGmDdPvkohc6Xq0vi92Z",
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
    "0x5f712628FA58d4DdBbdD3e681232f1272dd9b688") as `0x${string}`,
  USDC: (process.env.NEXT_PUBLIC_USDC_ADDRESS ||
    "0x036CbD53842c5426634e7929541eC2318f3dCF7e") as `0x${string}`,
} as const;

// ── Supported chains ────────────────────────────────────────────────────────

export const SUPPORTED_CHAINS = [
  baseSepolia,
  arcTestnet,
  sepolia,
  arbitrumSepolia,
] as const;

/** The primary chain where the Registry lives */
export const HOME_CHAIN = baseSepolia;

// ── Bridge Kit chain name mapping ──────────────────────────────────────────

/** Source chain where contracts + USDC live */
export const SOURCE_CHAIN = "Base_Sepolia" as const;

/** USDC address on Base Sepolia */
export const BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";

/** Maps ENS payout_chain text record values → Bridge Kit chain identifiers */
export const PAYOUT_CHAIN_MAP: Record<string, string> = {
  // Base Sepolia (same-chain, no bridge needed)
  base: "Base_Sepolia",
  "base-sepolia": "Base_Sepolia",
  // Arc
  arc: "Arc_Testnet",
  "arc-testnet": "Arc_Testnet",
  // Ethereum
  ethereum: "Ethereum_Sepolia",
  sepolia: "Ethereum_Sepolia",
  "ethereum-sepolia": "Ethereum_Sepolia",
  // Arbitrum
  arbitrum: "Arbitrum_Sepolia",
  "arbitrum-sepolia": "Arbitrum_Sepolia",
};

/** Human-readable chain labels for the UI */
export const CHAIN_LABELS: Record<string, string> = {
  base: "Base",
  arc: "Arc",
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
