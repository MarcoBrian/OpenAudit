// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "erc6551/interfaces/IERC6551Registry.sol";

/**
 * @title MockERC6551Registry
 * @notice Mock implementation of ERC-6551 Registry for testing
 * @dev Creates minimal proxy accounts for NFTs
 */
contract MockERC6551Registry is IERC6551Registry {
    /**
     * @notice Creates a token bound account for an NFT
     */
    function createAccount(
        address implementation,
        bytes32 salt,
        uint256 chainId,
        address tokenContract,
        uint256 tokenId
    ) external returns (address) {
        bytes memory code = _creationCode(implementation, salt, chainId, tokenContract, tokenId);

        address _account = _computeAddress(code);

        if (_account.code.length != 0) return _account;

        assembly {
            _account := create2(0, add(code, 0x20), mload(code), salt)
        }

        if (_account == address(0)) revert AccountCreationFailed();

        emit ERC6551AccountCreated(_account, implementation, salt, chainId, tokenContract, tokenId);

        return _account;
    }

    /**
     * @notice Computes the address of a token bound account
     */
    function account(
        address implementation,
        bytes32 salt,
        uint256 chainId,
        address tokenContract,
        uint256 tokenId
    ) external view returns (address) {
        bytes memory code = _creationCode(implementation, salt, chainId, tokenContract, tokenId);
        return _computeAddress(code);
    }

    function _creationCode(
        address implementation,
        bytes32 salt,
        uint256 chainId,
        address tokenContract,
        uint256 tokenId
    ) internal pure returns (bytes memory) {
        return abi.encodePacked(
            // ERC-1167 minimal proxy bytecode
            hex"3d60ad80600a3d3981f3363d3d373d3d3d363d73",
            implementation,
            hex"5af43d82803e903d91602b57fd5bf3",
            // Append immutable args
            abi.encode(salt, chainId, tokenContract, tokenId)
        );
    }

    function _computeAddress(bytes memory code) internal view returns (address) {
        bytes32 hash = keccak256(
            abi.encodePacked(
                bytes1(0xff),
                address(this),
                bytes32(0),
                keccak256(code)
            )
        );
        return address(uint160(uint256(hash)));
    }
}
