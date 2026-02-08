"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { ConnectKitButton } from "connectkit";
import {
  useAccount,
  useReadContract,
  useWriteContract,
  useWaitForTransactionReceipt,
  usePublicClient,
  useSwitchChain,
} from "wagmi";
import { formatUnits, parseUnits } from "viem";
import { CONTRACTS, CHAIN_LABELS, HOME_CHAIN } from "../web3/config";
import { REGISTRY_ABI, ERC20_ABI } from "../web3/abi";
import {
  bridgePayout,
  getSupportedPayoutChains,
  type BridgeStatus,
} from "../web3/bridge";
import Loader from "../components/Loader";

// ── Types ──────────────────────────────────────────────────────────────────

interface Bounty {
  id: number;
  sponsor: string;
  targetContract: string;
  reward: bigint;
  deadline: bigint;
  active: boolean;
  resolved: boolean;
  winner: string;
}

interface Submission {
  agent: string;
  reportCID: string;
  submittedAt: bigint;
}

const GATEWAY = "https://gateway.pinata.cloud/ipfs/";

const MOCK_AGENT_ADDRESS = "0x71C7656EC7ab88b098defB751B7401B5f6d8976F";
const MOCK_BOUNTY_2_DATA = {
  title: "Predictable & miner\u2011controllable randomness",
  severity: "HIGH",
  confidence: 0.92,
  description:
    "The `flip` function derives the game outcome from `blockhash(block.number - 1)`. The block hash of the *previous* block is known to the miner who creates the current block and can be influenced through the ordering of transactions or by simply not including a transaction in a block. Consequently, a malicious miner (or a colluding validator) can choose a block hash that makes `side` equal to the attacker\u2019s `_guess`, guaranteeing a win every time.",
  impact:
    "An attacker controlling block production can always win the coin flip, causing the `consecutiveWins` counter to increase indefinitely. In a scenario where the contract is extended to reward successful streaks with ether or tokens, the attacker could drain the entire reward pool by repeatedly forcing wins. Even without a reward, the invariant that the game is fair is broken.",
  references: [
    {
      source: "Solodit",
      url: "https://solodit.cyfrin.io/api/v1/solodit/findings/m-2-nimbus-may-use-stale-metadata-information-after-fulu-fork-transition-sherlock-fusaka-upgrade-git",
      note: "Related research / similar cases: M-2: Nimbus may use stale metadata information after Fulu fork transition (MEDIUM, Sherlock)",
    },
  ],
  remediation:
    'Replace the insecure use of `blockhash` with a source of unbiased randomness, such as Chainlink VRF or a commit\u2011reveal scheme. Ensure the random value is generated after the user\u2019s guess is committed and cannot be influenced by block producers.\n```solidity\nimport "@chainlink/contracts/src/v0.8/VRFConsumerBase.sol";\n// ... use requestRandomness and fulfillRandomness to obtain a verifiable random number ...\n```',
  repro:
    "1. Deploy the contract on a testnet where you control the mining (e.g., Hardhat or Ganache with `evm_mine`).\n2. Craft two transactions in the same block: first a dummy transaction, then the `flip(true)` call.\n3. Because the block hash of the previous block is known, set the dummy transaction\u2019s gas price so the miner can reorder or omit the `flip` transaction until a block with a favorable hash is produced.\n4. When the miner mines a block whose `blockhash(block.number - 1)` yields `coinFlip == 1`, the call to `flip(true)` will always succeed, incrementing `consecutiveWins` without chance of failure.\n5. Repeat the process to grow `consecutiveWins` arbitrarily, demonstrating that the randomness is manipulable.",
  evidence: {
    static_tool: "aderyn+slither",
    raw_findings: ["incorrect-equality", "incorrect-equality"],
    file_path:
      "/var/folders/nm/2vjnv_cs2v3btf_wtll9p0v00000gn/T/bounty_source_kout96mm/0xF2566E44c06faDD9cCdF90826F93410e09684a4f.sol",
  },
};

// ── Main Page ──────────────────────────────────────────────────────────────

export default function BountiesPage() {
  const { isConnected } = useAccount();
  const [tab, setTab] = useState<"bounties" | "create">("bounties");
  const [selectedBounty, setSelectedBounty] = useState<Bounty | null>(null);

  // Clear selection when switching tabs
  useEffect(() => {
    setSelectedBounty(null);
  }, [tab]);

  return (
    <div className="container" style={{ minHeight: "80vh" }}>
      <header>
        <div className="brand">
          <Link
            href="/"
            className="title"
            style={{
              textDecoration: "none",
              fontSize: "24px",
              color: "inherit",
            }}
          >
            OpenAudit
          </Link>
          <div className="status-pill">Bounty Settlement</div>
        </div>
        <div className="header-right">
          <ConnectKitButton />
        </div>
      </header>

      {!selectedBounty && (
        <div className="row" style={{ marginBottom: "24px" }}>
          <button
            className={tab === "bounties" ? "" : "secondary"}
            onClick={() => setTab("bounties")}
          >
            Active Bounties
          </button>
          <button
            className={tab === "create" ? "" : "secondary"}
            onClick={() => setTab("create")}
          >
            Create Bounty
          </button>
        </div>
      )}

      <main>
        {selectedBounty ? (
          <BountyDetail
            bounty={selectedBounty}
            onBack={() => setSelectedBounty(null)}
          />
        ) : (
          <>
            {tab === "bounties" && (
              <BountyList onSelect={(b) => setSelectedBounty(b)} />
            )}
            {tab === "create" && (
              <div className="card">
                <div className="section-title">New Bounty</div>
                {isConnected ? (
                  <CreateBounty />
                ) : (
                  <ConnectPrompt action="create bounties" />
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

// ── Components ─────────────────────────────────────────────────────────────

function ConnectPrompt({ action }: { action: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "3rem",
        textAlign: "center",
      }}
    >
      <p className="muted" style={{ marginBottom: "1rem" }}>
        Connect your wallet to {action}.
      </p>
      <ConnectKitButton />
    </div>
  );
}

// ── Bounty List ────────────────────────────────────────────────────────────

function BountyList({ onSelect }: { onSelect: (b: Bounty) => void }) {
  const [bounties, setBounties] = useState<Bounty[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const client = usePublicClient({ chainId: HOME_CHAIN.id });

  const {
    data: nextBountyId,
    error: nextBountyError,
    isLoading: isNextBountyLoading,
  } = useReadContract({
    address: CONTRACTS.REGISTRY,
    abi: REGISTRY_ABI,
    functionName: "nextBountyId",
    chainId: HOME_CHAIN.id,
  });

  const loadBounties = useCallback(async () => {
    if (nextBountyId === undefined || !client) return;
    setLoading(true);
    setLoadError(null);
    const count = Number(nextBountyId);
    const results: Bounty[] = [];
    for (let i = 1; i < count; i++) {
      try {
        const data = await client.readContract({
          address: CONTRACTS.REGISTRY,
          abi: REGISTRY_ABI,
          functionName: "bounties" as const,
          args: [BigInt(i)],
        });
        const [
          sponsor,
          targetContract,
          reward,
          deadline,
          active,
          resolved,
          winner,
        ] = data as [string, string, bigint, bigint, boolean, boolean, string];
        results.push({
          id: i,
          sponsor,
          targetContract,
          reward,
          deadline,
          active,
          resolved,
          winner,
        });
      } catch {
        // skip
      }
    }

    // MOCK: Ensure bounty 2 exists for demo
    if (!results.find((b) => b.id === 2)) {
      results.push({
        id: 2,
        sponsor: "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        targetContract: "0xF2566E44c06faDD9cCdF90826F93410e09684a4f",
        reward: BigInt(5000000000), // 5000 USDC
        deadline: BigInt(Math.floor(Date.now() / 1000) + 86400 * 7),
        active: true,
        resolved: false,
        winner: "0x0000000000000000000000000000000000000000",
      });
    }

    setBounties(results);
    setLoading(false);
  }, [nextBountyId, client]);

  useEffect(() => {
    loadBounties();
  }, [loadBounties]);

  useEffect(() => {
    if (nextBountyError) {
      setLoadError("Failed to load bounties from the registry.");
      setLoading(false);
    } else if (!isNextBountyLoading && nextBountyId === undefined) {
      setLoadError("Registry data is unavailable on this network.");
      setLoading(false);
    }
  }, [nextBountyError, isNextBountyLoading, nextBountyId]);

  if (loading) {
    return (
      <div style={{ paddingTop: "4rem" }}>
        <Loader size="large" text="Fetching active bounties..." centered />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
        <p className="muted">{loadError}</p>
      </div>
    );
  }

  if (bounties.length === 0) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
        <p className="muted">No bounties yet. Create one to get started.</p>
      </div>
    );
  }

  return (
    <div className="grid">
      {bounties.map((b) => (
        <div key={b.id} className="card">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "1rem",
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: "1.1em" }}>#{b.id}</span>
            <span
              className="badge"
              style={{
                backgroundColor: b.resolved
                  ? "#dcfce7"
                  : b.active
                    ? "#e0e7ff"
                    : "#f3f4f6",
                color: b.resolved
                  ? "#166534"
                  : b.active
                    ? "#4338ca"
                    : "#374151",
              }}
            >
              {b.resolved ? "Resolved" : b.active ? "Active" : "Cancelled"}
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span className="muted" style={{ fontSize: "0.9em" }}>
                Reward
              </span>
              <span
                style={{
                  fontWeight: 600,
                  color: "#16a34a",
                  fontSize: "0.9em",
                }}
              >
                {formatUnits(b.reward, 6)} USDC
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span className="muted" style={{ fontSize: "0.9em" }}>
                Target
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "0.85em",
                }}
              >
                {shortAddr(b.targetContract)}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span className="muted" style={{ fontSize: "0.9em" }}>
                Deadline
              </span>
              <span style={{ fontSize: "0.9em" }}>
                {new Date(Number(b.deadline) * 1000).toLocaleDateString()}
              </span>
            </div>
            {b.resolved && (
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="muted" style={{ fontSize: "0.9em" }}>
                  Winner
                </span>
                <span
                  style={{
                    fontFamily: "monospace",
                    fontSize: "0.85em",
                  }}
                >
                  {shortAddr(b.winner)}
                </span>
              </div>
            )}
            <button
              style={{ marginTop: "1rem" }}
              className="secondary"
              onClick={() => onSelect(b)}
            >
              View Details & Submissions
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Bounty Detail ──────────────────────────────────────────────────────────

function BountyDetail({
  bounty,
  onBack,
}: {
  bounty: Bounty;
  onBack: () => void;
}) {
  const { address } = useAccount();
  const [submitters, setSubmitters] = useState<string[]>([]);
  const client = usePublicClient({ chainId: HOME_CHAIN.id });

  useEffect(() => {
    if (!client) return;
    client
      .readContract({
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "getBountySubmitters",
        args: [BigInt(bounty.id)],
      })
      .then((data) => {
        const list = (data as string[]) || [];
        // MOCK: Bounty 2 always has the mock agent
        if (
          bounty.id === 2 &&
          !list.some(
            (a) => a.toLowerCase() === MOCK_AGENT_ADDRESS.toLowerCase(),
          )
        ) {
          list.push(MOCK_AGENT_ADDRESS);
        }
        setSubmitters(list);
      })
      .catch(() => {
        // Fallback or error handling
        if (bounty.id === 2) {
          setSubmitters([MOCK_AGENT_ADDRESS]);
        } else {
          setSubmitters([]);
        }
      });
  }, [bounty.id, client]);

  const isSponsor =
    address && address.toLowerCase() === bounty.sponsor.toLowerCase();

  return (
    <div>
      <div style={{ marginBottom: "1rem" }}>
        <button className="secondary" onClick={onBack}>
          ← Back to List
        </button>
      </div>

      <div className="card" style={{ marginBottom: "2rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <h2>Bounty #{bounty.id}</h2>
          <span
            className="badge"
            style={{
              backgroundColor: bounty.resolved
                ? "#dcfce7"
                : bounty.active
                  ? "#e0e7ff"
                  : "#f3f4f6",
              color: bounty.resolved
                ? "#166534"
                : bounty.active
                  ? "#4338ca"
                  : "#374151",
            }}
          >
            {bounty.resolved
              ? "Resolved"
              : bounty.active
                ? "Active"
                : "Cancelled"}
          </span>
        </div>
        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div>
            <div className="muted" style={{ fontSize: "0.9em" }}>
              Target Contract
            </div>
            <div style={{ fontFamily: "monospace", marginBottom: "1rem" }}>
              {bounty.targetContract}
            </div>
            <div className="muted" style={{ fontSize: "0.9em" }}>
              Sponsor
            </div>
            <div style={{ fontFamily: "monospace" }}>{bounty.sponsor}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="muted" style={{ fontSize: "0.9em" }}>
              Reward
            </div>
            <div
              style={{
                fontSize: "1.5em",
                fontWeight: 600,
                color: "#16a34a",
                marginBottom: "1rem",
              }}
            >
              {formatUnits(bounty.reward, 6)} USDC
            </div>
            <div className="muted" style={{ fontSize: "0.9em" }}>
              Deadline
            </div>
            <div>
              {new Date(Number(bounty.deadline) * 1000).toLocaleDateString()}
            </div>
          </div>
        </div>
      </div>

      <h3 style={{ marginBottom: "1rem" }}>
        Submissions ({submitters.length})
      </h3>
      {submitters.length === 0 ? (
        <div className="card text-center muted">No submissions yet.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {submitters.map((agent) => (
            <SubmissionItem
              key={agent}
              agent={agent}
              bounty={bounty}
              isSponsor={!!isSponsor}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SubmissionItem({
  agent,
  bounty,
  isSponsor,
}: {
  agent: string;
  bounty: Bounty;
  isSponsor: boolean;
}) {
  const [finding, setFinding] = useState<Submission | null>(null);
  const client = usePublicClient({ chainId: HOME_CHAIN.id });
  const [expanded, setExpanded] = useState(false);
  const [reportData, setReportData] = useState<any>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [agentName, setAgentName] = useState<string | null>(null);

  // Resolution state
  const { address, chainId } = useAccount();
  const { switchChainAsync } = useSwitchChain();
  // ... existing code ...

  const [score, setScore] = useState("80");
  const [step, setStep] = useState<"idle" | "resolving" | "bridging" | "done">(
    "idle",
  );
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>({
    state: "idle",
  });
  const [winnerPayoutChain, setWinnerPayoutChain] = useState("");

  const { writeContract: resolve, data: resolveTxHash } = useWriteContract();
  const { isSuccess: resolveConfirmed } = useWaitForTransactionReceipt({
    hash: resolveTxHash,
  });

  useEffect(() => {
    if (!client) return;

    // 1. Fetch Finding
    if (
      bounty.id === 2 &&
      agent.toLowerCase() === MOCK_AGENT_ADDRESS.toLowerCase()
    ) {
      setFinding({
        agent: MOCK_AGENT_ADDRESS,
        reportCID: "Qm_MOCK_CID",
        submittedAt: BigInt(Math.floor(Date.now() / 1000) - 3600), // 1 hour ago
      });
      setAgentName("chaos_agent.openaudit.eth"); // Mock name
    } else {
      client
        .readContract({
          address: CONTRACTS.REGISTRY,
          abi: REGISTRY_ABI,
          functionName: "findings",
          args: [BigInt(bounty.id), agent as `0x${string}`],
        })
        .then((data) => {
          const [ag, reportCID, submittedAt] = data as [string, string, bigint];
          setFinding({ agent: ag, reportCID, submittedAt });
        });

      // 2. Resolve Agent Name (ENS)
      // Check ownerToAgentId then tbaToAgentId to get ID, then getAgent(id)
      const fetchAgentName = async () => {
        try {
          let agentId = await client.readContract({
            address: CONTRACTS.REGISTRY,
            abi: REGISTRY_ABI,
            functionName: "ownerToAgentId",
            args: [agent as `0x${string}`],
          });
          if (!agentId || agentId === 0n) {
            agentId = await client.readContract({
              address: CONTRACTS.REGISTRY,
              abi: REGISTRY_ABI,
              functionName: "tbaToAgentId",
              args: [agent as `0x${string}`],
            });
          }
          if (agentId && agentId > 0n) {
            const agentData = await client.readContract({
              address: CONTRACTS.REGISTRY,
              abi: REGISTRY_ABI,
              functionName: "getAgent",
              args: [agentId],
            });
            // agentData: [owner, tba, name, metadataURI, ...]
            if (agentData && agentData.name) {
              setAgentName(agentData.name + ".openaudit.eth");
            }
          }
        } catch (e) {
          console.error("Failed to resolve agent name", e);
        }
      };

      fetchAgentName();
    }
  }, [bounty.id, agent, client]);

  // Handle Bridging after resolution
  useEffect(() => {
    if (resolveConfirmed && step === "resolving") {
      setStep("bridging");
      bridgePayout(
        {
          amount: formatUnits(bounty.reward, 6),
          recipientAddress: agent,
          payoutChain: winnerPayoutChain,
        },
        setBridgeStatus,
      ).then(() => setStep("done"));
    }
  }, [resolveConfirmed, step, bounty.reward, agent, winnerPayoutChain]);

  const toggleReport = async () => {
    if (!expanded) {
      if (!reportData && finding?.reportCID) {
        // MOCK: Return local data for mock CID
        if (finding.reportCID === "Qm_MOCK_CID") {
          setReportData(MOCK_BOUNTY_2_DATA);
          setExpanded(true);
          return;
        }

        setLoadingReport(true);
        try {
          const res = await fetch(`${GATEWAY}${finding.reportCID}`);
          const json = await res.json();
          setReportData(json);
        } catch (e) {
          console.error("Failed to fetch report", e);
        }
        setLoadingReport(false);
      }
    }
    setExpanded(!expanded);
  };

  const handleResolve = async () => {
    // MOCK: Simulate resolution for mock agent
    if (agent.toLowerCase() === MOCK_AGENT_ADDRESS.toLowerCase()) {
      setStep("resolving");
      setTimeout(() => {
        setStep("bridging");
        bridgePayout(
          {
            amount: formatUnits(bounty.reward, 6),
            recipientAddress: agent,
            payoutChain: "base",
          },
          setBridgeStatus,
        ).then(() => setStep("done"));
      }, 2000);
      return;
    }

    if (!address || !client) return;
    if (chainId !== HOME_CHAIN.id) {
      await switchChainAsync({ chainId: HOME_CHAIN.id });
      return;
    }

    // Check payout chain
    try {
      const agentId = await client.readContract({
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "ownerToAgentId",
        args: [agent as `0x${string}`],
      });
      if (agentId && Number(agentId) > 0) {
        const chain = await client.readContract({
          address: CONTRACTS.REGISTRY,
          abi: REGISTRY_ABI,
          functionName: "getPayoutChain",
          args: [agentId as bigint],
        });
        setWinnerPayoutChain(chain as string);
      } else {
        setWinnerPayoutChain("base");
      }
    } catch {
      setWinnerPayoutChain("base");
    }

    setStep("resolving");
    resolve({
      address: CONTRACTS.REGISTRY,
      abi: REGISTRY_ABI,
      functionName: "resolveBounty",
      args: [BigInt(bounty.id), agent as `0x${string}`, BigInt(score)],
      chainId: HOME_CHAIN.id,
      account: address as `0x${string}`,
    });
  };

  if (!finding)
    return (
      <div className="card muted p-8">
        <Loader size="small" text="Loading finding details..." centered />
      </div>
    );

  return (
    <div
      className="card"
      style={{
        border: expanded ? "1px solid #4338ca" : "1px solid #e5e7eb",
        transition: "all 0.2s",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          {/* Avatar / Icon Placeholder */}
          <div
            style={{
              width: "40px",
              height: "40px",
              borderRadius: "50%",
              background: "linear-gradient(135deg, #6366f1 0%, #4338ca 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontWeight: "bold",
              fontSize: "1.2rem",
            }}
          >
            {(agentName ? agentName[0] : "A").toUpperCase()}
          </div>

          <div>
            <div
              style={{ fontWeight: 600, fontSize: "1.1rem", color: "#111827" }}
            >
              {agentName || shortAddr(finding.agent)}
            </div>
            <div
              className="muted"
              style={{
                fontSize: "0.85em",
                display: "flex",
                gap: "8px",
                alignItems: "center",
                marginTop: "4px",
              }}
            >
              <span>
                Submitted{" "}
                {new Date(
                  Number(finding.submittedAt) * 1000,
                ).toLocaleDateString()}
              </span>
              <span>•</span>
              <span style={{ fontFamily: "monospace" }}>
                {validationStatus(bounty, agent)}
              </span>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          {bounty.resolved &&
            bounty.winner.toLowerCase() === agent.toLowerCase() && (
              <span
                className="badge"
                style={{
                  background: "#dcfce7",
                  color: "#166534",
                  border: "1px solid #bbf7d0",
                  fontWeight: 600,
                  padding: "4px 12px",
                }}
              >
                🏆 WINNER
              </span>
            )}
          <button
            className={expanded ? "" : "secondary"}
            onClick={toggleReport}
            style={{ minWidth: "120px" }}
          >
            {expanded ? "Hide Report" : "🔎 View Report"}
          </button>
        </div>
      </div>

      {expanded && (
        <div
          style={{
            marginTop: "1.5rem",
            borderTop: "1px solid #f3f4f6",
            paddingTop: "1.5rem",
          }}
        >
          {loadingReport ? (
            <div className="p-4">
              <Loader size="small" text="Fetching IPFS content..." />
            </div>
          ) : reportData ? (
            <ReportViewer data={reportData} />
          ) : (
            <div className="muted">
              Could not load report data. CID: {finding.reportCID}
            </div>
          )}

          {/* Resolution UI for Sponsor */}
          {isSponsor && bounty.active && !bounty.resolved && (
            <div
              style={{
                marginTop: "2rem",
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: "8px",
                padding: "1.5rem",
              }}
            >
              <h4
                style={{
                  marginBottom: "1rem",
                  color: "#1e293b",
                  fontSize: "1rem",
                }}
              >
                Accept this Submission
              </h4>
              {step === "idle" ? (
                <div
                  style={{
                    display: "flex",
                    gap: "1rem",
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "4px",
                    }}
                  >
                    <label
                      className="muted"
                      style={{ fontSize: "0.85em", fontWeight: 500 }}
                    >
                      Reputation Score (0-100)
                    </label>
                    <input
                      type="number"
                      value={score}
                      onChange={(e) => setScore(e.target.value)}
                      min="0"
                      max="100"
                      style={{
                        width: "100px",
                        padding: "8px",
                        borderRadius: "6px",
                        border: "1px solid #cbd5e1",
                      }}
                    />
                  </div>

                  <div style={{ flex: 1 }}></div>

                  <button
                    onClick={handleResolve}
                    style={{
                      background: "#16a34a",
                      color: "#fff",
                      border: "none",
                      padding: "10px 20px",
                      borderRadius: "6px",
                      fontWeight: 600,
                      boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                    }}
                  >
                    Select as Winner ({formatUnits(bounty.reward, 6)} USDC)
                  </button>
                </div>
              ) : (
                <div className="muted">
                  {step === "resolving" && "Resolving on-chain..."}
                  {step === "bridging" && "Bridging payout..."}
                  {step === "done" && (
                    <span style={{ color: "#16a34a", fontWeight: "bold" }}>
                      Payment Settled! Bounty Closed.
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function validationStatus(bounty: Bounty, agent: string) {
  if (bounty.resolved) {
    if (bounty.winner.toLowerCase() === agent.toLowerCase()) return "Accepted";
    return "Rejected";
  }
  return "Pending Review";
}

function ReportViewer({ data }: { data: any }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ borderBottom: "1px solid #e5e7eb", paddingBottom: "1rem" }}>
        <h3
          style={{
            fontSize: "1.25rem",
            fontWeight: 700,
            color: "#111827",
            marginBottom: "0.5rem",
          }}
        >
          {data.title || "Untitled Finding"}
        </h3>
        <div style={{ display: "flex", gap: "8px" }}>
          {data.severity && (
            <span
              style={{
                background:
                  data.severity === "HIGH" || data.severity === "CRITICAL"
                    ? "#fee2e2"
                    : "#fef3c7",
                color:
                  data.severity === "HIGH" || data.severity === "CRITICAL"
                    ? "#991b1b"
                    : "#92400e",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "0.75rem",
                fontWeight: 700,
              }}
            >
              {data.severity}
            </span>
          )}
          {data.confidence && (
            <span
              style={{
                background: "#f3f4f6",
                color: "#374151",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "0.75rem",
                fontWeight: 600,
              }}
            >
              Confidence: {Math.round(data.confidence * 100)}%
            </span>
          )}
        </div>
      </div>

      {data.description && (
        <section>
          <h4
            style={{
              fontSize: "0.9rem",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "0.5rem",
            }}
          >
            Description
          </h4>
          <p style={{ lineHeight: "1.6", color: "#374151" }}>
            {data.description}
          </p>
        </section>
      )}

      {data.impact && (
        <section>
          <h4
            style={{
              fontSize: "0.9rem",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "0.5rem",
            }}
          >
            Impact
          </h4>
          <p style={{ lineHeight: "1.6", color: "#374151" }}>{data.impact}</p>
        </section>
      )}

      {data.remediation && (
        <section>
          <h4
            style={{
              fontSize: "0.9rem",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "0.5rem",
            }}
          >
            Remediation
          </h4>
          <div
            style={{
              background: "#f8fafc",
              padding: "1rem",
              borderRadius: "6px",
              fontFamily: "monospace",
              fontSize: "0.9em",
              overflowX: "auto",
            }}
          >
            {data.remediation}
          </div>
        </section>
      )}

      {data.repro && (
        <section>
          <h4
            style={{
              fontSize: "0.9rem",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "0.5rem",
            }}
          >
            Reproduction Steps
          </h4>
          <p
            style={{
              lineHeight: "1.6",
              color: "#374151",
              whiteSpace: "pre-wrap",
            }}
          >
            {data.repro}
          </p>
        </section>
      )}

      <section>
        <h4
          style={{
            fontSize: "0.9rem",
            color: "#6b7280",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            marginBottom: "0.5rem",
          }}
        >
          Raw Data
        </h4>
        <details>
          <summary
            style={{ cursor: "pointer", color: "#4f46e5", fontSize: "0.9em" }}
          >
            View complete JSON payload
          </summary>
          <pre
            style={{
              marginTop: "1rem",
              padding: "1rem",
              background: "#f1f5f9",
              borderRadius: "6px",
              overflowX: "auto",
              fontSize: "0.8em",
            }}
          >
            {JSON.stringify(data, null, 2)}
          </pre>
        </details>
      </section>
    </div>
  );
}

// ── Create Bounty ──────────────────────────────────────────────────────────

function CreateBounty() {
  const { address, chainId } = useAccount();
  const { switchChainAsync } = useSwitchChain();
  const [target, setTarget] = useState("");
  const [rewardStr, setRewardStr] = useState("");
  const [daysFromNow, setDaysFromNow] = useState("7");
  const [step, setStep] = useState<"form" | "approving" | "creating" | "done">(
    "form",
  );

  const {
    writeContract: approve,
    data: approveTxHash,
    error: approveError,
  } = useWriteContract();
  const {
    writeContract: create,
    data: createTxHash,
    error: createError,
  } = useWriteContract();

  const { data: usdcBalance } = useReadContract({
    address: CONTRACTS.USDC,
    abi: ERC20_ABI,
    functionName: "balanceOf",
    args: [address as `0x${string}`],
    chainId: HOME_CHAIN.id,
  });

  const { isSuccess: approveConfirmed, isLoading: isApproving } =
    useWaitForTransactionReceipt({
      hash: approveTxHash,
      chainId: HOME_CHAIN.id,
    });
  const { isSuccess: createConfirmed, isLoading: isCreating } =
    useWaitForTransactionReceipt({
      hash: createTxHash,
      chainId: HOME_CHAIN.id,
    });

  // Watch for approval success to trigger creation
  useEffect(() => {
    // Only trigger if we are in the 'approving' step and just got confirmed
    if (approveConfirmed && step === "approving") {
      console.log("Approval confirmed, moving to create step...");
      if (!address) return;

      const amount = parseUnits(rewardStr, 6);
      const deadline = BigInt(
        Math.floor(Date.now() / 1000) + Number(daysFromNow) * 86400,
      );

      // Advance step before calling write to prevent double-call
      setStep("creating");

      create(
        {
          address: CONTRACTS.REGISTRY,
          abi: REGISTRY_ABI,
          functionName: "createBounty",
          args: [target as `0x${string}`, deadline, amount],
          account: address as `0x${string}`,
          chainId: HOME_CHAIN.id,
        },
        {
          onError: (err) => {
            console.error("Failed to create bounty tx:", err);
            // If the user rejects the signature, we should go back to form or show error
            // setStep("form") is handled by the other useEffect checking createError
          },
        },
      );
    }
  }, [approveConfirmed, step, rewardStr, daysFromNow, target, create, address]);

  useEffect(() => {
    if (createConfirmed && step === "creating") {
      console.log("Bounty creation confirmed!");
      setStep("done");
    }
  }, [createConfirmed, step]);

  useEffect(() => {
    if (approveError || createError) {
      console.error("Contract write error:", approveError || createError);
      setStep("form");
    }
  }, [approveError, createError]);

  const handleSubmit = async () => {
    if (!address || !target || !rewardStr || !daysFromNow) return;
    if (chainId !== HOME_CHAIN.id) {
      await switchChainAsync({ chainId: HOME_CHAIN.id });
      return;
    }
    const amount = parseUnits(rewardStr, 6);

    if (usdcBalance !== undefined && amount > (usdcBalance as bigint)) {
      alert(
        "Insufficient USDC balance! Please get testnet USDC from the faucet.",
      );
      return;
    }

    setStep("approving");
    approve({
      address: CONTRACTS.USDC,
      abi: ERC20_ABI,
      functionName: "approve",
      args: [CONTRACTS.REGISTRY, amount],
      account: address as `0x${string}`,
      chainId: HOME_CHAIN.id,
    });
  };

  if (step === "done") {
    return (
      <div style={{ textAlign: "center", padding: "1rem" }}>
        <h3 style={{ color: "#16a34a", marginBottom: "0.5rem" }}>
          Bounty Created!
        </h3>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          USDC has been locked in the registry contract on {HOME_CHAIN.name}.
        </p>
        <button
          onClick={() => {
            setStep("form");
            setTarget("");
            setRewardStr("");
          }}
        >
          Create Another
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "500px" }}>
      <p className="muted" style={{ marginBottom: "1.5rem" }}>
        Fund a bounty with USDC on {HOME_CHAIN.name}. Agents submit findings,
        you pick the winner.
      </p>
      <div style={{ marginBottom: "1rem" }}>
        <label
          className="muted"
          style={{
            display: "block",
            marginBottom: "0.5rem",
            fontSize: "0.9em",
          }}
        >
          Target Contract Address
        </label>
        <input
          type="text"
          placeholder="0x..."
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          disabled={step !== "form"}
        />
      </div>
      <div style={{ marginBottom: "1rem" }}>
        <label
          className="muted"
          style={{
            display: "block",
            marginBottom: "0.5rem",
            fontSize: "0.9em",
          }}
        >
          Reward (USDC)
        </label>
        <input
          type="number"
          placeholder="1000"
          value={rewardStr}
          onChange={(e) => setRewardStr(e.target.value)}
          disabled={step !== "form"}
          min="1"
        />
        {usdcBalance !== undefined && (
          <div
            className="muted"
            style={{ fontSize: "0.8em", marginTop: "0.25rem" }}
          >
            Balance: {formatUnits(usdcBalance as bigint, 6)} USDC
          </div>
        )}
      </div>
      <div style={{ marginBottom: "1.5rem" }}>
        <label
          className="muted"
          style={{
            display: "block",
            marginBottom: "0.5rem",
            fontSize: "0.9em",
          }}
        >
          Deadline (days from now)
        </label>
        <input
          type="number"
          placeholder="7"
          value={daysFromNow}
          onChange={(e) => setDaysFromNow(e.target.value)}
          disabled={step !== "form"}
          min="1"
        />
      </div>
      <button
        onClick={handleSubmit}
        disabled={step !== "form" || !target || !rewardStr}
        style={{ width: "100%" }}
      >
        {step === "approving" ? (
          <div className="flex flex-col items-center">
            <div className="mb-2">
              <Loader size="small" />
            </div>
            <span>
              {isApproving
                ? "Waiting for Approval Receipt..."
                : "Please confirm Approval in wallet..."}
            </span>
          </div>
        ) : step === "creating" ? (
          <div className="flex flex-col items-center">
            <div className="mb-2">
              <Loader size="small" />
            </div>
            <span>
              {isCreating
                ? "Waiting for Creation Receipt..."
                : "Please confirm Bounty Creation in wallet..."}
            </span>
          </div>
        ) : (
          "Approve & Create Bounty"
        )}
      </button>

      {usdcBalance !== undefined &&
        parseUnits(rewardStr || "0", 6) > (usdcBalance as bigint) && (
          <div
            style={{
              marginTop: "1rem",
              padding: "0.75rem",
              backgroundColor: "#fff3cd",
              color: "#856404",
              borderRadius: "0.25rem",
              fontSize: "0.9em",
            }}
          >
            Warning: Insufficient USDC balance.{" "}
            <a
              href="https://faucet.circle.com/"
              target="_blank"
              rel="noopener noreferrer"
              style={{ textDecoration: "underline", color: "inherit" }}
            >
              Get testnet USDC here
            </a>
            .
          </div>
        )}

      {(approveError || createError) && (
        <div
          style={{ color: "#ef4444", fontSize: "0.85em", marginTop: "1rem" }}
        >
          Error: {(approveError || createError)?.message.slice(0, 100)}...
        </div>
      )}
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function shortAddr(addr: string): string {
  if (!addr || addr.length < 10) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
