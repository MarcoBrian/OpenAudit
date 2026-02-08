// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";

import "../src/OpenAuditRegistry.sol";
import "../src/interfaces/IERC20.sol";

/**
 * @title CreateBounty
 * @notice Script to create a new USDC bounty on OpenAuditRegistry
 * @dev Required env vars: PRIVATE_KEY, OPENAUDIT_REGISTRY_ADDRESS, TARGET_CONTRACT_ADDRESS, DEADLINE, REWARD_USDC
 *      REWARD_USDC is in USDC base units (6 decimals), e.g. 1000000000 = 1000 USDC
 */
contract CreateBounty is Script {
    function run() external {
        uint256 sponsorPrivateKey = vm.envUint("PRIVATE_KEY");
        address sponsor = vm.addr(sponsorPrivateKey);
        address registryAddress = vm.envAddress("OPENAUDIT_REGISTRY_ADDRESS");
        address targetContract = vm.envAddress("TARGET_CONTRACT_ADDRESS");
        uint256 deadline = vm.envUint("DEADLINE");
        uint256 rewardUsdc = vm.envUint("REWARD_USDC");

        console.log("Sponsor:", sponsor);
        console.log("OpenAuditRegistry:", registryAddress);
        console.log("Target contract:", targetContract);
        console.log("Deadline:", deadline);
        console.log("Reward (USDC base units):", rewardUsdc);
        console.log("Chain ID:", block.chainid);

        OpenAuditRegistry registry = OpenAuditRegistry(registryAddress);
        IERC20 usdc = registry.usdc();

        vm.startBroadcast(sponsorPrivateKey);

        // Approve USDC spend
        usdc.approve(registryAddress, rewardUsdc);

        // Create bounty
        uint256 bountyId = registry.createBounty(
            targetContract,
            deadline,
            rewardUsdc
        );

        vm.stopBroadcast();

        console.log("Bounty created with ID:", bountyId);
    }
}
