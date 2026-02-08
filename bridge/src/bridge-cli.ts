/**
 * CLI tool for manually triggering a bridge or settlement.
 *
 * Usage:
 *   npm run bridge -- --bounty 1 --winner 0x... --amount 100.00 --chain ethereum
 *   npm run bridge -- --bridge --amount 10.00 --recipient 0x... --chain arbitrum
 */

import { processSettlement } from "./settlement.js";
import { executeBridge } from "./bridger.js";
import { PAYOUT_CHAIN_MAP, CHAIN_LABELS } from "./chains.js";

async function main() {
  const args = process.argv.slice(2);

  if (args.includes("--help") || args.length === 0) {
    console.log(`
OpenAudit Bridge CLI

Settlement mode (reads ENS payout chain):
  npm run bridge -- --bounty <id> --winner <addr> --amount <usdc> [--chain <chain>]

Direct bridge mode:
  npm run bridge -- --bridge --amount <usdc> --recipient <addr> --chain <chain>

List supported chains:
  npm run bridge -- --chains

Options:
  --bounty <id>       Bounty ID for settlement
  --winner <addr>     Winner's address
  --amount <usdc>     USDC amount (e.g. "100.00")
  --chain <chain>     Destination chain (e.g. "ethereum", "arbitrum", "arc")
  --recipient <addr>  Recipient address (bridge mode)
  --bridge            Direct bridge mode (no settlement logic)
  --chains            List supported chains
    `);
    return;
  }

  if (args.includes("--chains")) {
    console.log("\nSupported payout chains:");
    const seen = new Set<string>();
    for (const [key, bridgeKitName] of Object.entries(PAYOUT_CHAIN_MAP)) {
      if (!seen.has(bridgeKitName)) {
        seen.add(bridgeKitName);
        console.log(
          `  ${key.padEnd(20)} → ${CHAIN_LABELS[bridgeKitName] || bridgeKitName}`,
        );
      }
    }
    return;
  }

  const relayKey = process.env.PAYOUT_RELAY_PRIVATE_KEY;
  if (!relayKey) {
    console.error("Error: PAYOUT_RELAY_PRIVATE_KEY not set");
    process.exit(1);
  }

  const getArg = (flag: string): string => {
    const idx = args.indexOf(flag);
    return idx !== -1 && idx + 1 < args.length ? args[idx + 1] : "";
  };

  if (args.includes("--bridge")) {
    // Direct bridge mode
    const amount = getArg("--amount");
    const recipient = getArg("--recipient");
    const chain = getArg("--chain");

    if (!amount || !recipient || !chain) {
      console.error("Error: --amount, --recipient, and --chain are required");
      process.exit(1);
    }

    console.log(`Bridging ${amount} USDC → ${chain} for ${recipient}...`);
    const result = await executeBridge(
      { amount, recipient, destinationChain: chain },
      relayKey,
    );
    console.log(JSON.stringify(result, null, 2));
  } else {
    // Settlement mode
    const bountyId = getArg("--bounty");
    const winner = getArg("--winner");
    const amount = getArg("--amount");
    const chain = getArg("--chain");

    if (!bountyId || !winner || !amount) {
      console.error("Error: --bounty, --winner, and --amount are required");
      process.exit(1);
    }

    console.log(
      `Processing settlement for bounty #${bountyId}: ${amount} USDC → ${winner}...`,
    );
    const result = await processSettlement(
      bountyId,
      winner,
      amount,
      chain,
      relayKey,
    );
    console.log(JSON.stringify(result, null, 2));
  }
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
