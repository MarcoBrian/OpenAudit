/**
 * Express HTTP server for the Bridge Kit service.
 *
 * Provides REST endpoints for the Python backend to trigger cross-chain
 * USDC bridging after bounty resolution. Also watches for on-chain
 * BountySettlement events for automatic processing.
 *
 * Endpoints:
 *   POST /bridge           — Execute a cross-chain USDC bridge
 *   POST /settle           — Process a bounty settlement (reads ENS, bridges)
 *   GET  /bridge/:id       — Check bridge status
 *   GET  /chains           — List supported destination chains
 *   GET  /health           — Health check
 */

import express from "express";
import {
  executeBridge,
  estimateBridgeFees,
  type BridgeResult,
} from "./bridger.js";
import {
  processSettlement,
  watchSettlements,
  type SettlementResult,
} from "./settlement.js";
import { getAgentPayoutChain } from "./ens-resolver.js";
import {
  PAYOUT_CHAIN_MAP,
  CHAIN_LABELS,
  SOURCE_CHAIN,
  resolvePayoutChain,
} from "./chains.js";

const app = express();
app.use(express.json());

// ── Config ──

const PORT = parseInt(process.env.BRIDGE_SERVICE_PORT || "3001", 10);
const RELAY_PRIVATE_KEY = process.env.PAYOUT_RELAY_PRIVATE_KEY || "";
const REGISTRY_ADDRESS =
  process.env.OPENAUDIT_REGISTRY_ADDRESS ||
  process.env.NEXT_PUBLIC_REGISTRY_ADDRESS ||
  "";

// ── In-memory state ──

const bridgeResults = new Map<string, BridgeResult>();
const settlementResults = new Map<string, SettlementResult>();

// ── Endpoints ──

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "openaudit-bridge",
    sourceChain: SOURCE_CHAIN,
    relayConfigured: !!RELAY_PRIVATE_KEY,
    registryConfigured: !!REGISTRY_ADDRESS,
  });
});

/**
 * List supported destination chains.
 */
app.get("/chains", (_req, res) => {
  const chains = Object.entries(PAYOUT_CHAIN_MAP).reduce(
    (acc, [key, bridgeKitName]) => {
      if (!acc.find((c) => c.bridgeKitName === bridgeKitName)) {
        acc.push({
          value: key,
          bridgeKitName,
          label: CHAIN_LABELS[bridgeKitName] || bridgeKitName,
        });
      }
      return acc;
    },
    [] as { value: string; bridgeKitName: string; label: string }[],
  );

  res.json({ sourceChain: SOURCE_CHAIN, supportedDestinations: chains });
});

/**
 * Execute a cross-chain USDC bridge.
 *
 * Body: { amount: string, recipient: string, destination_chain: string }
 */
app.post("/bridge", async (req, res) => {
  const { amount, recipient, destination_chain } = req.body;

  if (!amount || !recipient || !destination_chain) {
    res.status(400).json({
      error: "Missing required fields: amount, recipient, destination_chain",
    });
    return;
  }

  if (!RELAY_PRIVATE_KEY) {
    res.status(500).json({ error: "Relay wallet private key not configured" });
    return;
  }

  const destChain = resolvePayoutChain(destination_chain);
  if (!destChain) {
    res.status(400).json({
      error: `Unsupported destination chain: ${destination_chain}`,
      supported: Object.keys(PAYOUT_CHAIN_MAP),
    });
    return;
  }

  try {
    const result = await executeBridge(
      { amount, recipient, destinationChain: destination_chain },
      RELAY_PRIVATE_KEY,
    );

    bridgeResults.set(result.bridgeId, result);

    res.json({
      bridge_id: result.bridgeId,
      status: result.success ? "complete" : "failed",
      source_chain: result.sourceChain,
      destination_chain: result.destinationChain,
      amount: result.amount,
      recipient: result.recipient,
      steps: result.steps,
      error: result.error,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: message });
  }
});

/**
 * Process a bounty settlement — resolves ENS payout chain + bridges.
 *
 * Body: {
 *   bounty_id: string,
 *   winner: string,
 *   reward_usdc: string,    // Human-readable (e.g. "100.00")
 *   payout_chain?: string   // Override; if omitted, reads from ENS
 * }
 */
app.post("/settle", async (req, res) => {
  const { bounty_id, winner, reward_usdc, payout_chain } = req.body;

  if (!bounty_id || !winner || !reward_usdc) {
    res.status(400).json({
      error: "Missing required fields: bounty_id, winner, reward_usdc",
    });
    return;
  }

  if (!RELAY_PRIVATE_KEY) {
    res.status(500).json({ error: "Relay wallet private key not configured" });
    return;
  }

  // Resolve payout chain: use provided value or read from ENS
  let resolvedChain = payout_chain || "";
  if (!resolvedChain && REGISTRY_ADDRESS) {
    try {
      resolvedChain = await getAgentPayoutChain(winner, REGISTRY_ADDRESS);
      console.log(
        `[Settle] Resolved payout chain from ENS for ${winner}: "${resolvedChain}"`,
      );
    } catch (err) {
      console.warn(`[Settle] Failed to read ENS payout chain:`, err);
    }
  }

  try {
    const result = await processSettlement(
      bounty_id,
      winner,
      reward_usdc,
      resolvedChain,
      RELAY_PRIVATE_KEY,
    );

    settlementResults.set(bounty_id, result);

    res.json({
      bounty_id: result.bountyId,
      winner: result.winner,
      reward_usdc: result.rewardUsdc,
      payout_chain: result.payoutChain,
      status: result.status,
      bridge: result.bridgeResult
        ? {
            bridge_id: result.bridgeResult.bridgeId,
            source_chain: result.bridgeResult.sourceChain,
            destination_chain: result.bridgeResult.destinationChain,
            steps: result.bridgeResult.steps,
          }
        : undefined,
      error: result.error,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: message });
  }
});

/**
 * Check bridge status by ID.
 */
app.get("/bridge/:id", (req, res) => {
  const result = bridgeResults.get(req.params.id);
  if (!result) {
    res.status(404).json({ error: "Bridge not found" });
    return;
  }
  res.json({
    bridge_id: result.bridgeId,
    status: result.success ? "complete" : "failed",
    source_chain: result.sourceChain,
    destination_chain: result.destinationChain,
    amount: result.amount,
    steps: result.steps,
    error: result.error,
  });
});

/**
 * Get settlement status by bounty ID.
 */
app.get("/settle/:bountyId", (req, res) => {
  const result = settlementResults.get(req.params.bountyId);
  if (!result) {
    res.status(404).json({ error: "Settlement not found" });
    return;
  }
  res.json(result);
});

/**
 * Estimate bridge fees.
 */
app.post("/estimate", async (req, res) => {
  const { amount, destination_chain } = req.body;
  const fees = await estimateBridgeFees(
    amount || "1.00",
    destination_chain || "base",
  );
  res.json({ fees });
});

/**
 * Read an agent's preferred payout chain from ENS.
 */
app.get("/payout-chain/:address", async (req, res) => {
  if (!REGISTRY_ADDRESS) {
    res.status(500).json({ error: "Registry address not configured" });
    return;
  }

  try {
    const chain = await getAgentPayoutChain(
      req.params.address,
      REGISTRY_ADDRESS,
    );
    const resolved = resolvePayoutChain(chain);
    res.json({
      address: req.params.address,
      payout_chain: chain,
      bridge_kit_chain: resolved || null,
      label: resolved ? CHAIN_LABELS[resolved] || resolved : null,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: message });
  }
});

// ── Start ──

app.listen(PORT, () => {
  console.log(`
╔══════════════════════════════════════════════════════════╗
║         OpenAudit Bridge Kit Service                     ║
║                                                          ║
║  Source chain:  Base Sepolia                              ║
║  USDC:          0x036CbD53842c5426634e7929541eC2318f3dCF7e║
║  Port:          ${PORT}                                       ║
║  Relay wallet:  ${RELAY_PRIVATE_KEY ? "configured ✓" : "NOT SET ✗"}                            ║
║  Registry:      ${REGISTRY_ADDRESS ? REGISTRY_ADDRESS.slice(0, 10) + "..." : "NOT SET ✗"}                        ║
╚══════════════════════════════════════════════════════════╝
  `);

  // Auto-watch for on-chain settlement events if configured
  if (RELAY_PRIVATE_KEY && REGISTRY_ADDRESS) {
    console.log("[Bridge] Starting BountySettlement event watcher...");
    watchSettlements(REGISTRY_ADDRESS, RELAY_PRIVATE_KEY, (result) => {
      console.log(
        `[Auto-settle] Bounty #${result.bountyId}: ${result.status}` +
          (result.error ? ` — ${result.error}` : ""),
      );
      settlementResults.set(result.bountyId, result);
    });
  } else {
    console.log(
      "[Bridge] Skipping event watcher (PAYOUT_RELAY_PRIVATE_KEY or REGISTRY_ADDRESS not set)",
    );
  }
});

export default app;
