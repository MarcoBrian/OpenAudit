// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/OpenAuditRegistry.sol";
import "../src/ERC6551Account.sol";
import "../src/mocks/MockERC6551Registry.sol";
import "../src/mocks/MockENS.sol";

contract OpenAuditRegistryTest is Test {
    OpenAuditRegistry public registry;
    ERC6551Account    public tbaImpl;
    MockERC6551Registry public erc6551Reg;
    MockENSRegistry   public ensReg;
    MockENSResolver   public ensRes;

    bytes32 public constant PARENT_NODE = keccak256("openaudit.eth");

    address public deployer = address(1);
    address public agent1   = address(2);
    address public agent2   = address(3);
    address public sponsor  = address(4);

    function setUp() public {
        vm.startPrank(deployer);

        // Deploy mock infrastructure
        tbaImpl   = new ERC6551Account();
        erc6551Reg = new MockERC6551Registry();
        ensReg    = new MockENSRegistry();
        ensRes    = new MockENSResolver();

        // Deploy registry
        registry = new OpenAuditRegistry(
            address(erc6551Reg),
            address(tbaImpl),
            address(ensReg),
            address(ensRes),
            PARENT_NODE
        );

        // Give the registry contract ownership of the ENS parent node
        ensReg.setNodeOwner(PARENT_NODE, address(registry));

        vm.stopPrank();

        vm.deal(sponsor, 100 ether);
        vm.deal(agent1, 1 ether);
    }

    // ── Agent Registration (with TBA + ENS) ─────────────────────────────

    function test_RegisterAgent() public {
        vm.prank(agent1);
        (uint256 id, address tba) = registry.registerAgent("alice-auditor", "ipfs://QmMeta1");

        assertEq(id, 1);
        assertTrue(tba != address(0));
        assertTrue(registry.isRegistered(agent1));
        assertTrue(registry.isRegistered(tba)); // TBA also counts as registered
        assertEq(registry.ownerToAgentId(agent1), 1);
        assertEq(registry.tbaToAgentId(tba), 1);

        OpenAuditRegistry.Agent memory a = registry.getAgent(1);
        assertEq(a.owner, agent1);
        assertEq(a.tba, tba);
        assertEq(a.name, "alice-auditor");
        assertEq(a.metadataURI, "ipfs://QmMeta1");

        // Agent NFT minted
        assertEq(registry.ownerOf(1), agent1);
    }

    function test_RegisterAgent_ENS() public {
        vm.prank(agent1);
        (uint256 id, address tba) = registry.registerAgent("alice", "ipfs://QmMeta1");

        // ENS subdomain resolves to TBA
        bytes32 labelHash = keccak256(bytes("alice"));
        bytes32 node = keccak256(abi.encodePacked(PARENT_NODE, labelHash));

        assertEq(ensRes.addr(node), tba);
        assertEq(keccak256(bytes(ensRes.text(node, "score"))), keccak256(bytes("0")));

        // resolveName helper works
        assertEq(registry.resolveName("alice"), tba);
    }

    function test_RegisterAgent_Duplicate() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m");

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.AlreadyRegistered.selector);
        registry.registerAgent("a2", "ipfs://m");
    }

    function test_RegisterAgent_NameTaken() public {
        vm.prank(agent1);
        registry.registerAgent("coolname", "ipfs://m");

        vm.prank(agent2);
        vm.expectRevert(OpenAuditRegistry.NameTaken.selector);
        registry.registerAgent("coolname", "ipfs://m2");
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

    // ── Resolve Bounty + ENS Score Update ────────────────────────────────

    function test_FullWorkflow() public {
        // Register
        vm.prank(agent1);
        (uint256 agentId, address tba) = registry.registerAgent("alice", "ipfs://m");

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

        // ENS score text record updated
        bytes32 node = registry.agentENSNode(agentId);
        assertEq(keccak256(bytes(ensRes.text(node, "score"))), keccak256(bytes("80")));
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

    function test_ResolveENS_AvgScoreUpdates() public {
        // Register agent
        vm.prank(agent1);
        (uint256 agentId, ) = registry.registerAgent("alice", "ipfs://m");

        // Bounty 1
        vm.prank(sponsor);
        uint256 b1 = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);
        vm.prank(agent1);
        registry.submitFinding(b1, "QmR1");
        vm.prank(deployer);
        registry.resolveBounty(b1, agent1, 60);

        // Bounty 2
        vm.prank(sponsor);
        uint256 b2 = registry.createBounty{value: 1 ether}(address(0xBEEF), block.timestamp + 7 days);
        vm.prank(agent1);
        registry.submitFinding(b2, "QmR2");
        vm.prank(deployer);
        registry.resolveBounty(b2, agent1, 100);

        // avg = (60 + 100) / 2 = 80
        (uint256 total, uint256 count, uint256 avg) = registry.getReputation(agent1);
        assertEq(total, 160);
        assertEq(count, 2);
        assertEq(avg, 80);

        // ENS text record should reflect avg
        bytes32 node = registry.agentENSNode(agentId);
        assertEq(keccak256(bytes(ensRes.text(node, "score"))), keccak256(bytes("80")));
    }
}
