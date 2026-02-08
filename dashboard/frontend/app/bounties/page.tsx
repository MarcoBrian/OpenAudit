"use client";

import { useState, useEffect, useCallback } from "react";
import { ConnectKitButton } from "connectkit";
import {
  useAccount,
  useReadContract,
  useWriteContract,
  useWaitForTransactionReceipt,
  usePublicClient,
} from "wagmi";
import { formatUnits, parseUnits } from "viem";
import { CONTRACTS, CHAIN_LABELS } from "../web3/config";
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
  const { address, isConnected } = useAccount();
  const [tab, setTab] = useState<"bounties" | "create" | "resolve">("bounties");

  return (
    <div className="bounties-page">
      <header className="bounties-header">
        <div className="header-left">
          <a href="/" className="back-link">
            &larr; Audit Runner
          </a>
          <h1>Bounty Settlement</h1>
          <span className="subtitle">USDC on Arc &bull; Cross-Chain Payouts</span>
        </div>
        <ConnectKitButton />
      </header>

      <nav className="tab-bar">
        <button
          className={tab === "bounties" ? "tab active" : "tab"}
          onClick={() => setTab("bounties")}
        >
          Active Bounties
        </button>
        <button
          className={tab === "create" ? "tab active" : "tab"}
          onClick={() => setTab("create")}
        >
          Create Bounty
        </button>
        <button
          className={tab === "resolve" ? "tab active" : "tab"}
          onClick={() => setTab("resolve")}
        >
          Resolve &amp; Settle
        </button>
      </nav>

      <main className="bounties-content">
        {tab === "bounties" && <BountyList />}
        {tab === "create" && (
          isConnected ? <CreateBounty /> : <ConnectPrompt action="create bounties" />
        )}
        {tab === "resolve" && (
          isConnected ? <ResolveBounty /> : <ConnectPrompt action="resolve bounties" />
        )}
      </main>

      <style jsx>{`
        .bounties-page {
          min-height: 100vh;
          background: #0a0a0f;
          color: #e0e0e0;
          font-family: "Montserrat", sans-serif;
          padding: 2rem;
          max-width: 960px;
          margin: 0 auto;
        }
        .bounties-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 2rem;
          gap: 1rem;
          flex-wrap: wrap;
        }
        .header-left { display: flex; flex-direction: column; gap: 0.25rem; }
        .back-link {
          color: #888;
          text-decoration: none;
          font-size: 0.85rem;
        }
        .back-link:hover { color: #aaa; }
        h1 { margin: 0; font-size: 1.8rem; }
        .subtitle { color: #6366f1; font-size: 0.85rem; font-weight: 500; }
        .tab-bar {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 2rem;
          border-bottom: 1px solid #222;
          padding-bottom: 0.5rem;
        }
        .tab {
          background: none;
          border: none;
          color: #888;
          cursor: pointer;
          padding: 0.5rem 1rem;
          font-size: 0.9rem;
          font-family: inherit;
          border-radius: 6px;
          transition: all 0.2s;
        }
        .tab:hover { color: #ccc; background: #151520; }
        .tab.active { color: #fff; background: #1a1a2e; }
        .bounties-content { min-height: 400px; }
      `}</style>
    </div>
  );
}

// ── Components ─────────────────────────────────────────────────────────────

function ConnectPrompt({ action }: { action: string }) {
  return (
    <div className="connect-prompt">
      <p>Connect your wallet to {action}.</p>
      <ConnectKitButton />
      <style jsx>{`
        .connect-prompt {
          text-align: center;
          padding: 3rem;
          background: #111118;
          border-radius: 12px;
          border: 1px solid #222;
        }
        p { color: #888; margin-bottom: 1rem; }
      `}</style>
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
          address: CONTRACTS.REGISTRY,
          abi: REGISTRY_ABI,
          functionName: "bounties",
          args: [BigInt(i)],
        });
        const [sponsor, targetContract, reward, deadline, active, resolved, winner] =
          data as [string, string, bigint, bigint, boolean, boolean, string];
        results.push({ id: i, sponsor, targetContract, reward, deadline, active, resolved, winner });
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
    return <div className="loading">Loading bounties...</div>;
  }

  if (bounties.length === 0) {
    return (
      <div className="empty">
        <p>No bounties yet. Create one to get started.</p>
        <style jsx>{`
          .empty { text-align: center; padding: 3rem; color: #666; }
        `}</style>
      </div>
    );
  }

  return (
    <div className="bounty-list">
      {bounties.map((b) => (
        <div key={b.id} className={`bounty-card ${b.resolved ? "resolved" : b.active ? "active" : "cancelled"}`}>
          <div className="bounty-top">
            <span className="bounty-id">#{b.id}</span>
            <span className={`status ${b.resolved ? "resolved" : b.active ? "active" : "cancelled"}`}>
              {b.resolved ? "Resolved" : b.active ? "Active" : "Cancelled"}
            </span>
          </div>
          <div className="bounty-info">
            <div className="info-row">
              <span className="label">Reward</span>
              <span className="value usdc">{formatUnits(b.reward, 6)} USDC</span>
            </div>
            <div className="info-row">
              <span className="label">Target</span>
              <span className="value mono">{shortAddr(b.targetContract)}</span>
            </div>
            <div className="info-row">
              <span className="label">Sponsor</span>
              <span className="value mono">{shortAddr(b.sponsor)}</span>
            </div>
            <div className="info-row">
              <span className="label">Deadline</span>
              <span className="value">{new Date(Number(b.deadline) * 1000).toLocaleDateString()}</span>
            </div>
            {b.resolved && (
              <div className="info-row">
                <span className="label">Winner</span>
                <span className="value mono">{shortAddr(b.winner)}</span>
              </div>
            )}
          </div>
        </div>
      ))}
      <style jsx>{`
        .bounty-list { display: flex; flex-direction: column; gap: 1rem; }
        .bounty-card {
          background: #111118;
          border: 1px solid #222;
          border-radius: 12px;
          padding: 1.25rem;
          transition: border-color 0.2s;
        }
        .bounty-card:hover { border-color: #333; }
        .bounty-card.resolved { border-left: 3px solid #22c55e; }
        .bounty-card.active { border-left: 3px solid #6366f1; }
        .bounty-card.cancelled { border-left: 3px solid #666; }
        .bounty-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
        .bounty-id { font-weight: 700; font-size: 1.1rem; }
        .status {
          font-size: 0.75rem;
          font-weight: 600;
          padding: 0.2rem 0.6rem;
          border-radius: 99px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .status.active { background: #1e1b4b; color: #818cf8; }
        .status.resolved { background: #052e16; color: #4ade80; }
        .status.cancelled { background: #1a1a1a; color: #888; }
        .bounty-info { display: flex; flex-direction: column; gap: 0.4rem; }
        .info-row { display: flex; justify-content: space-between; }
        .label { color: #666; font-size: 0.85rem; }
        .value { font-size: 0.85rem; }
        .value.usdc { color: #22c55e; font-weight: 600; }
        .value.mono { font-family: monospace; font-size: 0.8rem; }
        .loading { text-align: center; padding: 3rem; color: #666; }
      `}</style>
    </div>
  );
}

// ── Create Bounty ──────────────────────────────────────────────────────────

function CreateBounty() {
  const { address } = useAccount();
  const [target, setTarget] = useState("");
  const [rewardStr, setRewardStr] = useState("");
  const [daysFromNow, setDaysFromNow] = useState("7");
  const [step, setStep] = useState<"form" | "approving" | "creating" | "done">("form");

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
      const deadline = BigInt(Math.floor(Date.now() / 1000) + Number(daysFromNow) * 86400);
      create({
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "createBounty",
        args: [target as `0x${string}`, deadline, amount],
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
      args: [CONTRACTS.REGISTRY, amount],
    });
  };

  if (step === "done") {
    return (
      <div className="success-card">
        <h3>Bounty Created!</h3>
        <p>USDC has been locked in the registry contract on Arc.</p>
        <p className="tx-hash">
          Tx: <code>{createTxHash ? shortAddr(createTxHash) : "—"}</code>
        </p>
        <button className="btn" onClick={() => { setStep("form"); setTarget(""); setRewardStr(""); }}>
          Create Another
        </button>
        <style jsx>{`
          .success-card {
            background: #052e16;
            border: 1px solid #166534;
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
          }
          h3 { color: #4ade80; margin: 0 0 0.5rem; }
          p { color: #a3e5b7; margin: 0.25rem 0; }
          .tx-hash { font-size: 0.8rem; }
          code { color: #86efac; }
          .btn {
            margin-top: 1rem;
            background: #1e1b4b;
            color: #818cf8;
            border: 1px solid #312e81;
            padding: 0.5rem 1.25rem;
            border-radius: 8px;
            cursor: pointer;
            font-family: inherit;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="create-form">
      <h3>Create USDC Bounty</h3>
      <p className="desc">Fund a bounty with USDC on Arc. Agents submit findings, you pick the winner.</p>
      <div className="field">
        <label>Target Contract Address</label>
        <input
          type="text"
          placeholder="0x..."
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          disabled={step !== "form"}
        />
      </div>
      <div className="field">
        <label>Reward (USDC)</label>
        <input
          type="number"
          placeholder="1000"
          value={rewardStr}
          onChange={(e) => setRewardStr(e.target.value)}
          disabled={step !== "form"}
          min="1"
          step="0.01"
        />
      </div>
      <div className="field">
        <label>Deadline (days from now)</label>
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
        className="btn-primary"
        onClick={handleSubmit}
        disabled={step !== "form" || !target || !rewardStr}
      >
        {step === "approving"
          ? "Approving USDC..."
          : step === "creating"
          ? "Creating Bounty..."
          : "Approve & Create Bounty"}
      </button>

      <style jsx>{`
        .create-form {
          background: #111118;
          border: 1px solid #222;
          border-radius: 12px;
          padding: 2rem;
        }
        h3 { margin: 0 0 0.25rem; }
        .desc { color: #888; font-size: 0.85rem; margin: 0 0 1.5rem; }
        .field { margin-bottom: 1rem; }
        label { display: block; color: #888; font-size: 0.8rem; margin-bottom: 0.3rem; }
        input {
          width: 100%;
          background: #0a0a0f;
          border: 1px solid #333;
          border-radius: 8px;
          color: #e0e0e0;
          padding: 0.6rem 0.75rem;
          font-family: monospace;
          font-size: 0.9rem;
          outline: none;
          box-sizing: border-box;
        }
        input:focus { border-color: #6366f1; }
        input:disabled { opacity: 0.5; }
        .btn-primary {
          width: 100%;
          background: #6366f1;
          color: #fff;
          border: none;
          padding: 0.75rem;
          border-radius: 8px;
          font-family: inherit;
          font-size: 0.95rem;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.2s;
        }
        .btn-primary:hover:not(:disabled) { background: #4f46e5; }
        .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
      `}</style>
    </div>
  );
}

// ── Resolve Bounty ─────────────────────────────────────────────────────────

function ResolveBounty() {
  const { address } = useAccount();
  const [bountyIdStr, setBountyIdStr] = useState("");
  const [winnerAddr, setWinnerAddr] = useState("");
  const [score, setScore] = useState("80");
  const [step, setStep] = useState<"form" | "resolving" | "bridging" | "done">("form");
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>({ state: "idle" });
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
        setBridgeStatus
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
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "bounties",
        args: [bountyId],
      });
      const [, , reward] = data as [string, string, bigint, bigint, boolean, boolean, string];
      setResolvedReward(reward);
    } catch {
      // fallback
    }

    // Read winner's payout chain from agent
    try {
      // Get agentId from winner address
      const agentId = await client.readContract({
        address: CONTRACTS.REGISTRY,
        abi: REGISTRY_ABI,
        functionName: "ownerToAgentId",
        args: [winnerAddr as `0x${string}`],
      });
      if (agentId && Number(agentId) > 0) {
        const chain = await client.readContract({
          address: CONTRACTS.REGISTRY,
          abi: REGISTRY_ABI,
          functionName: "getPayoutChain",
          args: [agentId as bigint],
        });
        setWinnerPayoutChain(chain as string);
      }
    } catch {
      // If we can't read payout chain, default to arc (same chain)
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
      <div className="success-card">
        <h3>Bounty Settled!</h3>
        <p>
          {resolvedReward > 0n ? `${formatUnits(resolvedReward, 6)} USDC` : "Reward"}{" "}
          {winnerPayoutChain && winnerPayoutChain !== "arc"
            ? `bridged to ${CHAIN_LABELS[winnerPayoutChain] || winnerPayoutChain}`
            : "settled on Arc"}
        </p>
        <p className="winner">
          Winner: <code>{shortAddr(winnerAddr)}</code>
        </p>
        {bridgeStatus.state === "complete" && "destTxHash" in bridgeStatus && bridgeStatus.destTxHash && (
          <p className="tx-hash">
            Destination Tx: <code>{shortAddr(bridgeStatus.destTxHash)}</code>
          </p>
        )}
        <button className="btn" onClick={() => { setStep("form"); setBountyIdStr(""); setWinnerAddr(""); }}>
          Resolve Another
        </button>
        <style jsx>{`
          .success-card {
            background: #052e16;
            border: 1px solid #166534;
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
          }
          h3 { color: #4ade80; margin: 0 0 0.5rem; }
          p { color: #a3e5b7; margin: 0.25rem 0; }
          .winner { font-size: 0.9rem; }
          .tx-hash { font-size: 0.8rem; }
          code { color: #86efac; }
          .btn {
            margin-top: 1rem;
            background: #1e1b4b;
            color: #818cf8;
            border: 1px solid #312e81;
            padding: 0.5rem 1.25rem;
            border-radius: 8px;
            cursor: pointer;
            font-family: inherit;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="resolve-form">
      <h3>Resolve Bounty &amp; Settle Payment</h3>
      <p className="desc">
        Pick the winning agent. USDC is released from Arc and bridged to the winner&apos;s
        preferred chain via Circle Bridge Kit (CCTP).
      </p>

      <div className="field">
        <label>Bounty ID</label>
        <input
          type="number"
          placeholder="1"
          value={bountyIdStr}
          onChange={(e) => setBountyIdStr(e.target.value)}
          disabled={step !== "form"}
          min="1"
        />
      </div>
      <div className="field">
        <label>Winner Address</label>
        <input
          type="text"
          placeholder="0x..."
          value={winnerAddr}
          onChange={(e) => setWinnerAddr(e.target.value)}
          disabled={step !== "form"}
        />
      </div>
      <div className="field">
        <label>Reputation Score (0-100)</label>
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
        className="btn-primary"
        onClick={handleResolve}
        disabled={step !== "form" || !bountyIdStr || !winnerAddr}
      >
        {step === "resolving"
          ? "Resolving on-chain..."
          : step === "bridging"
          ? `Bridging USDC${winnerPayoutChain ? ` to ${CHAIN_LABELS[winnerPayoutChain] || winnerPayoutChain}` : ""}...`
          : "Resolve & Bridge Payout"}
      </button>

      {step !== "form" && (
        <div className="status-bar">
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

      <style jsx>{`
        .resolve-form {
          background: #111118;
          border: 1px solid #222;
          border-radius: 12px;
          padding: 2rem;
        }
        h3 { margin: 0 0 0.25rem; }
        .desc { color: #888; font-size: 0.85rem; margin: 0 0 1.5rem; }
        .field { margin-bottom: 1rem; }
        label { display: block; color: #888; font-size: 0.8rem; margin-bottom: 0.3rem; }
        input {
          width: 100%;
          background: #0a0a0f;
          border: 1px solid #333;
          border-radius: 8px;
          color: #e0e0e0;
          padding: 0.6rem 0.75rem;
          font-family: monospace;
          font-size: 0.9rem;
          outline: none;
          box-sizing: border-box;
        }
        input:focus { border-color: #6366f1; }
        input:disabled { opacity: 0.5; }
        .btn-primary {
          width: 100%;
          background: #6366f1;
          color: #fff;
          border: none;
          padding: 0.75rem;
          border-radius: 8px;
          font-family: inherit;
          font-size: 0.95rem;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.2s;
        }
        .btn-primary:hover:not(:disabled) { background: #4f46e5; }
        .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .status-bar {
          margin-top: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
      `}</style>
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
    <div className={`step ${done ? "done" : active ? "active" : ""}`}>
      <span className="dot">{done ? "✓" : active ? "◌" : "○"}</span>
      <span className="step-label">{label}</span>
      <style jsx>{`
        .step {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.85rem;
          color: #555;
        }
        .step.active { color: #818cf8; }
        .step.done { color: #4ade80; }
        .dot { font-size: 0.9rem; width: 1.2rem; text-align: center; }
      `}</style>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function shortAddr(addr: string): string {
  if (!addr || addr.length < 10) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
