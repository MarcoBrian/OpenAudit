// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import "erc6551/interfaces/IERC6551Registry.sol";
import "./interfaces/IENSRegistry.sol";

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

    // ── State ────────────────────────────────────────────────────────────────

    uint256 public nextAgentId = 1;
    uint256 public nextBountyId = 1;
    uint256 public constant MIN_REWARD = 0.001 ether;

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
        bytes32 _parentNode
    ) ERC721("OpenAudit Agent", "OAA") Ownable(msg.sender) {
        erc6551Registry = IERC6551Registry(_erc6551Registry);
        tbaImplementation = _tbaImplementation;
        ensRegistry = IENS(_ensRegistry);
        ensResolver = IENSResolver(_ensResolver);
        parentNode = _parentNode;
    }

    // ── Admin Functions ──────────────────────────────────────────────────────

    /**
     * @notice Allows owner to transfer the ENS parent node to a new address.
     * Useful for recovering the domain if a new registry is deployed.
     */
    function transferENSNode(address newOwner) external onlyOwner {
        ensRegistry.setOwner(parentNode, newOwner);
    }

    // ── Agent Registration ───────────────────────────────────────────────────

    /**
     * @notice Register an AI agent – mints NFT, creates TBA, assigns ENS subdomain
     * @param name   Unique agent name (becomes name.openaudit.eth)
     * @param metadataURI  IPFS URI for agent metadata
     */
    function registerAgent(
        string calldata name,
        string calldata metadataURI
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

        // 4. Store agent data
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
