/**
 * Chain configuration for Circle Bridge Kit cross-chain USDC routing.
 *
 * Contracts reside on Base Sepolia. When a bounty is resolved, USDC is sent
 * to the payout relay on Base Sepolia, then bridged to the winner's preferred
 * chain using Circle Bridge Kit (backed by CCTP).
 */

/** The source chain where OpenAudit contracts + USDC live */
export const SOURCE_CHAIN = "Base_Sepolia" as const;

/** USDC address on Base Sepolia */
export const BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";

/** CCTP domain IDs (testnet) */
export const CCTP_DOMAINS: Record<string, number> = {
  Ethereum_Sepolia: 0,
  Arbitrum_Sepolia: 3,
  Base_Sepolia: 6,
  Arc_Testnet: 26,
};

/**
 * Maps ENS payout_chain text record values → Bridge Kit chain identifiers.
 * These are the chains agents can choose to receive their USDC payouts on.
 */
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
  // Avalanche
  avalanche: "Avalanche_Fuji",
  "avalanche-fuji": "Avalanche_Fuji",
  // Polygon
  polygon: "Polygon_PoS_Amoy",
  "polygon-amoy": "Polygon_PoS_Amoy",
  // OP
  optimism: "OP_Sepolia",
  "op-sepolia": "OP_Sepolia",
};

/** Human-readable labels */
export const CHAIN_LABELS: Record<string, string> = {
  Base_Sepolia: "Base Sepolia",
  Arc_Testnet: "Arc Testnet",
  Ethereum_Sepolia: "Ethereum Sepolia",
  Arbitrum_Sepolia: "Arbitrum Sepolia",
  Avalanche_Fuji: "Avalanche Fuji",
  Polygon_PoS_Amoy: "Polygon Amoy",
  OP_Sepolia: "OP Sepolia",
};

/**
 * Resolve an ENS `payout_chain` text record to a Bridge Kit chain name.
 * Returns undefined if not supported.
 */
export function resolvePayoutChain(payoutChain: string): string | undefined {
  return PAYOUT_CHAIN_MAP[payoutChain.toLowerCase().trim()];
}

/** Check if a destination chain requires bridging (i.e. it's not Base Sepolia) */
export function needsBridging(bridgeKitChain: string): boolean {
  return bridgeKitChain !== SOURCE_CHAIN;
}
