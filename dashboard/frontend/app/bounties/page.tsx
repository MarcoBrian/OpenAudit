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
} from "wagmi";
import { formatUnits, parseUnits } from "viem";
import { CONTRACTS, CHAIN_LABELS, arcTestnet } from "../web3/config";
import { REGISTRY_ABI, ERC20_ABI } from "../web3/abi";
import {
  bridgePayout,
  getSupportedPayoutChains,
  type BridgeStatus,
} from "../web3/bridge";

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

// ── Main Page ──────────────────────────────────────────────────────────────

export default function BountiesPage() {
  const { isConnected } = useAccount();
  const [tab, setTab] = useState<"bounties" | "create" | "resolve">("bounties");

  return (
    <div className="container" style={{ minHeight: "80vh" }}>
      <header>
        <div className="brand">
          <Link
            href="/"
            className="title"
            style={{ textDecoration: "none", fontSize: "24px", color: "inherit" }}
          >
            OpenAudit
          </Link>
          <div className="status-pill">Bounty Settlement</div>
        </div>
        <div className="header-right">
          <ConnectKitButton />
        </div>
      </header>

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
        <button
          className={tab === "resolve" ? "" : "secondary"}
          onClick={() => setTab("resolve")}
        >
          Resolve &amp; Settle
        </button>
      </div>

      <main>
        {tab === "bounties" && <BountyList />}
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
        {tab === "resolve" && (
          <div className="card">
            <div className="section-title">Resolve Bounty</div>
            {isConnected ? (
              <ResolveBounty />
            ) : (
              <ConnectPrompt action="resolve bounties" />
            )}
          </div>
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

function BountyList() {
  const [bounties, setBounties] = useState<Bounty[]>([]);
  const [loading, setLoading] = useState(true);
  const client = usePublicClient();

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
          account: undefined,
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
    return <div className="muted text-center pt-10">Loading bounties...</div>;
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
            <div
              style={{ display: "flex", justifyContent: "space-between" }}
            >
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
            <div
              style={{ display: "flex", justifyContent: "space-between" }}
            >
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
            <div
              style={{ display: "flex", justifyContent: "space-between" }}
            >
              <span className="muted" style={{ fontSize: "0.9em" }}>
                Deadline
              </span>
              <span style={{ fontSize: "0.9em" }}>
                {new Date(Number(b.deadline) * 1000).toLocaleDateString()}
              </span>
            </div>
            {b.resolved && (
              <div
                style={{ display: "flex", justifyContent: "space-between" }}
              >
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
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Create Bounty ──────────────────────────────────────────────────────────

function CreateBounty() {
  const [target, setTarget] = useState("");
  const [rewardStr, setRewardStr] = useState("");
  const [daysFromNow, setDaysFromNow] = useState("7");
  const [step, setStep] = useState<"form" | "approving" | "creating" | "done">(
    "form",
  );

  const { writeContract: approve, data: approveTxHash } = useWriteContract();
  const { writeContract: create, data: createTxHash } = useWriteContract();

  const { isSuccess: approveConfirmed } = useWaitForTransactionReceipt({
    hash: approveTxHash,
  });
  const { isSuccess: createConfirmed } = useWaitForTransactionReceipt({
    hash: createTxHash,
  });

  useEffect(() => {
    if (approveConfirmed && step === "approving") {
      setStep("creating");
      const amount = parseUnits(rewardStr, 6);
      const deadline = BigInt(
        Math.floor(Date.now() / 1000) + Number(daysFromNow) * 86400,
      );
      create({
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "createBounty",
        args: [target as `0x${string}`, deadline, amount],
        chainId: arcTestnet.id,
      });
    }
  }, [approveConfirmed, step, rewardStr, daysFromNow, target, create]);

  useEffect(() => {
    if (createConfirmed && step === "creating") {
      setStep("done");
    }
  }, [createConfirmed, step]);

  const handleSubmit = () => {
    if (!target || !rewardStr || !daysFromNow) return;
    const amount = parseUnits(rewardStr, 6);
    setStep("approving");
    approve({
      address: CONTRACTS.USDC,
      abi: ERC20_ABI,
      functionName: "approve",
      chainId: arcTestnet.id,
      args: [CONTRACTS.REGISTRY, amount],
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
          style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.9em" }}
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
          style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.9em" }}
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
          style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.9em" }}
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
        {step === "approving"
          ? "Approving USDC..."
          : step === "creating"
            ? "Creating Bounty..."
            : "Approve & Create Bounty"}
      </button>
    </div>
  );
}

// ── Resolve Bounty ─────────────────────────────────────────────────────────

function ResolveBounty() {
  const [bountyIdStr, setBountyIdStr] = useState("");
  const [winnerAddr, setWinnerAddr] = useState("");
  const [score, setScore] = useState("80");
  const [step, setStep] = useState<"form" | "resolving" | "bridging" | "done">(
    "form",
  );
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>({
    state: "idle",
  });
  const [winnerPayoutChain, setWinnerPayoutChain] = useState("");
  const [resolvedReward, setResolvedReward] = useState<bigint>(0n);

  const client = usePublicClient();

  const { writeContract: resolve, data: resolveTxHash } = useWriteContract();
  const { isSuccess: resolveConfirmed } = useWaitForTransactionReceipt({
    hash: resolveTxHash,
  });

  // After resolution confirmed, start bridging
  useEffect(() => {
    if (resolveConfirmed && step === "resolving") {
      setStep("bridging");
      // Initiate bridge
      bridgePayout(
        {
          amount: formatUnits(resolvedReward, 6),
          recipientAddress: winnerAddr,
          payoutChain: winnerPayoutChain,
        },
        setBridgeStatus,
      ).then(() => {
        setStep("done");
      });
    }
  }, [resolveConfirmed, step, resolvedReward, winnerAddr, winnerPayoutChain]);

  const handleResolve = async () => {
    if (!bountyIdStr || !winnerAddr || !score || !client) return;
    setStep("resolving");

    const bountyId = BigInt(bountyIdStr);

    // Read bounty reward for bridge amount
    try {
      const data = await client.readContract({
        account: undefined,
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "bounties" as const,
        args: [bountyId],
      });
      const [, , reward] = data as [
        string,
        string,
        bigint,
        bigint,
        boolean,
        boolean,
        string,
      ];
      setResolvedReward(reward);
    } catch {
      // fallback
    }

    try {
      const agentId = await client.readContract({
        account: undefined,
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "ownerToAgentId" as const,
        args: [winnerAddr as `0x${string}`],
      });
      if (agentId && Number(agentId) > 0) {
        const chain = await client.readContract({
          account: undefined,
          address: CONTRACTS.REGISTRY,
          abi: REGISTRY_ABI,
          functionName: "getPayoutChain" as const,
          args: [agentId as bigint],
        });
        setWinnerPayoutChain(chain as string);
      }
    } catch {
      setWinnerPayoutChain("arc");
    }

    resolve({
      address: CONTRACTS.REGISTRY,
      abi: REGISTRY_ABI,
      functionName: "resolveBounty",
      args: [bountyId, winnerAddr as `0x${string}`, BigInt(score)],
    });
  };

  if (step === "done") {
    return (
      <div style={{ textAlign: "center", padding: "1rem" }}>
        <h3 style={{ color: "#16a34a", marginBottom: "0.5rem" }}>
          Bounty Settled!
        </h3>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          {resolvedReward > 0n
            ? `${formatUnits(resolvedReward, 6)} USDC`
            : "Reward"}{" "}
          {winnerPayoutChain && winnerPayoutChain !== "arc"
            ? `bridged to ${CHAIN_LABELS[winnerPayoutChain] || winnerPayoutChain}`
            : "settled on Arc"}
        </p>
        <button
          onClick={() => {
            setStep("form");
            setBountyIdStr("");
            setWinnerAddr("");
          }}
        >
          Resolve Another
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "500px" }}>
      <p className="muted" style={{ marginBottom: "1.5rem" }}>
        Pick the winning agent. USDC is released from Arc and bridged to the
        winner&apos;s preferred chain via Circle Bridge Kit (CCTP).
      </p>

      <div style={{ marginBottom: "1rem" }}>
        <label
          className="muted"
          style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.9em" }}
        >
          Bounty ID
        </label>
        <input
          type="number"
          placeholder="1"
          value={bountyIdStr}
          onChange={(e) => setBountyIdStr(e.target.value)}
          disabled={step !== "form"}
          min="1"
        />
      </div>
      <div style={{ marginBottom: "1rem" }}>
        <label
          className="muted"
          style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.9em" }}
        >
          Winner Address
        </label>
        <input
          type="text"
          placeholder="0x..."
          value={winnerAddr}
          onChange={(e) => setWinnerAddr(e.target.value)}
          disabled={step !== "form"}
        />
      </div>
      <div style={{ marginBottom: "1.5rem" }}>
        <label
          className="muted"
          style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.9em" }}
        >
          Reputation Score (0-100)
        </label>
        <input
          type="number"
          placeholder="80"
          value={score}
          onChange={(e) => setScore(e.target.value)}
          disabled={step !== "form"}
          min="0"
          max="100"
        />
      </div>

      <button
        onClick={handleResolve}
        disabled={step !== "form" || !bountyIdStr || !winnerAddr}
        style={{ width: "100%", marginBottom: "1.5rem" }}
      >
        {step === "resolving"
          ? "Resolving on-chain..."
          : step === "bridging"
            ? `Bridging USDC${winnerPayoutChain ? ` to ${CHAIN_LABELS[winnerPayoutChain] || winnerPayoutChain}` : ""}...`
            : "Resolve & Bridge Payout"}
      </button>

      {step !== "form" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <StatusStep
            label="Resolve on-chain"
            done={step !== "resolving"}
            active={step === "resolving"}
          />
          <StatusStep
            label="Read payout chain from ENS"
            done={step === "bridging" || step === "done"}
            active={step === "resolving"}
          />
          <StatusStep
            label={`Bridge USDC → ${CHAIN_LABELS[winnerPayoutChain] || winnerPayoutChain || "destination"}`}
            done={step === "done"}
            active={step === "bridging"}
          />
        </div>
      )}
    </div>
  );
}

// ── Status Step ────────────────────────────────────────────────────────────

function StatusStep({
  label,
  done,
  active,
}: {
  label: string;
  done: boolean;
  active: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        fontSize: "0.9rem",
        color: done ? "#16a34a" : active ? "#4c7dff" : "#9ca3af",
      }}
    >
      <span
        style={{
          width: "16px",
          height: "16px",
          borderRadius: "50%",
          background: done ? "#16a34a" : active ? "#4c7dff" : "#e5e7eb",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "10px",
          color: "#fff",
        }}
      >
        {done ? "✓" : active ? "" : ""}
      </span>
      <span>{label}</span>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function shortAddr(addr: string): string {
  if (!addr || addr.length < 10) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
