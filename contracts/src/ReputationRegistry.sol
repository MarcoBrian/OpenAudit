// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

import "./interfaces/IERC8004Reputation.sol";
import "./interfaces/IENSRegistry.sol";
import "./AgentRegistry.sol";

/**
 * @title ReputationRegistry
 * @notice ERC-8004 Reputation Registry for AI security agents
 * @dev Tracks reputation scores based on bounty outcomes
 */
contract ReputationRegistry is IERC8004Reputation, Ownable {
    // ═══════════════════════════════════════════════════════════════════════════
    // TYPES
    // ═══════════════════════════════════════════════════════════════════════════

    struct ReputationData {
        uint256 totalScore;         // Cumulative score
        uint256 feedbackCount;      // Number of feedback entries
        bool slashed;               // Whether agent has been slashed
        uint256 lastUpdated;        // Last update timestamp
    }

    struct FeedbackEntry {
        address reviewer;           // Who gave the feedback (e.g., BountyHive)
        uint256 score;              // Score given (0-100)
        bytes32 evidenceHash;       // Hash of evidence
        uint256 timestamp;          // When given
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice Agent Registry for ENS updates
    AgentRegistry public agentRegistry;

    /// @notice Mapping from TBA address to reputation data
    mapping(address => ReputationData) public reputations;

    /// @notice Mapping from TBA to array of feedback entries
    mapping(address => FeedbackEntry[]) public feedbackHistory;

    /// @notice Addresses authorized to give feedback (e.g., BountyHive)
    mapping(address => bool) public authorizedReviewers;

    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════════

    event ReviewerAuthorized(address indexed reviewer, bool authorized);
    event AgentRegistrySet(address indexed agentRegistry);

    // ═══════════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════════

    error NotAuthorizedReviewer();
    error InvalidScore();
    error AgentSlashed();

    // ═══════════════════════════════════════════════════════════════════════════
    // CONSTRUCTOR
    // ═══════════════════════════════════════════════════════════════════════════

    constructor() Ownable(msg.sender) {}

    // ═══════════════════════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Sets the AgentRegistry address
     * @param _agentRegistry The AgentRegistry address
     */
    function setAgentRegistry(address _agentRegistry) external onlyOwner {
        agentRegistry = AgentRegistry(_agentRegistry);
        emit AgentRegistrySet(_agentRegistry);
    }

    /**
     * @notice Authorizes or deauthorizes a reviewer (e.g., BountyHive)
     * @param reviewer The reviewer address
     * @param authorized Whether to authorize
     */
    function setAuthorizedReviewer(address reviewer, bool authorized) external onlyOwner {
        authorizedReviewers[reviewer] = authorized;
        emit ReviewerAuthorized(reviewer, authorized);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // FEEDBACK
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Gives feedback to an agent
     * @param agentTBA The Token Bound Account address of the agent
     * @param score The score (0-100). 0 = Spam/Slash, 100 = Critical finding
     * @param evidenceHash Hash of the evidence (IPFS CID hash)
     */
    function giveFeedback(
        address agentTBA,
        uint256 score,
        bytes32 evidenceHash
    ) external override {
        // Only authorized reviewers can give feedback
        if (!authorizedReviewers[msg.sender] && msg.sender != owner()) {
            revert NotAuthorizedReviewer();
        }
        if (score > 100) revert InvalidScore();

        ReputationData storage rep = reputations[agentTBA];

        // Handle spam/slash case
        if (score == 0) {
            rep.slashed = true;
            rep.totalScore = 0;
            rep.lastUpdated = block.timestamp;

            emit Slashed(agentTBA, evidenceHash);

            // Update ENS score to 0
            _updateENSScore(agentTBA, 0);
        } else {
            // Normal feedback
            if (rep.slashed) revert AgentSlashed();

            rep.totalScore += score;
            rep.feedbackCount += 1;
            rep.lastUpdated = block.timestamp;

            // Update ENS score
            uint256 avgScore = rep.totalScore / rep.feedbackCount;
            _updateENSScore(agentTBA, avgScore);
        }

        // Store feedback entry
        feedbackHistory[agentTBA].push(FeedbackEntry({
            reviewer: msg.sender,
            score: score,
            evidenceHash: evidenceHash,
            timestamp: block.timestamp
        }));

        emit FeedbackGiven(agentTBA, msg.sender, score, evidenceHash, block.timestamp);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @notice Gets the reputation score for an agent
     * @param agentTBA The Token Bound Account address
     * @return totalScore The cumulative score
     * @return feedbackCount The number of feedback entries
     * @return averageScore The average score (totalScore / feedbackCount)
     */
    function getScore(address agentTBA)
        external
        view
        override
        returns (
            uint256 totalScore,
            uint256 feedbackCount,
            uint256 averageScore
        )
    {
        ReputationData storage rep = reputations[agentTBA];
        totalScore = rep.totalScore;
        feedbackCount = rep.feedbackCount;
        averageScore = feedbackCount > 0 ? totalScore / feedbackCount : 0;
    }

    /**
     * @notice Checks if an agent has been slashed
     * @param agentTBA The Token Bound Account address
     * @return True if the agent has been slashed
     */
    function isSlashed(address agentTBA) external view override returns (bool) {
        return reputations[agentTBA].slashed;
    }

    /**
     * @notice Gets the feedback history for an agent
     * @param agentTBA The Token Bound Account address
     * @return Array of feedback entries
     */
    function getFeedbackHistory(address agentTBA)
        external
        view
        returns (FeedbackEntry[] memory)
    {
        return feedbackHistory[agentTBA];
    }

    /**
     * @notice Gets the number of feedback entries for an agent
     * @param agentTBA The Token Bound Account address
     * @return The count of feedback entries
     */
    function getFeedbackCount(address agentTBA) external view returns (uint256) {
        return feedbackHistory[agentTBA].length;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INTERNAL FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * @dev Updates the ENS text record for an agent's score
     */
    function _updateENSScore(address agentTBA, uint256 score) internal {
        if (address(agentRegistry) == address(0)) return;

        uint256 agentId = agentRegistry.tbaToAgentId(agentTBA);
        if (agentId == 0) return;

        // Convert score to string
        string memory scoreStr = _uintToString(score);

        try agentRegistry.updateAgentTextRecord(agentId, "score", scoreStr) {} catch {}
    }

    /**
     * @dev Converts uint256 to string
     */
    function _uintToString(uint256 value) internal pure returns (string memory) {
        if (value == 0) {
            return "0";
        }
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) {
            digits++;
            temp /= 10;
        }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits -= 1;
            buffer[digits] = bytes1(uint8(48 + uint256(value % 10)));
            value /= 10;
        }
        return string(buffer);
    }
}
