// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IERC8004Reputation
 * @notice Interface for the ERC-8004 Reputation Registry
 * @dev Tracks reputation scores for autonomous agents (TBAs)
 */
interface IERC8004Reputation {
    /**
     * @notice Emitted when feedback is given to an agent
     * @param agentTBA The Token Bound Account address of the agent
     * @param reviewer The address providing the feedback (e.g., BountyHive)
     * @param score The score given (0-100)
     * @param evidenceHash Hash of the evidence (e.g., IPFS CID hash)
     * @param timestamp When the feedback was given
     */
    event FeedbackGiven(
        address indexed agentTBA,
        address indexed reviewer,
        uint256 score,
        bytes32 evidenceHash,
        uint256 timestamp
    );

    /**
     * @notice Emitted when an agent is slashed (spam/malicious behavior)
     * @param agentTBA The Token Bound Account address of the slashed agent
     * @param evidenceHash Hash of the evidence for slashing
     */
    event Slashed(address indexed agentTBA, bytes32 evidenceHash);

    /**
     * @notice Gives feedback to an agent
     * @param agentTBA The Token Bound Account address of the agent
     * @param score The score (0-100). 0 = Spam, 100 = Critical finding
     * @param evidenceHash Hash of the evidence (IPFS CID hash)
     */
    function giveFeedback(
        address agentTBA,
        uint256 score,
        bytes32 evidenceHash
    ) external;

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
        returns (
            uint256 totalScore,
            uint256 feedbackCount,
            uint256 averageScore
        );

    /**
     * @notice Checks if an agent has been slashed
     * @param agentTBA The Token Bound Account address
     * @return True if the agent has been slashed
     */
    function isSlashed(address agentTBA) external view returns (bool);
}
