// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IERC6551Account
 * @notice Interface for ERC-6551 Token Bound Accounts
 */
interface IERC6551Account {
    /**
     * @notice Allows the account to receive native tokens
     */
    receive() external payable;

    /**
     * @notice Returns the token that owns this account
     * @return chainId The chain ID where the token exists
     * @return tokenContract The address of the NFT contract
     * @return tokenId The token ID
     */
    function token()
        external
        view
        returns (uint256 chainId, address tokenContract, uint256 tokenId);

    /**
     * @notice Returns the current state of the account
     * @dev State changes on each transaction to prevent replay attacks
     */
    function state() external view returns (uint256);

    /**
     * @notice Checks if a signer is valid for this account
     * @param signer The address to check
     * @param context Additional context data
     * @return magicValue The function selector if valid, 0 otherwise
     */
    function isValidSigner(address signer, bytes calldata context)
        external
        view
        returns (bytes4 magicValue);
}

/**
 * @title IERC6551Executable
 * @notice Interface for executing transactions from a Token Bound Account
 */
interface IERC6551Executable {
    /**
     * @notice Executes a transaction from the account
     * @param to The target address
     * @param value The ETH value to send
     * @param data The calldata
     * @param operation The operation type (0=CALL, 1=DELEGATECALL, 2=CREATE, 3=CREATE2)
     * @return result The return data from the call
     */
    function execute(
        address to,
        uint256 value,
        bytes calldata data,
        uint8 operation
    ) external payable returns (bytes memory result);
}
