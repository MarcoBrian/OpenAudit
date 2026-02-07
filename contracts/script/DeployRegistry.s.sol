// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/OpenAuditRegistry.sol";

/**
 * @title DeployOpenAudit
 * @notice Deploy the simplified OpenAuditRegistry MVP
 *
 *   forge script script/Deploy.s.sol:DeployOpenAudit --rpc-url $RPC_URL --broadcast
 */
contract DeployOpenAudit is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);

        vm.startBroadcast(deployerPrivateKey);

        OpenAuditRegistry registry = new OpenAuditRegistry();
        console.log("OpenAuditRegistry deployed:", address(registry));

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
 * @notice Quick deploy with default Anvil key
 */
contract DeployLocal is Script {
    function run() external {
        uint256 pk = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80;
        vm.startBroadcast(pk);

        OpenAuditRegistry registry = new OpenAuditRegistry();

        vm.stopBroadcast();

        console.log("OpenAuditRegistry:", address(registry));
    }
}
