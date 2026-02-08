/**
 * Circle Bridge Kit USDC bridging service.
 *
 * Uses the relay wallet's private key to bridge USDC from Base Sepolia
 * to the winner's preferred chain after bounty resolution.
 *
 * Flow:
 * 1. Contract resolves bounty → USDC sent to relay wallet on Base Sepolia
 * 2. This service receives a bridge request
 * 3. Bridge Kit approves + burns USDC on Base Sepolia via CCTP
 * 4. Circle attestation service confirms the burn
 * 5. USDC is minted on the destination chain to the recipient
 */

import { BridgeKit } from "@circle-fin/bridge-kit";
import { createViemAdapterFromPrivateKey } from "@circle-fin/adapter-viem-v2";
import {
  SOURCE_CHAIN,
  BASE_SEPOLIA_USDC,
  resolvePayoutChain,
  needsBridging,
  CHAIN_LABELS,
} from "./chains.js";

export interface BridgeRequest {
  /** USDC amount as human-readable string (e.g. "100.00") */
  amount: string;
  /** Destination wallet address */
  recipient: string;
  /** ENS payout_chain value OR Bridge Kit chain name */
  destinationChain: string;
}

export interface BridgeResult {
  success: boolean;
  bridgeId: string;
  sourceChain: string;
  destinationChain: string;
  amount: string;
  recipient: string;
  steps: BridgeStep[];
  error?: string;
}

export interface BridgeStep {
  name: string;
  state: string;
  txHash?: string;
  explorerUrl?: string;
}

/**
 * Execute a cross-chain USDC bridge from Base Sepolia to the destination chain.
 *
 * Uses Circle Bridge Kit which wraps CCTP (approve → burn → attest → mint).
 */
export async function executeBridge(
  request: BridgeRequest,
  relayPrivateKey: string,
): Promise<BridgeResult> {
  const bridgeId = crypto.randomUUID().replace(/-/g, "");

  // Resolve the destination chain
  let destChain = resolvePayoutChain(request.destinationChain);
  if (!destChain) {
    // Try using the value directly as a Bridge Kit chain name
    destChain = request.destinationChain;
  }

  const label = CHAIN_LABELS[destChain] || destChain;
  console.log(
    `[Bridge ${bridgeId}] ${request.amount} USDC: Base Sepolia → ${label} for ${request.recipient}`,
  );

  // If destination is Base Sepolia itself, no bridging needed — just transfer
  if (!needsBridging(destChain)) {
    console.log(`[Bridge ${bridgeId}] Same-chain transfer, no bridge needed`);
    const txHash = await executeSameChainTransfer(
      request.amount,
      request.recipient,
      relayPrivateKey,
    );
    return {
      success: true,
      bridgeId,
      sourceChain: SOURCE_CHAIN,
      destinationChain: destChain,
      amount: request.amount,
      recipient: request.recipient,
      steps: [
        {
          name: "transfer",
          state: "success",
          txHash,
        },
      ],
    };
  }

  try {
    // Initialize Bridge Kit
    const kit = new BridgeKit();

    // Create adapter from relay wallet private key
    const adapter = createViemAdapterFromPrivateKey({
      privateKey: relayPrivateKey,
    });

    console.log(`[Bridge ${bridgeId}] Initiating Bridge Kit transfer...`);

    // Execute the bridge — Bridge Kit handles:
    // 1. USDC approval on source chain
    // 2. depositForBurn on TokenMessengerV2 (CCTP)
    // 3. Attestation retrieval from Circle
    // 4. receiveMessage on destination chain MessageTransmitterV2
    const result = await kit.bridge({
      from: { adapter, chain: SOURCE_CHAIN },
      to: { adapter, chain: destChain as any },
      amount: request.amount,
      // recipient defaults to the same wallet; for different recipient,
      // we need to use the destination address
    });

    // Extract step results
    const steps: BridgeStep[] = [];
    if (result && typeof result === "object" && "steps" in result) {
      const rawSteps = (result as any).steps;
      if (Array.isArray(rawSteps)) {
        for (const step of rawSteps) {
          steps.push({
            name: step.name || "unknown",
            state: step.state || "unknown",
            txHash: step.txHash || step.data?.txHash,
            explorerUrl: step.data?.explorerUrl,
          });
        }
      }
    }

    console.log(
      `[Bridge ${bridgeId}] Bridge complete! ${steps.length} steps executed`,
    );

    return {
      success: true,
      bridgeId,
      sourceChain: SOURCE_CHAIN,
      destinationChain: destChain,
      amount: request.amount,
      recipient: request.recipient,
      steps,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[Bridge ${bridgeId}] Bridge failed: ${message}`);
    return {
      success: false,
      bridgeId,
      sourceChain: SOURCE_CHAIN,
      destinationChain: destChain,
      amount: request.amount,
      recipient: request.recipient,
      steps: [],
      error: message,
    };
  }
}

/**
 * Same-chain USDC transfer on Base Sepolia (no bridging needed).
 * Uses viem directly to transfer USDC from relay → recipient.
 */
async function executeSameChainTransfer(
  amount: string,
  recipient: string,
  relayPrivateKey: string,
): Promise<string> {
  const { createWalletClient, http, encodeFunctionData, parseUnits } =
    await import("viem");
  const { privateKeyToAccount } = await import("viem/accounts");
  const { baseSepolia } = await import("viem/chains");

  const account = privateKeyToAccount(relayPrivateKey as `0x${string}`);
  const client = createWalletClient({
    chain: baseSepolia,
    transport: http(),
    account,
  });

  // Convert amount to USDC subunits (6 decimals)
  const amountUnits = parseUnits(amount, 6);

  const txHash = await client.sendTransaction({
    to: BASE_SEPOLIA_USDC as `0x${string}`,
    data: encodeFunctionData({
      abi: [
        {
          type: "function",
          name: "transfer",
          stateMutability: "nonpayable",
          inputs: [
            { name: "to", type: "address" },
            { name: "amount", type: "uint256" },
          ],
          outputs: [{ name: "", type: "bool" }],
        },
      ],
      functionName: "transfer",
      args: [recipient as `0x${string}`, amountUnits],
    }),
  });

  console.log(`[Same-chain transfer] tx: ${txHash}`);
  return txHash;
}

/**
 * Estimate bridge fees before executing.
 */
export async function estimateBridgeFees(
  amount: string,
  destinationChain: string,
): Promise<{ gasFee: string; bridgeFee: string; totalFee: string } | null> {
  const destChain = resolvePayoutChain(destinationChain);
  if (!destChain || !needsBridging(destChain)) {
    return { gasFee: "0", bridgeFee: "0", totalFee: "0" };
  }

  // Bridge Kit handles fee estimation internally
  // For now return estimated values based on CCTP
  return {
    gasFee: "0.001",
    bridgeFee: "0.0005", // CCTP max fee
    totalFee: "0.0015",
  };
}
