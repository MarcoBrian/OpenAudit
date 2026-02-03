// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";

import "../src/AgentRegistry.sol";
import "../src/BountyHive.sol";
import "../src/ReputationRegistry.sol";
import "../src/ERC6551Account.sol";
import "../src/mocks/MockENS.sol";
import "../src/mocks/MockERC6551Registry.sol";

/**
 * @title OpenAuditTest
 * @notice Comprehensive tests for the OpenAudit system
 */
contract OpenAuditTest is Test {
    // ═══════════════════════════════════════════════════════════════════════════
    // CONTRACTS
    // ═══════════════════════════════════════════════════════════════════════════

    MockERC6551Registry public erc6551Registry;
    ERC6551Account public accountImplementation;
    MockENSRegistry public ensRegistry;
    MockENSResolver public ensResolver;
    AgentRegistry public agentRegistry;
    BountyHive public bountyHive;
    ReputationRegistry public reputationRegistry;

    // ═══════════════════════════════════════════════════════════════════════════
    // ACTORS
    // ═══════════════════════════════════════════════════════════════════════════

    address public deployer = address(1);
    address public agentOwner = address(2);
    address public agentOperator = address(3);
    address public sponsor = address(4);
    address public judge = address(5);

    // ═══════════════════════════════════════════════════════════════════════════
    // CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════════

    // namehash("openaudit.eth") - pre-computed
    bytes32 public constant PARENT_NODE = keccak256(
        abi.encodePacked(
            keccak256(abi.encodePacked(bytes32(0), keccak256("eth"))),
            keccak256("openaudit")
        )
    );

    // ═══════════════════════════════════════════════════════════════════════════
    // SETUP
    // ═══════════════════════════════════════════════════════════════════════════

    function setUp() public {
        vm.startPrank(deployer);

        // Deploy ERC-6551 infrastructure
        erc6551Registry = new MockERC6551Registry();
        accountImplementation = new ERC6551Account();

        // Deploy mock ENS
        ensRegistry = new MockENSRegistry();
        ensResolver = new MockENSResolver();

        // Deploy core contracts
        agentRegistry = new AgentRegistry(
            address(erc6551Registry),
            address(accountImplementation),
            address(ensRegistry),
            address(ensResolver),
            PARENT_NODE
        );

        reputationRegistry = new ReputationRegistry();
        
        bountyHive = new BountyHive(
            address(agentRegistry),
            address(reputationRegistry)
        );

        // Configure permissions
        reputationRegistry.setAgentRegistry(address(agentRegistry));
        reputationRegistry.setAuthorizedReviewer(address(bountyHive), true);
        
        // Authorize ReputationRegistry and BountyHive to update ENS text records
        agentRegistry.setAuthorizedCaller(address(reputationRegistry), true);
        agentRegistry.setAuthorizedCaller(address(bountyHive), true);

        // Set up ENS parent node ownership
        ensRegistry.setNodeOwner(PARENT_NODE, address(agentRegistry));

        // Transfer BountyHive ownership to judge
        bountyHive.transferOwnership(judge);

        vm.stopPrank();

        // Fund actors
        vm.deal(agentOwner, 100 ether);
        vm.deal(sponsor, 100 ether);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // AGENT REGISTRY TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    function test_RegisterAgent() public {
        vm.startPrank(agentOwner);

        (uint256 agentId, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "claude-security",
            agentOperator
        );

        vm.stopPrank();

        // Verify agent was created
        assertEq(agentId, 1, "Agent ID should be 1");
        assertTrue(tba != address(0), "TBA should not be zero address");

        // Verify mappings
        assertEq(agentRegistry.agentTBA(agentId), tba, "TBA mapping incorrect");
        assertEq(agentRegistry.tbaToAgentId(tba), agentId, "TBA to agent mapping incorrect");
        assertEq(agentRegistry.agentOperator(agentId), agentOperator, "Operator incorrect");
        assertEq(agentRegistry.nameToAgentId("claude-security"), agentId, "Name mapping incorrect");
        assertEq(agentRegistry.agentIdToName(agentId), "claude-security", "ID to name mapping incorrect");

        // Verify NFT ownership
        assertEq(agentRegistry.ownerOf(agentId), agentOwner, "NFT owner incorrect");

        // Verify ENS resolution
        assertEq(agentRegistry.resolveName("claude-security"), tba, "ENS resolution incorrect");

        // Verify total agents
        assertEq(agentRegistry.totalAgents(), 1, "Total agents incorrect");
    }

    function test_RegisterAgent_DuplicateName() public {
        vm.startPrank(agentOwner);

        agentRegistry.registerAgent("ipfs://QmAgentMetadata", "agent1", agentOperator);

        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.AgentNameTaken.selector, "agent1"));
        agentRegistry.registerAgent("ipfs://QmAgentMetadata2", "agent1", agentOperator);

        vm.stopPrank();
    }

    function test_RegisterAgent_InvalidName() public {
        vm.startPrank(agentOwner);

        // Empty name
        vm.expectRevert(AgentRegistry.InvalidAgentName.selector);
        agentRegistry.registerAgent("ipfs://QmAgentMetadata", "", agentOperator);

        // Name too long (33 chars)
        vm.expectRevert(AgentRegistry.InvalidAgentName.selector);
        agentRegistry.registerAgent("ipfs://QmAgentMetadata", "123456789012345678901234567890123", agentOperator);

        vm.stopPrank();
    }

    function test_UpdateOperator() public {
        vm.startPrank(agentOwner);
        (uint256 agentId, ) = agentRegistry.registerAgent("ipfs://QmAgentMetadata", "agent1", agentOperator);

        address newOperator = address(10);
        agentRegistry.updateOperator(agentId, newOperator);

        assertEq(agentRegistry.agentOperator(agentId), newOperator, "Operator not updated");
        vm.stopPrank();
    }

    function test_GetAgent() public {
        vm.startPrank(agentOwner);
        (uint256 agentId, address tba) = agentRegistry.registerAgent("ipfs://QmAgentMetadata", "agent1", agentOperator);
        vm.stopPrank();

        (string memory name, address returnedTba, address owner, address operator) = agentRegistry.getAgent(agentId);

        assertEq(name, "agent1", "Name incorrect");
        assertEq(returnedTba, tba, "TBA incorrect");
        assertEq(owner, agentOwner, "Owner incorrect");
        assertEq(operator, agentOperator, "Operator incorrect");
    }

    function test_IsRegisteredAgent() public {
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent("ipfs://QmAgentMetadata", "agent1", agentOperator);
        vm.stopPrank();

        assertTrue(agentRegistry.isRegisteredAgent(tba), "Should be registered");
        assertFalse(agentRegistry.isRegisteredAgent(address(999)), "Should not be registered");
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BOUNTY HIVE TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    function test_CreateBounty() public {
        vm.startPrank(sponsor);

        uint256 deadline = block.timestamp + 7 days;
        uint256 bountyId = bountyHive.createBounty{value: 1 ether}(
            address(0xDEAD),
            deadline
        );

        vm.stopPrank();

        assertEq(bountyId, 1, "Bounty ID should be 1");
        assertEq(bountyHive.totalBounties(), 1, "Total bounties incorrect");

        (
            address bSponsor,
            address target,
            uint256 reward,
            uint256 createdAt,
            uint256 bDeadline,
            BountyHive.BountyStatus status,
            address winnerTBA,
            BountyHive.Severity severity
        ) = bountyHive.bounties(bountyId);

        assertEq(bSponsor, sponsor, "Sponsor incorrect");
        assertEq(target, address(0xDEAD), "Target incorrect");
        assertEq(reward, 1 ether, "Reward incorrect");
        assertEq(bDeadline, deadline, "Deadline incorrect");
        assertEq(uint8(status), uint8(BountyHive.BountyStatus.Active), "Status should be Active");
    }

    function test_CreateBounty_InsufficientReward() public {
        vm.startPrank(sponsor);

        vm.expectRevert(BountyHive.InsufficientReward.selector);
        bountyHive.createBounty{value: 0.001 ether}(address(0xDEAD), block.timestamp + 1 days);

        vm.stopPrank();
    }

    function test_CancelBounty() public {
        vm.startPrank(sponsor);

        uint256 balanceBefore = sponsor.balance;
        uint256 bountyId = bountyHive.createBounty{value: 1 ether}(
            address(0xDEAD),
            block.timestamp + 7 days
        );

        bountyHive.cancelBounty(bountyId);

        uint256 balanceAfter = sponsor.balance;

        vm.stopPrank();

        // Balance should be restored (minus gas)
        assertEq(balanceAfter, balanceBefore, "Balance should be restored");

        (, , , , , BountyHive.BountyStatus status, , ) = bountyHive.bounties(bountyId);
        assertEq(uint8(status), uint8(BountyHive.BountyStatus.Cancelled), "Status should be Cancelled");
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // FULL WORKFLOW TEST
    // ═══════════════════════════════════════════════════════════════════════════

    function test_FullWorkflow() public {
        // 1. Register an agent
        vm.startPrank(agentOwner);
        (uint256 agentId, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "claude-auditor",
            agentOperator
        );
        vm.stopPrank();

        // 2. Create a bounty
        vm.startPrank(sponsor);
        uint256 bountyId = bountyHive.createBounty{value: 1 ether}(
            address(0xDEAD),
            block.timestamp + 7 days
        );
        vm.stopPrank();

        // 3-4. Commit and reveal finding
        string memory reportCID = "QmReportCID123";
        _commitAndRevealFinding(tba, bountyId, reportCID, "QmPocTestCID456", 12345);

        // 5. Judge resolves the bounty
        uint256 tbaBalanceBefore = tba.balance;

        vm.prank(judge);
        bountyHive.resolveBounty(bountyId, tba, BountyHive.Severity.Critical);

        // Verify reward was transferred
        assertEq(tba.balance - tbaBalanceBefore, 1 ether, "Reward not transferred");

        // 6. Verify bounty status and reputation
        _verifyBountyResolved(bountyId, tba);
        _verifyReputation(tba, 100, 1, 100);

        // 7. Verify ENS text records were updated
        _verifyENSRecords(agentId, "100", reportCID);
    }

    function _commitAndRevealFinding(
        address tba,
        uint256 bountyId,
        string memory reportCID,
        string memory pocTestCID,
        uint256 salt
    ) internal {
        bytes32 commitHash = bountyHive.computeCommitmentHash(tba, reportCID, salt);

        vm.prank(tba);
        bountyHive.commitFinding(bountyId, commitHash);

        vm.prank(tba);
        bountyHive.revealFinding(bountyId, reportCID, pocTestCID, salt);
    }

    function _verifyBountyResolved(uint256 bountyId, address expectedWinner) internal view {
        (, , , , , BountyHive.BountyStatus status, address winner, ) = 
            bountyHive.bounties(bountyId);

        assertEq(uint8(status), uint8(BountyHive.BountyStatus.Resolved), "Status should be Resolved");
        assertEq(winner, expectedWinner, "Winner incorrect");
    }

    function _verifyReputation(
        address tba,
        uint256 expectedTotal,
        uint256 expectedCount,
        uint256 expectedAvg
    ) internal view {
        (uint256 totalScore, uint256 feedbackCount, uint256 avgScore) = reputationRegistry.getScore(tba);
        assertEq(totalScore, expectedTotal, "Total score incorrect");
        assertEq(feedbackCount, expectedCount, "Feedback count incorrect");
        assertEq(avgScore, expectedAvg, "Average score incorrect");
    }

    function _verifyENSRecords(uint256 agentId, string memory expectedScore, string memory expectedLastAudit) internal view {
        bytes32 agentNode = agentRegistry.agentENSNode(agentId);
        assertEq(ensResolver.text(agentNode, "score"), expectedScore, "ENS score record incorrect");
        assertEq(ensResolver.text(agentNode, "last_audit"), expectedLastAudit, "ENS last_audit record incorrect");
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // SPAM/SLASH TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    function test_MarkAsSpam() public {
        // Register agent
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "spam-agent",
            agentOperator
        );
        vm.stopPrank();

        // Create bounty
        vm.startPrank(sponsor);
        uint256 bountyId = bountyHive.createBounty{value: 1 ether}(
            address(0xDEAD),
            block.timestamp + 7 days
        );
        vm.stopPrank();

        // Agent commits and reveals a spam finding
        string memory reportCID = "QmSpamReport";
        uint256 salt = 99999;
        bytes32 commitHash = bountyHive.computeCommitmentHash(tba, reportCID, salt);

        vm.prank(tba);
        bountyHive.commitFinding(bountyId, commitHash);

        vm.prank(tba);
        bountyHive.revealFinding(bountyId, reportCID, "QmFakePoC", salt);

        // Judge marks as spam
        vm.prank(judge);
        bountyHive.markAsSpam(bountyId, tba);

        // Verify agent was slashed
        assertTrue(reputationRegistry.isSlashed(tba), "Agent should be slashed");

        (uint256 totalScore, , ) = reputationRegistry.getScore(tba);
        assertEq(totalScore, 0, "Score should be 0 after slash");
    }

    function test_SlashedAgentCannotGetMoreFeedback() public {
        // Register agent
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "bad-agent",
            agentOperator
        );
        vm.stopPrank();

        // Slash the agent
        vm.prank(deployer);
        reputationRegistry.giveFeedback(tba, 0, bytes32(0));

        // Try to give positive feedback
        vm.prank(deployer);
        vm.expectRevert(ReputationRegistry.AgentSlashed.selector);
        reputationRegistry.giveFeedback(tba, 50, bytes32(0));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMMIT-REVEAL EDGE CASES
    // ═══════════════════════════════════════════════════════════════════════════

    function test_InvalidReveal() public {
        // Register agent
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "agent1",
            agentOperator
        );
        vm.stopPrank();

        // Create bounty
        vm.startPrank(sponsor);
        uint256 bountyId = bountyHive.createBounty{value: 1 ether}(
            address(0xDEAD),
            block.timestamp + 7 days
        );
        vm.stopPrank();

        // Commit with one CID
        bytes32 commitHash = bountyHive.computeCommitmentHash(tba, "QmCorrectCID", 123);
        vm.prank(tba);
        bountyHive.commitFinding(bountyId, commitHash);

        // Try to reveal with different CID
        vm.prank(tba);
        vm.expectRevert(BountyHive.InvalidReveal.selector);
        bountyHive.revealFinding(bountyId, "QmWrongCID", "QmPoC", 123);

        // Try to reveal with wrong salt
        vm.prank(tba);
        vm.expectRevert(BountyHive.InvalidReveal.selector);
        bountyHive.revealFinding(bountyId, "QmCorrectCID", "QmPoC", 456);
    }

    function test_DoubleReveal() public {
        // Register agent
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "agent1",
            agentOperator
        );
        vm.stopPrank();

        // Create bounty
        vm.startPrank(sponsor);
        uint256 bountyId = bountyHive.createBounty{value: 1 ether}(
            address(0xDEAD),
            block.timestamp + 7 days
        );
        vm.stopPrank();

        // Commit and reveal
        bytes32 commitHash = bountyHive.computeCommitmentHash(tba, "QmCID", 123);
        vm.prank(tba);
        bountyHive.commitFinding(bountyId, commitHash);

        vm.prank(tba);
        bountyHive.revealFinding(bountyId, "QmCID", "QmPoC", 123);

        // Try to reveal again
        vm.prank(tba);
        vm.expectRevert(BountyHive.CommitmentAlreadyRevealed.selector);
        bountyHive.revealFinding(bountyId, "QmCID", "QmPoC", 123);
    }

    function test_NonAgentCannotCommit() public {
        // Create bounty
        vm.startPrank(sponsor);
        uint256 bountyId = bountyHive.createBounty{value: 1 ether}(
            address(0xDEAD),
            block.timestamp + 7 days
        );
        vm.stopPrank();

        // Try to commit from non-agent address
        vm.prank(address(999));
        vm.expectRevert(BountyHive.NotRegisteredAgent.selector);
        bountyHive.commitFinding(bountyId, bytes32("test"));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // REPUTATION TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    function test_MultipleFindings() public {
        // Register agent
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "prolific-agent",
            agentOperator
        );
        vm.stopPrank();

        // Give multiple feedback scores
        vm.startPrank(deployer);
        reputationRegistry.giveFeedback(tba, 100, bytes32("finding1"));
        reputationRegistry.giveFeedback(tba, 50, bytes32("finding2"));
        reputationRegistry.giveFeedback(tba, 75, bytes32("finding3"));
        vm.stopPrank();

        (uint256 totalScore, uint256 feedbackCount, uint256 avgScore) = reputationRegistry.getScore(tba);

        assertEq(totalScore, 225, "Total score should be 225");
        assertEq(feedbackCount, 3, "Feedback count should be 3");
        assertEq(avgScore, 75, "Average score should be 75");

        // Check feedback history
        ReputationRegistry.FeedbackEntry[] memory history = reputationRegistry.getFeedbackHistory(tba);
        assertEq(history.length, 3, "Should have 3 feedback entries");
    }

    function test_UnauthorizedReviewer() public {
        vm.prank(address(999));
        vm.expectRevert(ReputationRegistry.NotAuthorizedReviewer.selector);
        reputationRegistry.giveFeedback(address(1), 50, bytes32(0));
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // TBA FUNCTIONALITY TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    function test_TBAReceivesETH() public {
        // Register agent
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "agent1",
            agentOperator
        );
        vm.stopPrank();

        // Send ETH to TBA
        vm.deal(address(this), 1 ether);
        (bool success, ) = tba.call{value: 1 ether}("");
        assertTrue(success, "TBA should receive ETH");
        assertEq(tba.balance, 1 ether, "TBA balance incorrect");
    }

    function test_TBAExecute() public {
        // Register agent
        vm.startPrank(agentOwner);
        (, address tba) = agentRegistry.registerAgent(
            "ipfs://QmAgentMetadata",
            "agent1",
            agentOperator
        );
        vm.stopPrank();

        // Fund the TBA
        vm.deal(tba, 1 ether);

        // Agent owner executes a transfer from TBA
        address recipient = address(999);
        uint256 recipientBalanceBefore = recipient.balance;

        vm.prank(agentOwner);
        ERC6551Account(payable(tba)).execute(
            recipient,
            0.5 ether,
            "",
            0 // CALL operation
        );

        assertEq(recipient.balance - recipientBalanceBefore, 0.5 ether, "Transfer should succeed");
    }
}
