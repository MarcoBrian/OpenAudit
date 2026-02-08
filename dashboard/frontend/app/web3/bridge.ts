/**
 * Bridge Kit service — wraps Circle Bridge Kit for cross-chain USDC settlement.
 *
 * After a bounty is resolved on Arc, USDC lands in the relay wallet.
 * This module bridges that USDC from Arc → the winner's preferred chain.
 */

import { PAYOUT_CHAIN_MAP } from "./config";

export type BridgeStatus =
  | { state: "idle" }
  | { state: "approving" }
  | { state: "bridging" }
  | { state: "waiting-attestation"; txHash: string }
  | { state: "complete"; txHash: string; destTxHash?: string }
  | { state: "error"; message: string };

export interface BridgeRequest {
  amount: string; // USDC amount as string (e.g. "1000.00")
  recipientAddress: string; // Destination address (winner)
  payoutChain: string; // ENS payout_chain value (e.g. "base")
}

/**
 * Maps a payout_chain ENS text record value to a Bridge Kit chain identifier.
 * Returns undefined if the chain is not supported.
 */
export function resolveBridgeChain(payoutChain: string): string | undefined {
  const normalized = payoutChain.toLowerCase().trim();
  return PAYOUT_CHAIN_MAP[normalized];
}

/**
 * Get the list of supported payout chains for the UI dropdown.
 */
export function getSupportedPayoutChains(): { value: string; label: string }[] {
  return [
    { value: "arc", label: "Arc (same chain)" },
    { value: "base", label: "Base" },
    { value: "ethereum", label: "Ethereum" },
    { value: "arbitrum", label: "Arbitrum" },
  ];
}

/**
 * Bridge USDC from Arc to the winner's preferred chain.
 *
 * This function is called from the settlement flow after bounty resolution.
 * It uses Circle Bridge Kit (CCTP) under the hood.
 *
 * @param request - The bridge parameters
 * @param onStatusChange - Callback for tracking bridge progress
 *
 * NOTE: For hackathon MVP, the actual Bridge Kit SDK calls require a Node.js
 * backend or a wallet adapter. This implementation provides the structure
 * and status tracking, with the actual bridging delegated to the backend API.
 */
export async function bridgePayout(
  request: BridgeRequest,
  onStatusChange: (status: BridgeStatus) => void,
): Promise<void> {
  const destChain = resolveBridgeChain(request.payoutChain);

  // If destination is Arc itself, no bridging needed
  if (!destChain || destChain === "Arc_Testnet") {
    onStatusChange({
      state: "complete",
      txHash: "same-chain",
    });
    return;
  }

  try {
    onStatusChange({ state: "bridging" });

    // Call the backend API to execute the bridge via Bridge Kit
    const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
    const res = await fetch(`${apiBase}/api/bridge/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount: request.amount,
        recipient: request.recipientAddress,
        destination_chain: destChain,
      }),
    });

    if (!res.ok) {
      const err = await res
        .json()
        .catch(() => ({ error: "Bridge request failed" }));
      throw new Error(err.error || `Bridge failed: ${res.status}`);
    }

    const data = await res.json();

    onStatusChange({
      state: "waiting-attestation",
      txHash: data.source_tx_hash || "",
    });

    // Poll for completion
    if (data.bridge_id) {
      const pollResult = await pollBridgeStatus(apiBase, data.bridge_id);
      onStatusChange({
        state: "complete",
        txHash: data.source_tx_hash || "",
        destTxHash: pollResult.dest_tx_hash,
      });
    } else {
      onStatusChange({
        state: "complete",
        txHash: data.source_tx_hash || "",
      });
    }
  } catch (err) {
    onStatusChange({
      state: "error",
      message: err instanceof Error ? err.message : "Unknown bridge error",
    });
  }
}

async function pollBridgeStatus(
  apiBase: string,
  bridgeId: string,
  maxAttempts = 60,
  intervalMs = 5000,
): Promise<{ dest_tx_hash?: string }> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    try {
      const res = await fetch(`${apiBase}/api/bridge/status/${bridgeId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === "complete") {
          return { dest_tx_hash: data.dest_tx_hash };
        }
        if (data.status === "failed") {
          throw new Error(data.error || "Bridge failed");
        }
      }
    } catch {
      // Continue polling
    }
  }
  return {}; // Timeout — bridge may still complete
}
