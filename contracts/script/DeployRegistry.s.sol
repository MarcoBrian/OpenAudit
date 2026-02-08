// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/OpenAuditRegistry.sol";
import "../src/ERC6551Account.sol";
import "../src/mocks/MockERC6551Registry.sol";
import "../src/mocks/MockENS.sol";
import "../src/mocks/MockERC20.sol";

/**
 * @title DeployOpenAudit
 * @notice Deploy OpenAuditRegistry with ERC-6551 + ENS infrastructure
 *
 *   forge script script/DeployRegistry.s.sol:DeployOpenAudit --rpc-url $RPC_URL --broadcast
 */
contract DeployOpenAudit is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        // Use env vars for existing infrastructure, or deploy mocks
        address erc6551Reg  = vm.envOr("ERC6551_REGISTRY", address(0));
        address ensRegAddr  = vm.envOr("ENS_REGISTRY", address(0));
        address ensResAddr  = vm.envOr("ENS_RESOLVER", address(0));
        bytes32 parentNode  = vm.envOr("ENS_PARENT_NODE", keccak256("openaudit.eth"));
        address usdcAddr    = vm.envOr("USDC_ADDRESS", address(0));
        address relayAddr   = vm.envOr("PAYOUT_RELAY", deployer);

        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);

        vm.startBroadcast(deployerPrivateKey);

        // TBA implementation
        ERC6551Account tbaImpl = new ERC6551Account();
        console.log("ERC6551Account impl:", address(tbaImpl));

        // Deploy mocks if no addresses provided
        if (erc6551Reg == address(0)) {
            MockERC6551Registry mock6551 = new MockERC6551Registry();
            erc6551Reg = address(mock6551);
            console.log("MockERC6551Registry:", erc6551Reg);
        }
        if (ensRegAddr == address(0)) {
            MockENSRegistry mockENS = new MockENSRegistry();
            ensRegAddr = address(mockENS);
            console.log("MockENSRegistry:", ensRegAddr);
        }
        if (ensResAddr == address(0)) {
            MockENSResolver mockRes = new MockENSResolver();
            ensResAddr = address(mockRes);
            console.log("MockENSResolver:", ensResAddr);
        }
        if (usdcAddr == address(0)) {
            MockERC20 mockUsdc = new MockERC20("USD Coin", "USDC", 6);
            usdcAddr = address(mockUsdc);
            console.log("MockERC20 (USDC):", usdcAddr);
        }

        console.log("Payout relay:", relayAddr);

        // Deploy registry
        OpenAuditRegistry registry = new OpenAuditRegistry(
            erc6551Reg,
            address(tbaImpl),
            ensRegAddr,
            ensResAddr,
            parentNode,
            usdcAddr,
            relayAddr
        );
        console.log("OpenAuditRegistry:", address(registry));

        // Give registry ownership of the ENS parent node (only if using mocks)
        if (vm.envOr("ENS_REGISTRY", address(0)) == address(0)) {
            MockENSRegistry(ensRegAddr).setNodeOwner(parentNode, address(registry));
            console.log("Set Mock ENS node owner to registry");
        } else {
            console.log("Using real ENS. Remember to manually set registry as owner of the parent node!");
        }

        // Optionally transfer ownership to a judge address
        address judge = vm.envOr("JUDGE_ADDRESS", deployer);
        if (judge != deployer) {
            registry.transferOwnership(judge);
            console.log("Ownership transferred to judge:", judge);
        }

        vm.stopBroadcast();

        console.log("=== DEPLOYMENT COMPLETE ===");
    }
}

/**
 * @title DeployLocal
 * @notice Quick deploy with default Anvil key (deploys mocks automatically)
 */
contract DeployLocal is Script {
    function run() external {
        uint256 pk = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80;
        address deployer = vm.addr(pk);

        vm.startBroadcast(pk);

        ERC6551Account tbaImpl = new ERC6551Account();
        MockERC6551Registry erc6551Reg = new MockERC6551Registry();
        MockENSRegistry ensReg = new MockENSRegistry();
        MockENSResolver ensRes = new MockENSResolver();
        MockERC20 mockUsdc = new MockERC20("USD Coin", "USDC", 6);

        bytes32 parentNode = keccak256("openaudit.eth");

        OpenAuditRegistry registry = new OpenAuditRegistry(
            address(erc6551Reg),
            address(tbaImpl),
            address(ensReg),
            address(ensRes),
            parentNode,
            address(mockUsdc),
            deployer  // relay = deployer for local testing
        );

        // Give registry ENS parent node ownership
        ensReg.setNodeOwner(parentNode, address(registry));

        vm.stopBroadcast();

        console.log("OpenAuditRegistry:", address(registry));
        console.log("ERC6551Account:", address(tbaImpl));
        console.log("ERC6551Registry:", address(erc6551Reg));
        console.log("ENSRegistry:", address(ensReg));
        console.log("ENSResolver:", address(ensRes));
        console.log("MockUSDC:", address(mockUsdc));
    }
}
