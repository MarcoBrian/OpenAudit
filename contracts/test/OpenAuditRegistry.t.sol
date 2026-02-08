// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/OpenAuditRegistry.sol";
import "../src/ERC6551Account.sol";
import "../src/mocks/MockERC6551Registry.sol";
import "../src/mocks/MockENS.sol";
import "../src/mocks/MockERC20.sol";

contract OpenAuditRegistryTest is Test {
    OpenAuditRegistry public registry;
    ERC6551Account    public tbaImpl;
    MockERC6551Registry public erc6551Reg;
    MockENSRegistry   public ensReg;
    MockENSResolver   public ensRes;
    MockERC20         public usdc;

    bytes32 public constant PARENT_NODE = keccak256("openaudit.eth");

    address public deployer = address(1);
    address public agent1   = address(2);
    address public agent2   = address(3);
    address public sponsor  = address(4);
    address public relay    = address(5);

    uint256 public constant BOUNTY_REWARD = 1000e6; // 1000 USDC

    function setUp() public {
        vm.startPrank(deployer);

        // Deploy mock infrastructure
        tbaImpl    = new ERC6551Account();
        erc6551Reg = new MockERC6551Registry();
        ensReg     = new MockENSRegistry();
        ensRes     = new MockENSResolver();
        usdc       = new MockERC20("USD Coin", "USDC", 6);

        // Deploy registry with USDC and relay
        registry = new OpenAuditRegistry(
            address(erc6551Reg),
            address(tbaImpl),
            address(ensReg),
            address(ensRes),
            PARENT_NODE,
            address(usdc),
            relay
        );

        // Give the registry contract ownership of the ENS parent node
        ensReg.setNodeOwner(PARENT_NODE, address(registry));

        vm.stopPrank();

        // Fund sponsor with USDC
        usdc.mint(sponsor, 100_000e6); // 100,000 USDC
        vm.deal(agent1, 1 ether);
    }

    // -- Agent Registration (with TBA + ENS + payout_chain) ------

    function test_RegisterAgent() public {
        vm.prank(agent1);
        (uint256 id, address tba) = registry.registerAgent("alice-auditor", "ipfs://QmMeta1", "base");

        assertEq(id, 1);
        assertTrue(tba != address(0));
        assertTrue(registry.isRegistered(agent1));
        assertTrue(registry.isRegistered(tba));
        assertEq(registry.ownerToAgentId(agent1), 1);
        assertEq(registry.tbaToAgentId(tba), 1);

        OpenAuditRegistry.Agent memory a = registry.getAgent(1);
        assertEq(a.owner, agent1);
        assertEq(a.tba, tba);
        assertEq(a.name, "alice-auditor");
        assertEq(a.metadataURI, "ipfs://QmMeta1");

        assertEq(registry.ownerOf(1), agent1);
    }

    function test_RegisterAgent_ENS() public {
        vm.prank(agent1);
        (uint256 id, address tba) = registry.registerAgent("alice", "ipfs://QmMeta1", "base");

        bytes32 labelHash = keccak256(bytes("alice"));
        bytes32 node = keccak256(abi.encodePacked(PARENT_NODE, labelHash));

        assertEq(ensRes.addr(node), tba);
        assertEq(keccak256(bytes(ensRes.text(node, "score"))), keccak256(bytes("0")));
        assertEq(keccak256(bytes(ensRes.text(node, "payout_chain"))), keccak256(bytes("base")));
        assertEq(registry.resolveName("alice"), tba);
    }

    function test_RegisterAgent_PayoutChain() public {
        vm.prank(agent1);
        (uint256 id, ) = registry.registerAgent("alice", "ipfs://QmMeta1", "arbitrum");

        string memory chain = registry.getPayoutChain(id);
        assertEq(keccak256(bytes(chain)), keccak256(bytes("arbitrum")));
    }

    function test_RegisterAgent_EmptyPayoutChain() public {
        vm.prank(agent1);
        (uint256 id, ) = registry.registerAgent("alice", "ipfs://QmMeta1", "");

        string memory chain = registry.getPayoutChain(id);
        assertEq(bytes(chain).length, 0);
    }

    function test_SetPayoutChain() public {
        vm.prank(agent1);
        (uint256 id, ) = registry.registerAgent("alice", "ipfs://QmMeta1", "base");

        vm.prank(agent1);
        registry.setPayoutChain(id, "ethereum");

        string memory chain = registry.getPayoutChain(id);
        assertEq(keccak256(bytes(chain)), keccak256(bytes("ethereum")));
    }

    function test_SetPayoutChain_NotOwner() public {
        vm.prank(agent1);
        (uint256 id, ) = registry.registerAgent("alice", "ipfs://QmMeta1", "base");

        vm.prank(agent2);
        vm.expectRevert(OpenAuditRegistry.NotRegistered.selector);
        registry.setPayoutChain(id, "ethereum");
    }

    function test_RegisterAgent_Duplicate() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m", "base");

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.AlreadyRegistered.selector);
        registry.registerAgent("a2", "ipfs://m", "base");
    }

    function test_RegisterAgent_NameTaken() public {
        vm.prank(agent1);
        registry.registerAgent("coolname", "ipfs://m", "base");

        vm.prank(agent2);
        vm.expectRevert(OpenAuditRegistry.NameTaken.selector);
        registry.registerAgent("coolname", "ipfs://m2", "ethereum");
    }

    function test_RegisterAgent_EmptyName() public {
        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.EmptyValue.selector);
        registry.registerAgent("", "ipfs://m", "base");
    }

    // -- Bounty Creation (USDC) -----------------------------------

    function test_CreateBounty() public {
        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 id = registry.createBounty(
            address(0xBEEF),
            block.timestamp + 7 days,
            BOUNTY_REWARD
        );
        vm.stopPrank();

        assertEq(id, 1);

        (
            address s, address t, uint256 r, uint256 d,
            bool active, bool resolved, address w
        ) = registry.bounties(id);

        assertEq(s, sponsor);
        assertEq(t, address(0xBEEF));
        assertEq(r, BOUNTY_REWARD);
        assertTrue(active);
        assertFalse(resolved);
        assertEq(w, address(0));
        assertEq(usdc.balanceOf(address(registry)), BOUNTY_REWARD);
    }

    function test_CreateBounty_InsufficientReward() public {
        vm.startPrank(sponsor);
        usdc.approve(address(registry), 100);
        vm.expectRevert(OpenAuditRegistry.InsufficientReward.selector);
        registry.createBounty(address(0xBEEF), block.timestamp + 1 days, 100);
        vm.stopPrank();
    }

    function test_CreateBounty_NoApproval() public {
        vm.prank(sponsor);
        vm.expectRevert();
        registry.createBounty(address(0xBEEF), block.timestamp + 1 days, BOUNTY_REWARD);
    }

    function test_CancelBounty() public {
        vm.startPrank(sponsor);
        uint256 balBefore = usdc.balanceOf(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 id = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        registry.cancelBounty(id);
        vm.stopPrank();

        assertEq(usdc.balanceOf(sponsor), balBefore);
        assertEq(usdc.balanceOf(address(registry)), 0);

        (, , , , bool active, , ) = registry.bounties(id);
        assertFalse(active);
    }

    // -- Submit Finding -------------------------------------------

    function test_SubmitFinding() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m", "base");

        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 bountyId = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();

        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmReportCID123");

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
        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 bountyId = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.NotRegistered.selector);
        registry.submitFinding(bountyId, "QmCID");
    }

    function test_SubmitFinding_EmptyCID() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m", "base");

        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 bountyId = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.EmptyValue.selector);
        registry.submitFinding(bountyId, "");
    }

    function test_SubmitFinding_Duplicate() public {
        vm.prank(agent1);
        registry.registerAgent("a1", "ipfs://m", "base");

        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 bountyId = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();

        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmCID1");

        vm.prank(agent1);
        vm.expectRevert(OpenAuditRegistry.AlreadySubmitted.selector);
        registry.submitFinding(bountyId, "QmCID2");
    }

    // -- Resolve Bounty + USDC Payout + Settlement ----------------

    function test_FullWorkflow() public {
        vm.prank(agent1);
        (uint256 agentId, address tba) = registry.registerAgent("alice", "ipfs://m", "base");

        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 bountyId = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();

        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmReport123");

        uint256 relayBalBefore = usdc.balanceOf(relay);
        vm.prank(deployer);
        registry.resolveBounty(bountyId, agent1, 80);

        assertEq(usdc.balanceOf(relay) - relayBalBefore, BOUNTY_REWARD);
        assertEq(usdc.balanceOf(address(registry)), 0);

        (, , , , bool active, bool resolved, address winner) = registry.bounties(bountyId);
        assertFalse(active);
        assertTrue(resolved);
        assertEq(winner, agent1);

        (uint256 total, uint256 count, uint256 avg) = registry.getReputation(agent1);
        assertEq(total, 80);
        assertEq(count, 1);
        assertEq(avg, 80);

        bytes32 node = registry.agentENSNode(agentId);
        assertEq(keccak256(bytes(ensRes.text(node, "score"))), keccak256(bytes("80")));
    }

    function test_FullWorkflow_NoRelay() public {
        vm.startPrank(deployer);
        OpenAuditRegistry regNoRelay = new OpenAuditRegistry(
            address(erc6551Reg),
            address(tbaImpl),
            address(ensReg),
            address(ensRes),
            PARENT_NODE,
            address(usdc),
            address(0)
        );
        ensReg.setNodeOwner(PARENT_NODE, address(regNoRelay));
        vm.stopPrank();

        vm.prank(agent1);
        regNoRelay.registerAgent("alice", "ipfs://m", "base");

        vm.startPrank(sponsor);
        usdc.approve(address(regNoRelay), BOUNTY_REWARD);
        uint256 bountyId = regNoRelay.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();

        vm.prank(agent1);
        regNoRelay.submitFinding(bountyId, "QmR1");

        uint256 agentBalBefore = usdc.balanceOf(agent1);
        vm.prank(deployer);
        regNoRelay.resolveBounty(bountyId, agent1, 80);

        assertEq(usdc.balanceOf(agent1) - agentBalBefore, BOUNTY_REWARD);
    }

    function test_ResolveBounty_NoFinding() public {
        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 bountyId = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();

        vm.prank(deployer);
        vm.expectRevert(OpenAuditRegistry.NoFinding.selector);
        registry.resolveBounty(bountyId, agent1, 50);
    }

    function test_MultipleAgentsMultipleFindings() public {
        vm.prank(agent1);
        registry.registerAgent("alice", "ipfs://m1", "base");
        vm.prank(agent2);
        registry.registerAgent("bob", "ipfs://m2", "arbitrum");

        vm.startPrank(sponsor);
        usdc.approve(address(registry), 2000e6);
        uint256 bountyId = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, 2000e6);
        vm.stopPrank();

        vm.prank(agent1);
        registry.submitFinding(bountyId, "QmAliceReport");
        vm.prank(agent2);
        registry.submitFinding(bountyId, "QmBobReport");

        address[] memory subs = registry.getBountySubmitters(bountyId);
        assertEq(subs.length, 2);

        vm.prank(deployer);
        registry.resolveBounty(bountyId, agent2, 100);

        (, , , , , bool resolved, address winner) = registry.bounties(bountyId);
        assertTrue(resolved);
        assertEq(winner, agent2);
        assertEq(usdc.balanceOf(relay), 2000e6);
    }

    function test_ResolveENS_AvgScoreUpdates() public {
        vm.prank(agent1);
        (uint256 agentId, ) = registry.registerAgent("alice", "ipfs://m", "base");

        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 b1 = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();
        vm.prank(agent1);
        registry.submitFinding(b1, "QmR1");
        vm.prank(deployer);
        registry.resolveBounty(b1, agent1, 60);

        vm.startPrank(sponsor);
        usdc.approve(address(registry), BOUNTY_REWARD);
        uint256 b2 = registry.createBounty(address(0xBEEF), block.timestamp + 7 days, BOUNTY_REWARD);
        vm.stopPrank();
        vm.prank(agent1);
        registry.submitFinding(b2, "QmR2");
        vm.prank(deployer);
        registry.resolveBounty(b2, agent1, 100);

        (uint256 total, uint256 count, uint256 avg) = registry.getReputation(agent1);
        assertEq(total, 160);
        assertEq(count, 2);
        assertEq(avg, 80);

        bytes32 node = registry.agentENSNode(agentId);
        assertEq(keccak256(bytes(ensRes.text(node, "score"))), keccak256(bytes("80")));
    }

    // -- Payout Relay Admin ---------------------------------------

    function test_SetPayoutRelay() public {
        address newRelay = address(0xDEAD);
        vm.prank(deployer);
        registry.setPayoutRelay(newRelay);
        assertEq(registry.payoutRelay(), newRelay);
    }

    function test_SetPayoutRelay_NotOwner() public {
        vm.prank(agent1);
        vm.expectRevert();
        registry.setPayoutRelay(address(0xDEAD));
    }

    // -- USDC reference -------------------------------------------

    function test_USDCAddress() public view {
        assertEq(address(registry.usdc()), address(usdc));
    }

    function test_MinReward() public view {
        assertEq(registry.MIN_REWARD(), 1e6);
    }
}
