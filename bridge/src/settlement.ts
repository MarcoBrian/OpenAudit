/**
 * Settlement service — orchestrates the full payout flow:
 *
 * 1. Listen for BountySettlement events from the OpenAuditRegistry on Base Sepolia
 * 2. Read the winner's preferred payout chain from their ENS text record
 * 3. Bridge USDC from Base Sepolia → destination chain using Circle Bridge Kit
 *
 * This is the core logic that connects contract resolution to cross-chain payout.
 */

import { createPublicClient, http, parseAbiItem, formatUnits } from "viem";
import { baseSepolia } from "viem/chains";
import { executeBridge, type BridgeResult } from "./bridger.js";
import { getAgentPayoutChain } from "./ens-resolver.js";
import { resolvePayoutChain, needsBridging, SOURCE_CHAIN } from "./chains.js";

export interface SettlementEvent {
  bountyId: bigint;
  winner: string;
  reward: bigint;
  payoutChain: string;
  blockNumber: bigint;
  txHash: string;
}

export interface SettlementResult {
  bountyId: string;
  winner: string;
  rewardUsdc: string;
  payoutChain: string;
  bridgeResult?: BridgeResult;
  status: "bridged" | "same-chain" | "skipped" | "error";
  error?: string;
}

/**
 * Process a settlement: bridge USDC from relay wallet on Base Sepolia
 * to the winner's preferred chain.
 *
 * @param bountyId - The bounty ID that was resolved
 * @param winner - The winner's address
 * @param rewardAmount - USDC amount in subunits (6 decimals)
 * @param payoutChain - ENS payout_chain value
 * @param relayPrivateKey - The relay wallet's private key (holds USDC on Base Sepolia)
 */
export async function processSettlement(
  bountyId: string,
  winner: string,
  rewardAmount: string, // Human-readable USDC amount
  payoutChain: string,
  relayPrivateKey: string,
): Promise<SettlementResult> {
  console.log(
    `[Settlement] Processing bounty #${bountyId}: ${rewardAmount} USDC → ${winner} on ${payoutChain || "default"}`,
  );

  // If no payout chain specified, default to same-chain (Base Sepolia)
  if (!payoutChain || payoutChain.trim() === "") {
    payoutChain = "base";
  }

  const destChain = resolvePayoutChain(payoutChain);
  if (!destChain) {
    return {
      bountyId,
      winner,
      rewardUsdc: rewardAmount,
      payoutChain,
      status: "error",
      error: `Unsupported payout chain: ${payoutChain}`,
    };
  }

  // If same chain, do a direct USDC transfer
  if (!needsBridging(destChain)) {
    console.log(`[Settlement] Same-chain payout on Base Sepolia`);
    const bridgeResult = await executeBridge(
      {
        amount: rewardAmount,
        recipient: winner,
        destinationChain: payoutChain,
      },
      relayPrivateKey,
    );

    return {
      bountyId,
      winner,
      rewardUsdc: rewardAmount,
      payoutChain,
      bridgeResult,
      status: bridgeResult.success ? "same-chain" : "error",
      error: bridgeResult.error,
    };
  }

  // Cross-chain bridge via Circle Bridge Kit
  console.log(`[Settlement] Bridging from Base Sepolia → ${destChain}`);

  const bridgeResult = await executeBridge(
    {
      amount: rewardAmount,
      recipient: winner,
      destinationChain: payoutChain,
    },
    relayPrivateKey,
  );

  return {
    bountyId,
    winner,
    rewardUsdc: rewardAmount,
    payoutChain,
    bridgeResult,
    status: bridgeResult.success ? "bridged" : "error",
    error: bridgeResult.error,
  };
}

/**
 * Watch for BountySettlement events and auto-process them.
 *
 * This creates a background watcher that listens for events on Base Sepolia
 * and automatically triggers the bridge flow.
 */
export function watchSettlements(
  registryAddress: string,
  relayPrivateKey: string,
  onSettlement?: (result: SettlementResult) => void,
): () => void {
  const rpcUrl = process.env.BASE_SEPOLIA_RPC_URL || process.env.RPC_URL || "";

  const client = createPublicClient({
    chain: baseSepolia,
    transport: http(rpcUrl || undefined),
  });

  const unwatch = client.watchEvent({
    address: registryAddress as `0x${string}`,
    event: parseAbiItem(
      "event BountySettlement(uint256 indexed bountyId, address indexed winner, uint256 reward, string payoutChain)",
    ),
    onLogs: async (logs) => {
      for (const log of logs) {
        const args = log.args as any;
        const bountyId = String(args.bountyId);
        const winner = args.winner as string;
        const reward = args.reward as bigint;
        const payoutChain = args.payoutChain as string;

        // Convert reward from subunits to human-readable
        const rewardUsdc = formatUnits(reward, 6);

        console.log(
          `[Watcher] BountySettlement event: bounty #${bountyId}, ` +
            `winner=${winner}, reward=${rewardUsdc} USDC, chain=${payoutChain}`,
        );

        try {
          const result = await processSettlement(
            bountyId,
            winner,
            rewardUsdc,
            payoutChain,
            relayPrivateKey,
          );
          onSettlement?.(result);
        } catch (err) {
          console.error(
            `[Watcher] Settlement failed for bounty #${bountyId}:`,
            err,
          );
          onSettlement?.({
            bountyId,
            winner,
            rewardUsdc,
            payoutChain,
            status: "error",
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    },
  });

  console.log(
    `[Watcher] Listening for BountySettlement events on ${registryAddress}`,
  );
  return unwatch;
}
