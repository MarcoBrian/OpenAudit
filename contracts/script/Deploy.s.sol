// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";

import "../src/AgentRegistry.sol";
import "../src/BountyHive.sol";
import "../src/ReputationRegistry.sol";
import "../src/ERC6551Account.sol";
import "../src/mocks/MockENS.sol";
import "../src/mocks/MockERC6551Registry.sol";

/**
 * @title DeployOpenAudit
 * @notice Deployment script for the OpenAudit system
 */
contract DeployOpenAudit is Script {
    // ═══════════════════════════════════════════════════════════════════════════
    // DEPLOYED ADDRESSES (to be filled after deployment)
    // ═══════════════════════════════════════════════════════════════════════════

    // Canonical ERC-6551 Registry (same on all EVM chains)
    address constant ERC6551_REGISTRY = 0x000000006551c19487814612e58FE06813775758;

    // Sepolia ENS addresses
    address constant SEPOLIA_ENS_REGISTRY = 0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e;
    address constant SEPOLIA_ENS_RESOLVER = 0x8FADE66B79cC9f707aB26799354482EB93a5B7dD;

    // namehash("openaudit.eth")
    bytes32 constant PARENT_NODE = keccak256(
        abi.encodePacked(
            keccak256(abi.encodePacked(bytes32(0), keccak256("eth"))),
            keccak256("openaudit")
        )
    );

    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);
        address judgeAddress = vm.envOr("JUDGE_ADDRESS", deployer);

        console.log("Deployer:", deployer);
        console.log("Judge:", judgeAddress);
        console.log("Chain ID:", block.chainid);

        vm.startBroadcast(deployerPrivateKey);

        // Determine if we're on a network that has ENS (Sepolia) or requires mocks
        bool isSepolia = block.chainid == 11155111;
        bool isBaseSepolia = block.chainid == 84532;
        bool isLocal = block.chainid == 31337;

        address erc6551Registry;
        address ensRegistry;
        address ensResolver;

        if (isSepolia) {
            console.log("Deploying to Sepolia with real ENS...");
            erc6551Registry = ERC6551_REGISTRY;
            ensRegistry = SEPOLIA_ENS_REGISTRY;
            ensResolver = SEPOLIA_ENS_RESOLVER;
        } else if (isBaseSepolia) {
            console.log("Deploying to Base Sepolia...");
            // ERC6551 Registry is canonical on Base Sepolia
            erc6551Registry = ERC6551_REGISTRY;
            
            // Deploy mock ENS as it's not natively on Base Sepolia
            MockENSRegistry mockENS = new MockENSRegistry();
            MockENSResolver mockResolver = new MockENSResolver();
            ensRegistry = address(mockENS);
            ensResolver = address(mockResolver);
            console.log("MockENSRegistry deployed on Base:", ensRegistry);
            console.log("MockENSResolver deployed on Base:", ensResolver);
        } else if (isLocal) {
            console.log("Deploying to local network with mocks...");
            
            // Deploy mock ERC-6551 registry
            MockERC6551Registry mockRegistry = new MockERC6551Registry();
            erc6551Registry = address(mockRegistry);
            console.log("MockERC6551Registry deployed:", erc6551Registry);

            // Deploy mock ENS
            MockENSRegistry mockENS = new MockENSRegistry();
            MockENSResolver mockResolver = new MockENSResolver();
            ensRegistry = address(mockENS);
            ensResolver = address(mockResolver);
            console.log("MockENSRegistry deployed:", ensRegistry);
            console.log("MockENSResolver deployed:", ensResolver);
        }

        // 1. Deploy ERC6551Account implementation
        ERC6551Account accountImpl = new ERC6551Account();
        console.log("ERC6551Account implementation deployed:", address(accountImpl));

        // 2. Deploy AgentRegistry
        AgentRegistry agentRegistry = new AgentRegistry(
            erc6551Registry,
            address(accountImpl),
            ensRegistry,
            ensResolver,
            PARENT_NODE
        );
        console.log("AgentRegistry deployed:", address(agentRegistry));

        // 3. Deploy ReputationRegistry
        ReputationRegistry reputationRegistry = new ReputationRegistry();
        console.log("ReputationRegistry deployed:", address(reputationRegistry));

        // 4. Deploy BountyHive
        BountyHive bountyHive = new BountyHive(
            address(agentRegistry),
            address(reputationRegistry)
        );
        console.log("BountyHive deployed:", address(bountyHive));

        // 5. Configure permissions
        reputationRegistry.setAgentRegistry(address(agentRegistry));
        reputationRegistry.setAuthorizedReviewer(address(bountyHive), true);
        agentRegistry.setAuthorizedCaller(address(reputationRegistry), true);
        agentRegistry.setAuthorizedCaller(address(bountyHive), true);
        console.log("Permissions configured");

        // 6. If using mocks, set up ENS parent node ownership
        if (isLocal || isBaseSepolia) {
            MockENSRegistry(ensRegistry).setNodeOwner(PARENT_NODE, address(agentRegistry));
            console.log("ENS parent node ownership set");
        }

        // 7. Transfer BountyHive ownership to judge
        if (judgeAddress != deployer && judgeAddress != address(0)) {
            bountyHive.transferOwnership(judgeAddress);
            console.log("BountyHive ownership transferred to judge");
        }

        vm.stopBroadcast();

        // Print summary
        console.log("\n=== DEPLOYMENT SUMMARY ===");
        console.log("ERC6551Account Implementation:", address(accountImpl));
        console.log("AgentRegistry:", address(agentRegistry));
        console.log("ReputationRegistry:", address(reputationRegistry));
        console.log("BountyHive:", address(bountyHive));
        console.log("Judge Address:", judgeAddress);
        console.log("========================\n");
    }
}

/**
 * @title DeployLocal
 * @notice Quick deployment for local testing with Anvil
 */
contract DeployLocal is Script {
    function run() external {
        // Use default Anvil private key
        uint256 deployerPrivateKey = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80;

        vm.startBroadcast(deployerPrivateKey);

        // Deploy mocks
        MockERC6551Registry erc6551Registry = new MockERC6551Registry();
        ERC6551Account accountImpl = new ERC6551Account();
        MockENSRegistry ensRegistry = new MockENSRegistry();
        MockENSResolver ensResolver = new MockENSResolver();

        bytes32 parentNode = keccak256(
            abi.encodePacked(
                keccak256(abi.encodePacked(bytes32(0), keccak256("eth"))),
                keccak256("openaudit")
            )
        );

        // Deploy core contracts
        AgentRegistry agentRegistry = new AgentRegistry(
            address(erc6551Registry),
            address(accountImpl),
            address(ensRegistry),
            address(ensResolver),
            parentNode
        );

        ReputationRegistry reputationRegistry = new ReputationRegistry();
        BountyHive bountyHive = new BountyHive(
            address(agentRegistry),
            address(reputationRegistry)
        );

        // Configure
        reputationRegistry.setAgentRegistry(address(agentRegistry));
        reputationRegistry.setAuthorizedReviewer(address(bountyHive), true);
        agentRegistry.setAuthorizedCaller(address(reputationRegistry), true);
        agentRegistry.setAuthorizedCaller(address(bountyHive), true);
        ensRegistry.setNodeOwner(parentNode, address(agentRegistry));

        vm.stopBroadcast();

        console.log("=== LOCAL DEPLOYMENT ===");
        console.log("AgentRegistry:", address(agentRegistry));
        console.log("BountyHive:", address(bountyHive));
        console.log("ReputationRegistry:", address(reputationRegistry));
    }
}
