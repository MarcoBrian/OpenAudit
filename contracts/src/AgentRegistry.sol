// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

import "erc6551/interfaces/IERC6551Registry.sol";
import "./interfaces/IENSRegistry.sol";

/**
 * @title AgentRegistry
 * @notice Registry for autonomous AI security agents
 * @dev Each agent is an ERC-721 NFT with a Token Bound Account (ERC-6551)
 *      and an ENS subdomain (agentName.openaudit.eth)
 */
contract AgentRegistry is ERC721, ERC721URIStorage, Ownable, ReentrancyGuard {
    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════════

    event AgentRegistered(
        uint256 indexed agentId,
        address indexed owner,
        address indexed tba,
        string name,
        string metadataURI
    );

    event AgentOperatorUpdated(
        uint256 indexed agentId,
        address indexed oldOperator,
        address indexed newOperator
    );

    event ENSNameRegistered(
        uint256 indexed agentId,
        bytes32 indexed node,
        string name
    );

    // ═══════════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════════

    error AgentNameTaken(string name);
    error InvalidAgentName();
    error NotAgentOwner();
    error AgentDoesNotExist();
    error InvalidOperator();

    // ═══════════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice Counter for agent IDs
    uint256 private _nextAgentId;

    /// @notice ERC-6551 Registry for creating Token Bound Accounts
    IERC6551Registry public immutable erc6551Registry;

    /// @notice Implementation address for Token Bound Accounts
    address public immutable accountImplementation;

    /// @notice ENS Registry
    IENS public immutable ensRegistry;

    /// @notice ENS Resolver for setting address and text records
    IENSResolver public immutable ensResolver;

    /// @notice The parent ENS node (namehash of "openaudit.eth")
    bytes32 public immutable parentNode;

    /// @notice Mapping from agent ID to Token Bound Account address
    mapping(uint256 => address) public agentTBA;

    /// @notice Mapping from agent ID to operator address (who can act on behalf)
    mapping(uint256 => address) public agentOperator;

    /// @notice Mapping from agent name to agent ID (0 = not taken)
    mapping(string => uint256) public nameToAgentId;

    /// @notice Mapping from agent ID to name
    mapping(uint256 => string) public agentIdToName;

    /// @notice Mapping from TBA address to agent ID
    mapping(address => uint256) public tbaToAgentId;

    /// @notice Mapping from agent ID to ENS node
    mapping(uint256 => bytes32) public agentENSNode;

    /// @notice Addresses authorized to update agent text records
    mapping(address => bool) public authorizedCallers;

    // ═══════════════════════════════════════════════════════════════════════════
    // CONSTRUCTOR
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @param _erc6551Registry Address of the ERC-6551 registry
     * @param _accountImplementation Address of the TBA implementation
     * @param _ensRegistry Address of the ENS registry
     * @param _ensResolver Address of the ENS resolver
     * @param _parentNode The namehash of "openaudit.eth"
     */
    constructor(
        address _erc6551Registry,
        address _accountImplementation,
        address _ensRegistry,
        address _ensResolver,
        bytes32 _parentNode
    ) ERC721("OpenAudit Agent", "OAAGENT") Ownable(msg.sender) {
        erc6551Registry = IERC6551Registry(_erc6551Registry);
        accountImplementation = _accountImplementation;
        ensRegistry = IENS(_ensRegistry);
        ensResolver = IENSResolver(_ensResolver);
        parentNode = _parentNode;

        // Start agent IDs at 1 (0 is reserved for "not found")
        _nextAgentId = 1;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // AGENT REGISTRATION
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Registers a new AI agent
     * @param metadataURI IPFS URI pointing to agent metadata (model info, etc.)
     * @param agentName The name for the agent (will become agentName.openaudit.eth)
     * @param initialOperator The address that can operate on behalf of the agent
     * @return agentId The ID of the newly created agent
     * @return tba The Token Bound Account address for this agent
     */
    function registerAgent(
        string calldata metadataURI,
        string calldata agentName,
        address initialOperator
    ) external nonReentrant returns (uint256 agentId, address tba) {
        // Validate agent name
        if (bytes(agentName).length == 0 || bytes(agentName).length > 32) {
            revert InvalidAgentName();
        }
        if (nameToAgentId[agentName] != 0) {
            revert AgentNameTaken(agentName);
        }
        if (initialOperator == address(0)) {
            revert InvalidOperator();
        }

        // Get next agent ID
        agentId = _nextAgentId++;

        // Mint the agent NFT to the caller
        _mint(msg.sender, agentId);
        _setTokenURI(agentId, metadataURI);

        // Create Token Bound Account
        tba = erc6551Registry.createAccount(
            accountImplementation,
            bytes32(0), // salt
            block.chainid,
            address(this),
            agentId
        );

        // Store mappings
        agentTBA[agentId] = tba;
        tbaToAgentId[tba] = agentId;
        agentOperator[agentId] = initialOperator;
        nameToAgentId[agentName] = agentId;
        agentIdToName[agentId] = agentName;

        // Create ENS subdomain
        bytes32 labelHash = keccak256(bytes(agentName));
        bytes32 node = keccak256(abi.encodePacked(parentNode, labelHash));
        agentENSNode[agentId] = node;

        // Set subdomain owner to this contract, so we can manage records
        ensRegistry.setSubnodeRecord(
            parentNode,
            labelHash,
            address(this),
            address(ensResolver),
            0 // ttl
        );

        // Set ENS address resolution to the TBA
        ensResolver.setAddr(node, tba);

        // Set initial text records
        ensResolver.setText(node, "score", "0");
        ensResolver.setText(node, "model", "unknown");

        emit AgentRegistered(agentId, msg.sender, tba, agentName, metadataURI);
        emit ENSNameRegistered(agentId, node, agentName);

        return (agentId, tba);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // AGENT MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Updates the operator for an agent
     * @param agentId The agent ID
     * @param newOperator The new operator address
     */
    function updateOperator(uint256 agentId, address newOperator) external {
        if (!_exists(agentId)) revert AgentDoesNotExist();
        if (ownerOf(agentId) != msg.sender) revert NotAgentOwner();
        if (newOperator == address(0)) revert InvalidOperator();

        address oldOperator = agentOperator[agentId];
        agentOperator[agentId] = newOperator;

        emit AgentOperatorUpdated(agentId, oldOperator, newOperator);
    }

    /**
     * @notice Updates an agent's ENS text record (only callable by contract owner or authorized)
     * @param agentId The agent ID
     * @param key The text record key
     * @param value The text record value
     */
    function updateAgentTextRecord(
        uint256 agentId,
        string calldata key,
        string calldata value
    ) external {
        if (!_exists(agentId)) revert AgentDoesNotExist();
        // Only contract owner, agent owner, or authorized callers can update text records
        if (msg.sender != owner() && msg.sender != ownerOf(agentId) && !authorizedCallers[msg.sender]) {
            revert NotAgentOwner();
        }

        bytes32 node = agentENSNode[agentId];
        ensResolver.setText(node, key, value);
    }

    /**
     * @notice Sets an address as authorized to update agent text records
     * @param caller The address to authorize/deauthorize
     * @param authorized Whether to authorize
     */
    function setAuthorizedCaller(address caller, bool authorized) external onlyOwner {
        authorizedCallers[caller] = authorized;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Resolves an agent name to its TBA address
     * @param agentName The agent name (without .openaudit.eth)
     * @return The TBA address, or address(0) if not found
     */
    function resolveName(string calldata agentName) external view returns (address) {
        uint256 agentId = nameToAgentId[agentName];
        if (agentId == 0) return address(0);
        return agentTBA[agentId];
    }

    /**
     * @notice Gets agent information by ID
     * @param agentId The agent ID
     * @return name The agent name
     * @return tba The Token Bound Account address
     * @return agentOwner The owner of the agent NFT
     * @return operator The operator address
     */
    function getAgent(uint256 agentId)
        external
        view
        returns (
            string memory name,
            address tba,
            address agentOwner,
            address operator
        )
    {
        if (!_exists(agentId)) revert AgentDoesNotExist();
        return (
            agentIdToName[agentId],
            agentTBA[agentId],
            ownerOf(agentId),
            agentOperator[agentId]
        );
    }

    /**
     * @notice Gets the total number of registered agents
     * @return The count of agents
     */
    function totalAgents() external view returns (uint256) {
        return _nextAgentId - 1;
    }

    /**
     * @notice Checks if a TBA belongs to a registered agent
     * @param tba The TBA address to check
     * @return True if the TBA belongs to a registered agent
     */
    function isRegisteredAgent(address tba) external view returns (bool) {
        return tbaToAgentId[tba] != 0;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INTERNAL FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @dev Checks if a token exists
     */
    function _exists(uint256 tokenId) internal view returns (bool) {
        return tokenId > 0 && tokenId < _nextAgentId;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // OVERRIDES
    // ═══════════════════════════════════════════════════════════════════════════

    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
