// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title OpenAuditRegistry
 * @notice Hackathon MVP – single contract for agents, bounties, findings & reputation
 */
contract OpenAuditRegistry is Ownable, ReentrancyGuard {
    // ── Types ────────────────────────────────────────────────────────────────

    struct Agent {
        address owner;
        string  name;
        string  metadataURI;      // ipfs://…
        uint256 totalScore;
        uint256 findingsCount;
        bool    registered;
    }

    struct Bounty {
        address sponsor;
        address targetContract;
        uint256 reward;
        uint256 deadline;
        bool    active;
        bool    resolved;
        address winner;
    }

    struct Finding {
        address agent;
        string  reportCID;        // IPFS CID of the report
        uint256 submittedAt;
    }

    // ── Events ───────────────────────────────────────────────────────────────

    event AgentRegistered(uint256 indexed agentId, address indexed owner, string name);
    event BountyCreated(uint256 indexed bountyId, address indexed sponsor, uint256 reward, uint256 deadline);
    event BountyCancelled(uint256 indexed bountyId);
    event FindingSubmitted(uint256 indexed bountyId, address indexed agent, string reportCID);
    event BountyResolved(uint256 indexed bountyId, address indexed winner, uint256 reward);
    event ReputationUpdated(address indexed agent, uint256 newScore, uint256 totalFindings);

    // ── Errors ───────────────────────────────────────────────────────────────

    error NotRegistered();
    error AlreadyRegistered();
    error EmptyValue();
    error BountyNotActive();
    error DeadlinePassed();
    error InsufficientReward();
    error InvalidDeadline();
    error NotSponsor();
    error AlreadySubmitted();
    error NoFinding();
    error TransferFailed();

    // ── State ────────────────────────────────────────────────────────────────

    uint256 public nextAgentId = 1;
    uint256 public nextBountyId = 1;
    uint256 public constant MIN_REWARD = 0.001 ether;

    mapping(uint256 => Agent)   public agents;
    mapping(address => uint256) public addressToAgentId;

    mapping(uint256 => Bounty)  public bounties;

    /// bountyId => agent address => Finding
    mapping(uint256 => mapping(address => Finding)) public findings;
    /// bountyId => list of submitters
    mapping(uint256 => address[]) public bountySubmitters;
    /// agent address => list of CIDs they ever submitted
    mapping(address => string[]) public agentReportCIDs;

    // ── Constructor ──────────────────────────────────────────────────────────

    constructor() Ownable(msg.sender) {}

    // ── Agent Registration ───────────────────────────────────────────────────

    function registerAgent(
        string calldata name,
        string calldata metadataURI
    ) external returns (uint256 agentId) {
        if (bytes(name).length == 0) revert EmptyValue();
        if (addressToAgentId[msg.sender] != 0) revert AlreadyRegistered();

        agentId = nextAgentId++;
        agents[agentId] = Agent({
            owner: msg.sender,
            name: name,
            metadataURI: metadataURI,
            totalScore: 0,
            findingsCount: 0,
            registered: true
        });
        addressToAgentId[msg.sender] = agentId;

        emit AgentRegistered(agentId, msg.sender, name);
    }

    function isRegistered(address addr) external view returns (bool) {
        return addressToAgentId[addr] != 0;
    }

    function getAgent(uint256 agentId) external view returns (Agent memory) {
        return agents[agentId];
    }

    // ── Bounty Management ────────────────────────────────────────────────────

    function createBounty(
        address targetContract,
        uint256 deadline
    ) external payable nonReentrant returns (uint256 bountyId) {
        if (msg.value < MIN_REWARD) revert InsufficientReward();
        if (deadline <= block.timestamp) revert InvalidDeadline();

        bountyId = nextBountyId++;
        bounties[bountyId] = Bounty({
            sponsor: msg.sender,
            targetContract: targetContract,
            reward: msg.value,
            deadline: deadline,
            active: true,
            resolved: false,
            winner: address(0)
        });

        emit BountyCreated(bountyId, msg.sender, msg.value, deadline);
    }

    function cancelBounty(uint256 bountyId) external nonReentrant {
        Bounty storage b = bounties[bountyId];
        if (b.sponsor != msg.sender) revert NotSponsor();
        if (!b.active) revert BountyNotActive();

        b.active = false;

        (bool ok, ) = msg.sender.call{value: b.reward}("");
        if (!ok) revert TransferFailed();

        emit BountyCancelled(bountyId);
    }

    // ── Submit Finding (pin to IPFS first, then submit CID here) ─────────

    function submitFinding(
        uint256 bountyId,
        string calldata reportCID
    ) external {
        if (bytes(reportCID).length == 0) revert EmptyValue();
        if (addressToAgentId[msg.sender] == 0) revert NotRegistered();

        Bounty storage b = bounties[bountyId];
        if (!b.active) revert BountyNotActive();
        if (block.timestamp > b.deadline) revert DeadlinePassed();
        if (findings[bountyId][msg.sender].submittedAt != 0) revert AlreadySubmitted();

        findings[bountyId][msg.sender] = Finding({
            agent: msg.sender,
            reportCID: reportCID,
            submittedAt: block.timestamp
        });
        bountySubmitters[bountyId].push(msg.sender);
        agentReportCIDs[msg.sender].push(reportCID);

        emit FindingSubmitted(bountyId, msg.sender, reportCID);
    }

    // ── Resolve Bounty (owner/judge picks winner) ────────────────────────

    function resolveBounty(
        uint256 bountyId,
        address winner,
        uint256 reputationScore   // 0-100
    ) external onlyOwner nonReentrant {
        Bounty storage b = bounties[bountyId];
        if (!b.active) revert BountyNotActive();
        if (findings[bountyId][winner].submittedAt == 0) revert NoFinding();

        b.active = false;
        b.resolved = true;
        b.winner = winner;

        // Update reputation
        uint256 agentId = addressToAgentId[winner];
        agents[agentId].totalScore += reputationScore;
        agents[agentId].findingsCount += 1;

        emit ReputationUpdated(winner, agents[agentId].totalScore, agents[agentId].findingsCount);

        // Pay winner
        (bool ok, ) = winner.call{value: b.reward}("");
        if (!ok) revert TransferFailed();

        emit BountyResolved(bountyId, winner, b.reward);
    }

    // ── View Helpers ─────────────────────────────────────────────────────────

    function getBountySubmitters(uint256 bountyId) external view returns (address[] memory) {
        return bountySubmitters[bountyId];
    }

    function getAgentReportCIDs(address agent) external view returns (string[] memory) {
        return agentReportCIDs[agent];
    }

    function getReputation(address agent) external view returns (uint256 totalScore, uint256 findingsCount, uint256 avgScore) {
        uint256 agentId = addressToAgentId[agent];
        if (agentId == 0) return (0, 0, 0);
        Agent storage a = agents[agentId];
        totalScore = a.totalScore;
        findingsCount = a.findingsCount;
        avgScore = findingsCount > 0 ? totalScore / findingsCount : 0;
    }
}
