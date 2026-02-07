// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import "./interfaces/IERC8004Reputation.sol";
import "./AgentRegistry.sol";

/**
 * @title BountyHive
 * @notice Core workflow for the OpenAudit security bounty system
 * @dev Implements commit-reveal scheme for secret bug reports
 */
contract BountyHive is Ownable, ReentrancyGuard {
    // ═══════════════════════════════════════════════════════════════════════════
    // TYPES
    // ═══════════════════════════════════════════════════════════════════════════

    enum BountyStatus {
        Active,     // Bounty is open for submissions
        Resolved,   // Bounty has been resolved with a winner
        Cancelled   // Bounty was cancelled by sponsor
    }

    enum Severity {
        None,       // 0 - No valid finding
        Low,        // 1 - Low severity
        Medium,     // 2 - Medium severity
        High,       // 3 - High severity
        Critical    // 4 - Critical severity
    }

    struct Bounty {
        address sponsor;            // Who created the bounty
        address targetContract;     // The contract being audited
        uint256 reward;             // ETH reward amount
        uint256 createdAt;          // Timestamp of creation
        uint256 deadline;           // Deadline for submissions
        BountyStatus status;        // Current status
        address winnerTBA;          // Winner's TBA (if resolved)
        Severity resolvedSeverity;  // Severity of winning finding
    }

    struct Commitment {
        string reportCID;           // IPFS CID of the report
        uint256 bountyId;           // The bounty this commitment is for
        uint256 timestamp;          // When committed
        bool revealed;              // Whether PoC was revealed
    }

    struct Finding {
        address submitter;          // Who submitted (TBA address)
        string reportCID;           // IPFS CID of the report
        string pocTestCID;          // IPFS CID of the Foundry PoC test
        uint256 revealedAt;         // When PoC was revealed
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════════

    event BountyCreated(
        uint256 indexed bountyId,
        address indexed sponsor,
        address indexed targetContract,
        uint256 reward,
        uint256 deadline
    );

    event BountyCancelled(uint256 indexed bountyId, address indexed sponsor);

    event FindingCommitted(
        uint256 indexed bountyId,
        address indexed submitter,
        string reportCID
    );

    event FindingRevealed(
        uint256 indexed bountyId,
        address indexed submitter,
        string reportCID,
        string pocTestCID
    );

    event BountyResolved(
        uint256 indexed bountyId,
        address indexed winnerTBA,
        Severity severity,
        uint256 reward
    );

    // ═══════════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════════

    error BountyNotFound();
    error BountyNotActive();
    error BountyDeadlinePassed();
    error BountyDeadlineNotPassed();
    error InsufficientReward();
    error InvalidDeadline();
    error NotBountySponsor();
    error CommitmentNotFound();
    error CommitmentAlreadyRevealed();
    error InvalidReveal();
    error InvalidWinner();
    error NotRegisteredAgent();
    error TransferFailed();
    error EmptyCID();

    // ═══════════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice Counter for bounty IDs
    uint256 private _nextBountyId;

    /// @notice Minimum bounty reward (0.01 ETH)
    uint256 public constant MIN_REWARD = 0.01 ether;

    /// @notice Agent Registry for verifying agents
    AgentRegistry public immutable agentRegistry;

    /// @notice Reputation Registry for giving feedback
    IERC8004Reputation public immutable reputationRegistry;

    /// @notice Mapping from bounty ID to Bounty
    mapping(uint256 => Bounty) public bounties;

    /// @notice Mapping from commitment key (keccak256(submitter, bountyId)) to Commitment
    mapping(bytes32 => Commitment) public commitments;

    /// @notice Mapping from (bountyId, submitter) to Finding (after reveal)
    mapping(uint256 => mapping(address => Finding)) public findings;

    /// @notice Array of submitters per bounty (for enumeration)
    mapping(uint256 => address[]) public bountySubmitters;

    /// @notice Mapping from submitter address to array of CIDs they submitted
    mapping(address => string[]) public submitterReportCIDs;

    // ═══════════════════════════════════════════════════════════════════════════
    // CONSTRUCTOR
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @param _agentRegistry Address of the AgentRegistry
     * @param _reputationRegistry Address of the ReputationRegistry
     */
    constructor(
        address _agentRegistry,
        address _reputationRegistry
    ) Ownable(msg.sender) {
        agentRegistry = AgentRegistry(_agentRegistry);
        reputationRegistry = IERC8004Reputation(_reputationRegistry);
        _nextBountyId = 1;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BOUNTY CREATION
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Creates a new bounty
     * @param targetContract The contract to be audited
     * @param deadline Deadline timestamp for submissions
     * @return bountyId The ID of the created bounty
     */
    function createBounty(
        address targetContract,
        uint256 deadline
    ) external payable nonReentrant returns (uint256 bountyId) {
        if (msg.value < MIN_REWARD) revert InsufficientReward();
        if (deadline <= block.timestamp) revert InvalidDeadline();

        bountyId = _nextBountyId++;

        bounties[bountyId] = Bounty({
            sponsor: msg.sender,
            targetContract: targetContract,
            reward: msg.value,
            createdAt: block.timestamp,
            deadline: deadline,
            status: BountyStatus.Active,
            winnerTBA: address(0),
            resolvedSeverity: Severity.None
        });

        emit BountyCreated(
            bountyId,
            msg.sender,
            targetContract,
            msg.value,
            deadline
        );

        return bountyId;
    }

    /**
     * @notice Cancels a bounty and refunds the sponsor
     * @param bountyId The bounty ID
     */
    function cancelBounty(uint256 bountyId) external nonReentrant {
        Bounty storage bounty = bounties[bountyId];
        if (bounty.sponsor == address(0)) revert BountyNotFound();
        if (bounty.sponsor != msg.sender) revert NotBountySponsor();
        if (bounty.status != BountyStatus.Active) revert BountyNotActive();

        bounty.status = BountyStatus.Cancelled;

        // Refund sponsor
        (bool success, ) = msg.sender.call{value: bounty.reward}("");
        if (!success) revert TransferFailed();

        emit BountyCancelled(bountyId, msg.sender);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // PHASE 1: COMMIT
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Commits a finding with its IPFS report CID (Phase 1)
     * @dev The CID is stored on-chain, correlated with msg.sender for ownership tracking
     * @param bountyId The bounty ID
     * @param reportCID The IPFS CID of the report (obtained by pinning to IPFS first)
     */
    function commitFinding(
        uint256 bountyId,
        string calldata reportCID
    ) external {
        if (bytes(reportCID).length == 0) revert EmptyCID();

        Bounty storage bounty = bounties[bountyId];
        if (bounty.sponsor == address(0)) revert BountyNotFound();
        if (bounty.status != BountyStatus.Active) revert BountyNotActive();
        if (block.timestamp > bounty.deadline) revert BountyDeadlinePassed();

        // Verify caller is a registered agent TBA
        if (!agentRegistry.isRegisteredAgent(msg.sender)) {
            revert NotRegisteredAgent();
        }

        bytes32 commitKey = keccak256(abi.encodePacked(msg.sender, bountyId));

        commitments[commitKey] = Commitment({
            reportCID: reportCID,
            bountyId: bountyId,
            timestamp: block.timestamp,
            revealed: false
        });

        bountySubmitters[bountyId].push(msg.sender);
        submitterReportCIDs[msg.sender].push(reportCID);

        emit FindingCommitted(bountyId, msg.sender, reportCID);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // PHASE 2: REVEAL
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Reveals the PoC test for a committed finding (Phase 2)
     * @param bountyId The bounty ID
     * @param pocTestCID IPFS CID of the Foundry PoC test file (.t.sol)
     */
    function revealFinding(
        uint256 bountyId,
        string calldata pocTestCID
    ) external {
        Bounty storage bounty = bounties[bountyId];
        if (bounty.sponsor == address(0)) revert BountyNotFound();
        if (bounty.status != BountyStatus.Active) revert BountyNotActive();

        bytes32 commitKey = keccak256(abi.encodePacked(msg.sender, bountyId));
        Commitment storage commitment = commitments[commitKey];

        if (bytes(commitment.reportCID).length == 0) revert CommitmentNotFound();
        if (commitment.revealed) revert CommitmentAlreadyRevealed();

        // Mark as revealed
        commitment.revealed = true;

        // Store the finding
        findings[bountyId][msg.sender] = Finding({
            submitter: msg.sender,
            reportCID: commitment.reportCID,
            pocTestCID: pocTestCID,
            revealedAt: block.timestamp
        });

        emit FindingRevealed(bountyId, msg.sender, commitment.reportCID, pocTestCID);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // PHASE 3: SETTLEMENT
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Resolves a bounty and pays the winner (Admin/Judge only)
     * @param bountyId The bounty ID
     * @param winnerTBA The TBA address of the winner
     * @param severity The severity of the finding (determines reputation score)
     */
    function resolveBounty(
        uint256 bountyId,
        address winnerTBA,
        Severity severity
    ) external onlyOwner nonReentrant {
        Bounty storage bounty = bounties[bountyId];
        if (bounty.sponsor == address(0)) revert BountyNotFound();
        if (bounty.status != BountyStatus.Active) revert BountyNotActive();

        // Verify winner has a revealed finding
        Finding storage finding = findings[bountyId][winnerTBA];
        if (finding.submitter == address(0)) revert InvalidWinner();

        // Update bounty status
        bounty.status = BountyStatus.Resolved;
        bounty.winnerTBA = winnerTBA;
        bounty.resolvedSeverity = severity;

        // Calculate reputation score based on severity
        uint256 reputationScore = _severityToScore(severity);

        // Give feedback to reputation registry
        bytes32 evidenceHash = keccak256(bytes(finding.reportCID));
        reputationRegistry.giveFeedback(winnerTBA, reputationScore, evidenceHash);

        // Update agent's ENS text record with last audit CID
        uint256 agentId = agentRegistry.tbaToAgentId(winnerTBA);
        if (agentId != 0) {
            try agentRegistry.updateAgentTextRecord(agentId, "last_audit", finding.reportCID) {} catch {}
        }

        // Transfer reward to winner TBA
        (bool success, ) = winnerTBA.call{value: bounty.reward}("");
        if (!success) revert TransferFailed();

        emit BountyResolved(bountyId, winnerTBA, severity, bounty.reward);
    }

    /**
     * @notice Marks a submission as spam and slashes the agent
     * @param bountyId The bounty ID
     * @param spammerTBA The TBA address of the spammer
     */
    function markAsSpam(
        uint256 bountyId,
        address spammerTBA
    ) external onlyOwner {
        Bounty storage bounty = bounties[bountyId];
        if (bounty.sponsor == address(0)) revert BountyNotFound();

        // Give 0 score (spam) to reputation registry
        Finding storage finding = findings[bountyId][spammerTBA];
        bytes32 evidenceHash = finding.submitter != address(0) 
            ? keccak256(bytes(finding.reportCID))
            : bytes32(0);

        reputationRegistry.giveFeedback(spammerTBA, 0, evidenceHash);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Gets the total number of bounties
     * @return The count of bounties
     */
    function totalBounties() external view returns (uint256) {
        return _nextBountyId - 1;
    }

    /**
     * @notice Gets all submitters for a bounty
     * @param bountyId The bounty ID
     * @return Array of submitter addresses
     */
    function getBountySubmitters(uint256 bountyId) external view returns (address[] memory) {
        return bountySubmitters[bountyId];
    }

    /**
     * @notice Gets a commitment
     * @param submitter The submitter address
     * @param bountyId The bounty ID
     * @return The commitment details
     */
    function getCommitment(
        address submitter,
        uint256 bountyId
    ) external view returns (Commitment memory) {
        bytes32 commitKey = keccak256(abi.encodePacked(submitter, bountyId));
        return commitments[commitKey];
    }

    /**
     * @notice Gets all report CIDs submitted by an address
     * @param submitter The submitter address
     * @return Array of IPFS CIDs
     */
    function getSubmitterReportCIDs(
        address submitter
    ) external view returns (string[] memory) {
        return submitterReportCIDs[submitter];
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INTERNAL FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @dev Converts severity to reputation score (0-100)
     */
    function _severityToScore(Severity severity) internal pure returns (uint256) {
        if (severity == Severity.Critical) return 100;
        if (severity == Severity.High) return 75;
        if (severity == Severity.Medium) return 50;
        if (severity == Severity.Low) return 25;
        return 0; // None
    }
}
