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
import { CONTRACTS, CHAIN_LABELS, arcTestnet } from "../web3/config";
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
  const client = usePublicClient({ chainId: arcTestnet.id });

  const { data: nextBountyId } = useReadContract({
    address: CONTRACTS.REGISTRY,
    abi: REGISTRY_ABI,
    functionName: "nextBountyId",
  });

  const loadBounties = useCallback(async () => {
    if (!nextBountyId || !client) return;
    setLoading(true);
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
    setBounties(results);
    setLoading(false);
  }, [nextBountyId, client]);

  useEffect(() => {
    loadBounties();
  }, [loadBounties]);

  if (loading) {
    return (
      <div style={{ paddingTop: "4rem" }}>
        <Loader size="large" text="Fetching active bounties..." centered />
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
  const client = usePublicClient({ chainId: arcTestnet.id });

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
        setSubmitters((data as string[]) || []);
      })
      .catch(() => setSubmitters([]));
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
  const client = usePublicClient({ chainId: arcTestnet.id });
  const [expanded, setExpanded] = useState(false);
  const [reportData, setReportData] = useState<any>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  // Resolution state
  const { address, chainId } = useAccount();
  const { switchChainAsync } = useSwitchChain();
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
    if (!address || !client) return;
    if (chainId !== arcTestnet.id) {
      await switchChainAsync({ chainId: arcTestnet.id });
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
        setWinnerPayoutChain("arc");
      }
    } catch {
      setWinnerPayoutChain("arc");
    }

    setStep("resolving");
    resolve({
      address: CONTRACTS.REGISTRY,
      abi: REGISTRY_ABI,
      functionName: "resolveBounty",
      args: [BigInt(bounty.id), agent as `0x${string}`, BigInt(score)],
      chainId: arcTestnet.id,
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
    <div className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div>
          <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
            Agent: {shortAddr(finding.agent)}
          </div>
          <div className="muted" style={{ fontSize: "0.85em" }}>
            Submitted:{" "}
            {new Date(Number(finding.submittedAt) * 1000).toLocaleString()}
          </div>
        </div>
        <div>
          {bounty.resolved &&
            bounty.winner.toLowerCase() === agent.toLowerCase() && (
              <span
                className="badge"
                style={{
                  background: "#dcfce7",
                  color: "#166534",
                  marginRight: "1rem",
                }}
              >
                WINNER
              </span>
            )}
          <button className="secondary" onClick={toggleReport}>
            {expanded ? "Hide Report" : "Read Report"}
          </button>
        </div>
      </div>

      {expanded && (
        <div
          style={{
            marginTop: "1rem",
            padding: "1rem",
            background: "#111",
            borderRadius: "8px",
            border: "1px solid #333",
            overflowX: "auto",
          }}
        >
          {loadingReport ? (
            <div className="p-4">
              <Loader size="small" text="Fetching IPFS content..." />
            </div>
          ) : reportData ? (
            <pre style={{ margin: 0, fontSize: "0.85em", color: "#ccc" }}>
              {JSON.stringify(reportData, null, 2)}
            </pre>
          ) : (
            <div className="muted">
              Could not load report data. CID: {finding.reportCID}
            </div>
          )}

          {/* Resolution UI for Sponsor */}
          {isSponsor && bounty.active && !bounty.resolved && (
            <div
              style={{
                marginTop: "1.5rem",
                borderTop: "1px solid #333",
                paddingTop: "1rem",
              }}
            >
              <h4 style={{ marginBottom: "0.5rem" }}>Accept this Submission</h4>
              {step === "idle" ? (
                <div
                  style={{ display: "flex", gap: "1rem", alignItems: "center" }}
                >
                  <label className="muted" style={{ fontSize: "0.9em" }}>
                    Score (0-100):
                  </label>
                  <input
                    type="number"
                    value={score}
                    onChange={(e) => setScore(e.target.value)}
                    min="0"
                    max="100"
                    style={{ width: "80px", padding: "4px" }}
                  />
                  <button
                    onClick={handleResolve}
                    style={{
                      background: "#16a34a",
                      color: "#fff",
                      border: "none",
                    }}
                  >
                    Win & Pay {formatUnits(bounty.reward, 6)} USDC
                  </button>
                </div>
              ) : (
                <div className="muted">
                  {step === "resolving" && "Resolving on-chain..."}
                  {step === "bridging" && "Bridging payout..."}
                  {step === "done" && (
                    <span style={{ color: "#16a34a" }}>
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

  const { isSuccess: approveConfirmed, isLoading: isApproving } =
    useWaitForTransactionReceipt({
      hash: approveTxHash,
      chainId: arcTestnet.id,
    });
  const { isSuccess: createConfirmed, isLoading: isCreating } =
    useWaitForTransactionReceipt({
      hash: createTxHash,
      chainId: arcTestnet.id,
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
          chainId: arcTestnet.id,
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
    if (chainId !== arcTestnet.id) {
      await switchChainAsync({ chainId: arcTestnet.id });
      return;
    }
    const amount = parseUnits(rewardStr, 6);
    setStep("approving");
    approve({
      address: CONTRACTS.USDC,
      abi: ERC20_ABI,
      functionName: "approve",
      args: [CONTRACTS.REGISTRY, amount],
      account: address as `0x${string}`,
      chainId: arcTestnet.id,
    });
  };

  if (step === "done") {
    return (
      <div style={{ textAlign: "center", padding: "1rem" }}>
        <h3 style={{ color: "#16a34a", marginBottom: "0.5rem" }}>
          Bounty Created!
        </h3>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          USDC has been locked in the registry contract on Arc.
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
        Fund a bounty with USDC on Arc. Agents submit findings, you pick the
        winner.
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
