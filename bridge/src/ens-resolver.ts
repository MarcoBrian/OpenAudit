/**
 * ENS payout chain resolver.
 *
 * Reads an agent's preferred payout chain from their ENS subname text record
 * on the network where the OpenAudit contracts are deployed (Base Sepolia).
 */

import { createPublicClient, http, namehash } from "viem";
import { baseSepolia } from "viem/chains";

const ENS_RESOLVER_ABI = [
  {
    type: "function",
    name: "text",
    stateMutability: "view",
    inputs: [
      { name: "node", type: "bytes32" },
      { name: "key", type: "string" },
    ],
    outputs: [{ name: "", type: "string" }],
  },
] as const;

const REGISTRY_ABI = [
  {
    type: "function",
    name: "agents",
    inputs: [{ name: "agentId", type: "uint256" }],
    outputs: [
      { name: "owner", type: "address" },
      { name: "tba", type: "address" },
      { name: "name", type: "string" },
      { name: "metadataURI", type: "string" },
      { name: "totalScore", type: "uint256" },
      { name: "findingsCount", type: "uint256" },
      { name: "registered", type: "bool" },
    ],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "getPayoutChain",
    inputs: [{ name: "agentId", type: "uint256" }],
    outputs: [{ name: "", type: "string" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "ownerToAgentId",
    inputs: [{ name: "", type: "address" }],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "tbaToAgentId",
    inputs: [{ name: "", type: "address" }],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "agentENSNode",
    inputs: [{ name: "agentId", type: "uint256" }],
    outputs: [{ name: "", type: "bytes32" }],
    stateMutability: "view",
  },
] as const;

let _client: any = null;

function getClient(): any {
  if (!_client) {
    const rpcUrl =
      process.env.BASE_SEPOLIA_RPC_URL || process.env.RPC_URL || "";
    _client = createPublicClient({
      chain: baseSepolia,
      transport: http(rpcUrl || undefined),
    }) as any;
  }
  return _client;
}

/**
 * Read an agent's preferred payout chain from the on-chain registry.
 *
 * @param winnerAddress - The winner's address (owner or TBA)
 * @param registryAddress - The OpenAuditRegistry contract address
 * @returns The payout chain string (e.g. "base", "ethereum", "arbitrum") or empty string
 */
export async function getAgentPayoutChain(
  winnerAddress: string,
  registryAddress: string,
): Promise<string> {
  const client = getClient();
  const addr = winnerAddress as `0x${string}`;
  const registry = registryAddress as `0x${string}`;

  try {
    // Try to resolve agentId from owner address first
    let agentId = await client.readContract({
      address: registry,
      abi: REGISTRY_ABI,
      functionName: "ownerToAgentId",
      args: [addr],
    });

    // If not found as owner, try TBA
    if (agentId === 0n) {
      agentId = await client.readContract({
        address: registry,
        abi: REGISTRY_ABI,
        functionName: "tbaToAgentId",
        args: [addr],
      });
    }

    if (agentId === 0n) {
      console.warn(`No agent found for address ${winnerAddress}`);
      return "";
    }

    // Read payout chain from registry (which reads from ENS text record)
    const payoutChain = await client.readContract({
      address: registry,
      abi: REGISTRY_ABI,
      functionName: "getPayoutChain",
      args: [agentId],
    });

    return payoutChain;
  } catch (err) {
    console.error(
      `Failed to read payout chain for ${winnerAddress}:`,
      err instanceof Error ? err.message : err,
    );
    return "";
  }
}

/**
 * Get agent details from the registry.
 */
export async function getAgentDetails(
  agentId: bigint,
  registryAddress: string,
): Promise<{
  owner: string;
  tba: string;
  name: string;
  payoutChain: string;
} | null> {
  const client = getClient();
  const registry = registryAddress as `0x${string}`;

  try {
    const agent = await client.readContract({
      address: registry,
      abi: REGISTRY_ABI,
      functionName: "agents",
      args: [agentId],
    });

    if (!agent[6]) return null; // not registered

    const payoutChain = await client.readContract({
      address: registry,
      abi: REGISTRY_ABI,
      functionName: "getPayoutChain",
      args: [agentId],
    });

    return {
      owner: agent[0],
      tba: agent[1],
      name: agent[2],
      payoutChain,
    };
  } catch (err) {
    console.error(`Failed to read agent ${agentId}:`, err);
    return null;
  }
}
