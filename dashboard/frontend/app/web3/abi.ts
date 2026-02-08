/** OpenAuditRegistry ABI – only the functions we call from the frontend */
export const REGISTRY_ABI = [
  // ── Read functions ──
  {
    type: "function",
    name: "bounties",
    inputs: [{ name: "bountyId", type: "uint256" }],
    outputs: [
      { name: "sponsor", type: "address" },
      { name: "targetContract", type: "address" },
      { name: "reward", type: "uint256" },
      { name: "deadline", type: "uint256" },
      { name: "active", type: "bool" },
      { name: "resolved", type: "bool" },
      { name: "winner", type: "address" },
    ],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "nextBountyId",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "nextAgentId",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
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
    name: "getAgent",
    inputs: [{ name: "agentId", type: "uint256" }],
    outputs: [
      {
        name: "",
        type: "tuple",
        components: [
          { name: "owner", type: "address" },
          { name: "tba", type: "address" },
          { name: "name", type: "string" },
          { name: "metadataURI", type: "string" },
          { name: "totalScore", type: "uint256" },
          { name: "findingsCount", type: "uint256" },
          { name: "registered", type: "bool" },
        ],
      },
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
    name: "getBountySubmitters",
    inputs: [{ name: "bountyId", type: "uint256" }],
    outputs: [{ name: "", type: "address[]" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "getReputation",
    inputs: [{ name: "agent", type: "address" }],
    outputs: [
      { name: "totalScore", type: "uint256" },
      { name: "findingsCount", type: "uint256" },
      { name: "avgScore", type: "uint256" },
    ],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "isRegistered",
    inputs: [{ name: "addr", type: "address" }],
    outputs: [{ name: "", type: "bool" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "resolveName",
    inputs: [{ name: "name", type: "string" }],
    outputs: [{ name: "", type: "address" }],
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
    name: "findings",
    inputs: [
      { name: "bountyId", type: "uint256" },
      { name: "agent", type: "address" },
    ],
    outputs: [
      { name: "agent", type: "address" },
      { name: "reportCID", type: "string" },
      { name: "submittedAt", type: "uint256" },
    ],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "usdc",
    inputs: [],
    outputs: [{ name: "", type: "address" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "payoutRelay",
    inputs: [],
    outputs: [{ name: "", type: "address" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "MIN_REWARD",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },

  // ── Write functions ──
  {
    type: "function",
    name: "createBounty",
    inputs: [
      { name: "targetContract", type: "address" },
      { name: "deadline", type: "uint256" },
      { name: "rewardAmount", type: "uint256" },
    ],
    outputs: [{ name: "bountyId", type: "uint256" }],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "cancelBounty",
    inputs: [{ name: "bountyId", type: "uint256" }],
    outputs: [],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "registerAgent",
    inputs: [
      { name: "name", type: "string" },
      { name: "metadataURI", type: "string" },
      { name: "payoutChain", type: "string" },
    ],
    outputs: [
      { name: "agentId", type: "uint256" },
      { name: "tba", type: "address" },
    ],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "setPayoutChain",
    inputs: [
      { name: "agentId", type: "uint256" },
      { name: "chain", type: "string" },
    ],
    outputs: [],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "submitFinding",
    inputs: [
      { name: "bountyId", type: "uint256" },
      { name: "reportCID", type: "string" },
    ],
    outputs: [],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "resolveBounty",
    inputs: [
      { name: "bountyId", type: "uint256" },
      { name: "winner", type: "address" },
      { name: "reputationScore", type: "uint256" },
    ],
    outputs: [],
    stateMutability: "nonpayable",
  },

  // ── Events ──
  {
    type: "event",
    name: "BountyCreated",
    inputs: [
      { name: "bountyId", type: "uint256", indexed: true },
      { name: "sponsor", type: "address", indexed: true },
      { name: "reward", type: "uint256", indexed: false },
      { name: "deadline", type: "uint256", indexed: false },
    ],
  },
  {
    type: "event",
    name: "BountyResolved",
    inputs: [
      { name: "bountyId", type: "uint256", indexed: true },
      { name: "winner", type: "address", indexed: true },
      { name: "reward", type: "uint256", indexed: false },
    ],
  },
  {
    type: "event",
    name: "BountySettlement",
    inputs: [
      { name: "bountyId", type: "uint256", indexed: true },
      { name: "winner", type: "address", indexed: true },
      { name: "reward", type: "uint256", indexed: false },
      { name: "payoutChain", type: "string", indexed: false },
    ],
  },
  {
    type: "event",
    name: "BountyCancelled",
    inputs: [{ name: "bountyId", type: "uint256", indexed: true }],
  },
  {
    type: "event",
    name: "AgentRegistered",
    inputs: [
      { name: "agentId", type: "uint256", indexed: true },
      { name: "owner", type: "address", indexed: true },
      { name: "tba", type: "address", indexed: true },
      { name: "name", type: "string", indexed: false },
    ],
  },
] as const;

/** Minimal ERC-20 ABI for USDC approve + balanceOf */
export const ERC20_ABI = [
  {
    type: "function",
    name: "approve",
    inputs: [
      { name: "spender", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
    stateMutability: "nonpayable",
  },
  {
    type: "function",
    name: "balanceOf",
    inputs: [{ name: "account", type: "address" }],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "allowance",
    inputs: [
      { name: "owner", type: "address" },
      { name: "spender", type: "address" },
    ],
    outputs: [{ name: "", type: "uint256" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "decimals",
    inputs: [],
    outputs: [{ name: "", type: "uint8" }],
    stateMutability: "view",
  },
  {
    type: "function",
    name: "symbol",
    inputs: [],
    outputs: [{ name: "", type: "string" }],
    stateMutability: "view",
  },
] as const;
