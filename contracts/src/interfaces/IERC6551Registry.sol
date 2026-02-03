// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IERC6551Registry
 * @notice Interface for the ERC-6551 Token Bound Account Registry
 * @dev Standard registry address: 0x000000006551c19487814612e58FE06813775758
 */
interface IERC6551Registry {
    /**
     * @dev Emitted when a token bound account is created
     */
    event ERC6551AccountCreated(
        address account,
        address indexed implementation,
        bytes32 salt,
        uint256 chainId,
        address indexed tokenContract,
        uint256 indexed tokenId
    );

    /**
     * @dev Reverts if account creation fails
     */
    error AccountCreationFailed();

    /**
     * @notice Creates a token bound account for a non-fungible token
     * @param implementation The address of the account implementation
     * @param salt Unique salt for account creation
     * @param chainId The chain ID where the token exists
     * @param tokenContract The address of the NFT contract
     * @param tokenId The token ID
     * @return account The address of the created token bound account
     */
    function createAccount(
        address implementation,
        bytes32 salt,
        uint256 chainId,
        address tokenContract,
        uint256 tokenId
    ) external returns (address account);

    /**
     * @notice Computes the address of a token bound account
     * @param implementation The address of the account implementation
     * @param salt Unique salt for account creation
     * @param chainId The chain ID where the token exists
     * @param tokenContract The address of the NFT contract
     * @param tokenId The token ID
     * @return account The computed address of the token bound account
     */
    function account(
        address implementation,
        bytes32 salt,
        uint256 chainId,
        address tokenContract,
        uint256 tokenId
    ) external view returns (address account);
}
