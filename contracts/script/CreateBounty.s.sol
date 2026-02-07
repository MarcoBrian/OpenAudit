// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";

import "../src/BountyHive.sol";

/**
 * @title CreateBounty
 * @notice Script to create a new bounty on BountyHive
 * @dev Required env vars: PRIVATE_KEY, BOUNTY_HIVE, TARGET_CONTRACT, DEADLINE, REWARD_WEI
 */
contract CreateBounty is Script {
    function run() external {
        uint256 sponsorPrivateKey = vm.envUint("PRIVATE_KEY");
        address sponsor = vm.addr(sponsorPrivateKey);
        address bountyHiveAddress = vm.envAddress("BOUNTY_HIVE");
        address targetContract = vm.envAddress("TARGET_CONTRACT");
        uint256 deadline = vm.envUint("DEADLINE");
        uint256 rewardWei = vm.envUint("REWARD_WEI");

        console.log("Sponsor:", sponsor);
        console.log("BountyHive:", bountyHiveAddress);
        console.log("Target contract:", targetContract);
        console.log("Deadline:", deadline);
        console.log("Reward (wei):", rewardWei);
        console.log("Chain ID:", block.chainid);

        vm.startBroadcast(sponsorPrivateKey);

        uint256 bountyId = BountyHive(bountyHiveAddress).createBounty{value: rewardWei}(
            targetContract,
            deadline
        );

        vm.stopBroadcast();

        console.log("Bounty created with ID:", bountyId);
    }
}
