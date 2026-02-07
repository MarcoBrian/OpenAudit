// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/OpenAuditRegistry.sol";

contract OpenAuditRegistryTest is Test {
    OpenAuditRegistry public registry;

    address public deployer = address(1);
    address public agent1   = address(2);
    address public agent2   = address(3);
    address public sponsor  = address(4);

    function setUp() public {
        vm.prank(deployer);
        registry = new OpenAuditRegistry();

        vm.deal(sponsor, 100 ether);
        vm.deal(agent1, 1 ether);
    }

    // ── Agent Registration ───────────────────────────────────────────────

    function test_RegisterAgent() public {
        vm.prank(agent1);
        uint256 id = registry.registerAgent("alice-auditor", "ipfs://QmMeta1");

        assertEq(id, 1);
        assertTrue(registry.isRegistered(agent1));
        assertEq(registry.addressToAgentId(agent1), 1);

        OpenAuditRegistry.Agent memory a = registry.getAgent(1);
        assertEq(a.owner, agent1);
        assertEq(a.name, "alice-auditor");
        assertEq(a.metadataURI, "ipfs://QmMeta1");
    }

    function test_RegisterAgent_Duplicate() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m");

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.AlreadyRegistered.selector);
        registry.registerAgent("a2", "ipfs://m");
    }

    function test_RegisterAgent_EmptyName() public {
        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.EmptyValue.selector);
        registry.registerAgent("", "ipfs://m");
    }

    // ── Bounty Creation ──────────────────────────────────────────────────

    function test_CreateBounty() public {
        vm.prank(sponsor);
        uint256 id = registry.createBounty{value: 1 ether}(
            address(0xBEEF),
            block.timestamp + 7 days
        );

        assertEq(id, 1);

        (
            address s, address t, uint256 r, uint256 d,
            bool active, bool resolved, address w
        ) = registry.bounties(id);

        assertEq(s, sponsor);
        assertEq(t, address(0xBEEF));
        assertEq(r, 1 ether);
        assertTrue(active);
        assertFalse(resolved);
        assertEq(w, address(0));
    }

    function test_CreateBounty_InsufficientReward() public {
        vm.prank(sponsor);
        vm.expectRevert(OpenAuditRegistry.InsufficientReward.selector);
        registry.createBounty{value: 0.0001 ether}(address(0xBEEF), block.timestamp + 1 days);
    }

    function test_CancelBounty() public {
        vm.startPrank(sponsor);
        uint256 balBefore = sponsor.balance;
        uint256 id = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);
        registry.cancelBounty(id);
        vm.stopPrank();

        assertEq(sponsor.balance, balBefore);

        (, , , , bool active, , ) = registry.bounties(id);
        assertFalse(active);
    }

    // ── Submit Finding ───────────────────────────────────────────────────

    function test_SubmitFinding() public {
        // Register agent
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m");

        // Create bounty
        vm.prank(sponsor);
        uint256 bountyId = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);

        // Submit
        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmReportCID123");

        // Verify
        (address fa, string memory cid, uint256 at) = registry.findings(bountyId, agent1);
        assertEq(fa, agent1);
        assertEq(cid, "QmReportCID123");
        assertTrue(at > 0);

        address[] memory subs = registry.getBountySubmitters(bountyId);
        assertEq(subs.length, 1);
        assertEq(subs[0], agent1);

        string[] memory cids = registry.getAgentReportCIDs(agent1);
        assertEq(cids.length, 1);
        assertEq(cids[0], "QmReportCID123");
    }

    function test_SubmitFinding_NotRegistered() public {
        vm.prank(sponsor);
        uint256 bountyId = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.NotRegistered.selector);
        registry.submitFinding(bountyId, "QmCID");
    }

    function test_SubmitFinding_EmptyCID() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m");

        vm.prank(sponsor);
        uint256 bountyId = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.EmptyValue.selector);
        registry.submitFinding(bountyId, "");
    }

    function test_SubmitFinding_Duplicate() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m");

        vm.prank(sponsor);
        uint256 bountyId = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);

        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmCID1");

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.AlreadySubmitted.selector);
        registry.submitFinding(bountyId, "QmCID2");
    }

    // ── Resolve Bounty ───────────────────────────────────────────────────

    function test_FullWorkflow() public {
        // Register
        vm.prank(agent1);
        registry.registerAgent("alice", "ipfs://m");

        // Bounty
        vm.prank(sponsor);
        uint256 bountyId = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);

        // Submit finding
        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmReport123");

        // Resolve
        uint256 balBefore = agent1.balance;
        vm.prank(deployer);
        registry.resolveBounty(bountyId, agent1, 80);

        // Reward paid
        assertEq(agent1.balance - balBefore, 1 ether);

        // Bounty closed
        (, , , , bool active, bool resolved, address winner) = registry.bounties(bountyId);
        assertFalse(active);
        assertTrue(resolved);
        assertEq(winner, agent1);

        // Reputation updated
        (uint256 total, uint256 count, uint256 avg) = registry.getReputation(agent1);
        assertEq(total, 80);
        assertEq(count, 1);
        assertEq(avg, 80);
    }

    function test_ResolveBounty_NoFinding() public {
        vm.prank(sponsor);
        uint256 bountyId = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);

        vm.prank(deployer);
        vm.expectRevert(OpenAuditRegistry.NoFinding.selector);
        registry.resolveBounty(bountyId, agent1, 50);
    }

    function test_MultipleAgentsMultipleFindings() public {
        // Register two agents
        vm.prank(agent1);
        registry.registerAgent("alice", "ipfs://m1");
        vm.prank(agent2);
        registry.registerAgent("bob", "ipfs://m2");

        // Create bounty
        vm.prank(sponsor);
        uint256 bountyId = registry.createBounty{value: 2 ether}(address(0xBEEF), block.timestamp + 7 days);

        // Both submit
        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmAliceReport");
        vm.prank(agent2);
        registry.submitFinding(bountyId, "QmBobReport");

        address[] memory subs = registry.getBountySubmitters(bountyId);
        assertEq(subs.length, 2);

        // Resolve with agent2 as winner
        vm.prank(deployer);
        registry.resolveBounty(bountyId, agent2, 100);

        (, , , , , bool resolved, address winner) = registry.bounties(bountyId);
        assertTrue(resolved);
        assertEq(winner, agent2);
    }
}
