// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import "erc6551/interfaces/IERC6551Registry.sol";
import "./interfaces/IENSRegistry.sol";
import "./interfaces/IERC20.sol";

/**
 * @title OpenAuditRegistry
 * @notice Hackathon MVP – agents (with TBA + ENS), bounties, findings & reputation
 */
contract OpenAuditRegistry is ERC721, Ownable, ReentrancyGuard {
    // ── Types ────────────────────────────────────────────────────────────────

    struct Agent {
        address owner;
        address tba;              // ERC-6551 Token Bound Account
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

    event AgentRegistered(uint256 indexed agentId, address indexed owner, address indexed tba, string name);
    event BountyCreated(uint256 indexed bountyId, address indexed sponsor, uint256 reward, uint256 deadline);
    event BountyCancelled(uint256 indexed bountyId);
    event FindingSubmitted(uint256 indexed bountyId, address indexed agent, string reportCID);
    event BountyResolved(uint256 indexed bountyId, address indexed winner, uint256 reward);
    event BountySettlement(
        uint256 indexed bountyId,
        address indexed winner,
        uint256 reward,
        string  payoutChain
    );
    event PayoutChainUpdated(uint256 indexed agentId, string chain);
    event PayoutRelayUpdated(address indexed newRelay);
    event ReputationUpdated(address indexed agent, uint256 newScore, uint256 totalFindings);

    // ── Errors ───────────────────────────────────────────────────────────────

    error NotRegistered();
    error AlreadyRegistered();
    error NameTaken();
    error EmptyValue();
    error BountyNotActive();
    error DeadlinePassed();
    error InsufficientReward();
    error InvalidDeadline();
    error NotSponsor();
    error AlreadySubmitted();
    error NoFinding();
    error TransferFailed();

    // ── Immutables ───────────────────────────────────────────────────────────

    IERC6551Registry public immutable erc6551Registry;
    address          public immutable tbaImplementation;
    IENS             public immutable ensRegistry;
    IENSResolver     public immutable ensResolver;
    bytes32          public immutable parentNode;        // namehash("openaudit.eth")
    IERC20           public immutable usdc;               // USDC token on Arc

    // ── State ────────────────────────────────────────────────────────────────

    uint256 public nextAgentId = 1;
    uint256 public nextBountyId = 1;
    uint256 public constant MIN_REWARD = 1e6;  // 1 USDC (6 decimals)

    /// @notice Relay wallet that receives USDC on resolution for cross-chain bridging
    address public payoutRelay;

    mapping(uint256 => Agent)   public agents;
    mapping(address => uint256) public ownerToAgentId;       // owner addr  → agentId
    mapping(address => uint256) public tbaToAgentId;          // TBA addr    → agentId
    mapping(string  => uint256) public nameToAgentId;         // agent name  → agentId
    mapping(uint256 => bytes32) public agentENSNode;          // agentId     → ENS node

    mapping(uint256 => Bounty)  public bounties;

    /// bountyId => agent address => Finding
    mapping(uint256 => mapping(address => Finding)) public findings;
    /// bountyId => list of submitters
    mapping(uint256 => address[]) public bountySubmitters;
    /// agent address => list of CIDs they ever submitted
    mapping(address => string[]) public agentReportCIDs;

    // ── Constructor ──────────────────────────────────────────────────────────

    constructor(
        address _erc6551Registry,
        address _tbaImplementation,
        address _ensRegistry,
        address _ensResolver,
        bytes32 _parentNode,
        address _usdc,
        address _payoutRelay
    ) ERC721("OpenAudit Agent", "OAA") Ownable(msg.sender) {
        erc6551Registry = IERC6551Registry(_erc6551Registry);
        tbaImplementation = _tbaImplementation;
        ensRegistry = IENS(_ensRegistry);
        ensResolver = IENSResolver(_ensResolver);
        parentNode = _parentNode;
        usdc = IERC20(_usdc);
        payoutRelay = _payoutRelay;
    }

    // ── Admin Functions ──────────────────────────────────────────────────────

    /**
     * @notice Allows owner to transfer the ENS parent node to a new address.
     * Useful for recovering the domain if a new registry is deployed.
     */
    function transferENSNode(address newOwner) external onlyOwner {
        ensRegistry.setOwner(parentNode, newOwner);
    }

    /**
     * @notice Update the relay wallet that receives USDC for cross-chain bridging
     */
    function setPayoutRelay(address _payoutRelay) external onlyOwner {
        payoutRelay = _payoutRelay;
        emit PayoutRelayUpdated(_payoutRelay);
    }

    // ── Agent Registration ───────────────────────────────────────────────────

    /**
     * @notice Register an AI agent – mints NFT, creates TBA, assigns ENS subdomain
     * @param name   Unique agent name (becomes name.openaudit.eth)
     * @param metadataURI  IPFS URI for agent metadata
     */
    /**
     * @notice Register an AI agent – mints NFT, creates TBA, assigns ENS subdomain
     * @param name   Unique agent name (becomes name.openaudit.eth)
     * @param metadataURI  IPFS URI for agent metadata
     * @param payoutChain  Preferred chain for receiving USDC payouts (e.g. "base", "ethereum", "arbitrum")
     */
    function registerAgent(
        string calldata name,
        string calldata metadataURI,
        string calldata payoutChain
    ) external nonReentrant returns (uint256 agentId, address tba) {
        if (bytes(name).length == 0 || bytes(name).length > 32) revert EmptyValue();
        if (ownerToAgentId[msg.sender] != 0) revert AlreadyRegistered();
        if (nameToAgentId[name] != 0) revert NameTaken();

        agentId = nextAgentId++;

        // 1. Mint agent NFT
        _mint(msg.sender, agentId);

        // 2. Create TBA via ERC-6551
        tba = erc6551Registry.createAccount(
            tbaImplementation,
            bytes32(0),
            block.chainid,
            address(this),
            agentId
        );

        // 3. Register ENS subdomain (name.openaudit.eth)
        bytes32 labelHash = keccak256(bytes(name));
        bytes32 node = keccak256(abi.encodePacked(parentNode, labelHash));
        agentENSNode[agentId] = node;

        ensRegistry.setSubnodeRecord(
            parentNode,
            labelHash,
            address(this),
            address(ensResolver),
            0
        );
        ensResolver.setAddr(node, tba);
        ensResolver.setText(node, "score", "0");

        // 4. Set preferred payout chain in ENS text record
        if (bytes(payoutChain).length > 0) {
            ensResolver.setText(node, "payout_chain", payoutChain);
        }

        // 5. Store agent data
        agents[agentId] = Agent({
            owner: msg.sender,
            tba: tba,
            name: name,
            metadataURI: metadataURI,
            totalScore: 0,
            findingsCount: 0,
            registered: true
        });
        ownerToAgentId[msg.sender] = agentId;
        tbaToAgentId[tba] = agentId;
        nameToAgentId[name] = agentId;

        emit AgentRegistered(agentId, msg.sender, tba, name);
    }

    /**
     * @notice Update an agent's preferred payout chain
     * @dev Callable by agent owner or TBA
     */
    function setPayoutChain(uint256 agentId, string calldata chain) external {
        Agent storage a = agents[agentId];
        if (!a.registered) revert NotRegistered();
        if (msg.sender != a.owner && msg.sender != a.tba) revert NotRegistered();
        bytes32 node = agentENSNode[agentId];
        ensResolver.setText(node, "payout_chain", chain);
        emit PayoutChainUpdated(agentId, chain);
    }

    /**
     * @notice Read an agent's preferred payout chain from ENS
     */
    function getPayoutChain(uint256 agentId) external view returns (string memory) {
        bytes32 node = agentENSNode[agentId];
        if (node == bytes32(0)) return "";
        return ensResolver.text(node, "payout_chain");
    }

    function isRegistered(address addr) external view returns (bool) {
        return ownerToAgentId[addr] != 0 || tbaToAgentId[addr] != 0;
    }

    function getAgent(uint256 agentId) external view returns (Agent memory) {
        return agents[agentId];
    }

    /// @notice Look up an agent's TBA by their name
    function resolveName(string calldata name) external view returns (address) {
        uint256 agentId = nameToAgentId[name];
        if (agentId == 0) return address(0);
        return agents[agentId].tba;
    }

    // ── Bounty Management ────────────────────────────────────────────────────

    /**
     * @notice Create a bounty with USDC reward
     * @dev Sponsor must first approve this contract to spend `rewardAmount` USDC
     * @param targetContract The contract address to be audited
     * @param deadline       Timestamp after which no findings can be submitted
     * @param rewardAmount   USDC reward amount (6 decimals, e.g. 1000e6 = 1000 USDC)
     */
    function createBounty(
        address targetContract,
        uint256 deadline,
        uint256 rewardAmount
    ) external nonReentrant returns (uint256 bountyId) {
        if (rewardAmount < MIN_REWARD) revert InsufficientReward();
        if (deadline <= block.timestamp) revert InvalidDeadline();

        // Transfer USDC from sponsor to this contract
        bool ok = usdc.transferFrom(msg.sender, address(this), rewardAmount);
        if (!ok) revert TransferFailed();

        bountyId = nextBountyId++;
        bounties[bountyId] = Bounty({
            sponsor: msg.sender,
            targetContract: targetContract,
            reward: rewardAmount,
            deadline: deadline,
            active: true,
            resolved: false,
            winner: address(0)
        });

        emit BountyCreated(bountyId, msg.sender, rewardAmount, deadline);
    }

    /**
     * @notice Cancel a bounty and refund USDC to sponsor
     */
    function cancelBounty(uint256 bountyId) external nonReentrant {
        Bounty storage b = bounties[bountyId];
        if (b.sponsor != msg.sender) revert NotSponsor();
        if (!b.active) revert BountyNotActive();

        b.active = false;

        bool ok = usdc.transfer(b.sponsor, b.reward);
        if (!ok) revert TransferFailed();

        emit BountyCancelled(bountyId);
    }

    // ── Submit Finding ───────────────────────────────────────────────────────

    /**
     * @notice Submit a finding – caller can be agent owner OR their TBA
     * @dev Pin the report to IPFS first, then submit the CID here
     */
    function submitFinding(
        uint256 bountyId,
        string calldata reportCID
    ) external {
        if (bytes(reportCID).length == 0) revert EmptyValue();

        // Accept submission from either agent owner or TBA
        address submitter = msg.sender;
        if (ownerToAgentId[submitter] == 0 && tbaToAgentId[submitter] == 0) {
            revert NotRegistered();
        }

        Bounty storage b = bounties[bountyId];
        if (!b.active) revert BountyNotActive();
        if (block.timestamp > b.deadline) revert DeadlinePassed();
        if (findings[bountyId][submitter].submittedAt != 0) revert AlreadySubmitted();

        findings[bountyId][submitter] = Finding({
            agent: submitter,
            reportCID: reportCID,
            submittedAt: block.timestamp
        });
        bountySubmitters[bountyId].push(submitter);
        agentReportCIDs[submitter].push(reportCID);

        emit FindingSubmitted(bountyId, submitter, reportCID);
    }

    // ── Resolve Bounty ───────────────────────────────────────────────────────

    /**
     * @notice Resolve a bounty – picks winner, updates reputation, sends USDC to
     *         payout relay for cross-chain bridging to winner's preferred chain
     * @param bountyId        The bounty to resolve
     * @param winner          Address of the winning agent (owner or TBA)
     * @param reputationScore Score 0-100 for this finding
     */
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

        // Resolve agentId from either owner or TBA
        uint256 agentId = ownerToAgentId[winner];
        if (agentId == 0) agentId = tbaToAgentId[winner];

        // Update reputation
        agents[agentId].totalScore += reputationScore;
        agents[agentId].findingsCount += 1;

        // Update ENS score text record
        _updateENSScore(agentId);

        emit ReputationUpdated(winner, agents[agentId].totalScore, agents[agentId].findingsCount);

        // Read winner's preferred payout chain from ENS
        string memory payoutChain = "";
        bytes32 node = agentENSNode[agentId];
        if (node != bytes32(0)) {
            try ensResolver.text(node, "payout_chain") returns (string memory chain) {
                payoutChain = chain;
            } catch {}
        }

        // Transfer USDC to payout relay for cross-chain bridging
        // If no relay is set, send directly to winner (same-chain settlement)
        address recipient = payoutRelay != address(0) ? payoutRelay : winner;
        bool ok = usdc.transfer(recipient, b.reward);
        if (!ok) revert TransferFailed();

        emit BountyResolved(bountyId, winner, b.reward);
        emit BountySettlement(bountyId, winner, b.reward, payoutChain);
    }

    // ── View Helpers ─────────────────────────────────────────────────────────

    function getBountySubmitters(uint256 bountyId) external view returns (address[] memory) {
        return bountySubmitters[bountyId];
    }

    function getAgentReportCIDs(address agent) external view returns (string[] memory) {
        return agentReportCIDs[agent];
    }

    function getReputation(address agent) external view returns (uint256 totalScore, uint256 findingsCount, uint256 avgScore) {
        uint256 agentId = ownerToAgentId[agent];
        if (agentId == 0) agentId = tbaToAgentId[agent];
        if (agentId == 0) return (0, 0, 0);
        Agent storage a = agents[agentId];
        totalScore = a.totalScore;
        findingsCount = a.findingsCount;
        avgScore = findingsCount > 0 ? totalScore / findingsCount : 0;
    }

    // ── Internal ─────────────────────────────────────────────────────────────

    function _updateENSScore(uint256 agentId) internal {
        bytes32 node = agentENSNode[agentId];
        if (node == bytes32(0)) return;
        Agent storage a = agents[agentId];
        uint256 avg = a.findingsCount > 0 ? a.totalScore / a.findingsCount : 0;
        try ensResolver.setText(node, "score", _toString(avg)) {} catch {}
    }

    function _toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) { digits++; temp /= 10; }
        bytes memory buf = new bytes(digits);
        while (value != 0) { digits--; buf[digits] = bytes1(uint8(48 + value % 10)); value /= 10; }
        return string(buf);
    }
}
