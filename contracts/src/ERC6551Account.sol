// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/introspection/IERC165.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import "@openzeppelin/contracts/interfaces/IERC1271.sol";
import "@openzeppelin/contracts/utils/cryptography/SignatureChecker.sol";

import "./interfaces/IERC6551Account.sol";

/**
 * @title ERC6551Account
 * @notice Simple Token Bound Account implementation
 * @dev Based on the ERC-6551 reference implementation
 */
contract ERC6551Account is IERC165, IERC1271, IERC6551Account, IERC6551Executable {
    /// @notice State counter, incremented on each transaction
    uint256 public state;

    /// @notice Allows the account to receive native tokens
    receive() external payable override {}

    /**
     * @notice Executes a transaction from the account
     * @param to The target address
     * @param value The ETH value to send
     * @param data The calldata
     * @param operation The operation type (only 0=CALL is supported)
     * @return result The return data from the call
     */
    function execute(
        address to,
        uint256 value,
        bytes calldata data,
        uint8 operation
    ) external payable override returns (bytes memory result) {
        require(_isValidSigner(msg.sender), "Invalid signer");
        require(operation == 0, "Only call operations are supported");

        ++state;

        bool success;
        (success, result) = to.call{value: value}(data);

        if (!success) {
            assembly {
                revert(add(result, 32), mload(result))
            }
        }
    }

    /**
     * @notice Checks if a signer is valid for this account
     * @param signer The address to check
     * @return magicValue The function selector if valid, 0 otherwise
     */
    function isValidSigner(
        address signer,
        bytes calldata
    ) external view override returns (bytes4) {
        if (_isValidSigner(signer)) {
            return IERC6551Account.isValidSigner.selector;
        }
        return bytes4(0);
    }

    /**
     * @notice Validates a signature (ERC-1271)
     * @param hash The hash that was signed
     * @param signature The signature to validate
     * @return magicValue The ERC-1271 magic value if valid
     */
    function isValidSignature(
        bytes32 hash,
        bytes memory signature
    ) external view override returns (bytes4 magicValue) {
        bool isValid = SignatureChecker.isValidSignatureNow(
            owner(),
            hash,
            signature
        );

        if (isValid) {
            return IERC1271.isValidSignature.selector;
        }

        return bytes4(0);
    }

    /**
     * @notice Returns whether this contract implements a given interface
     * @param interfaceId The interface ID to check
     * @return True if the interface is supported
     */
    function supportsInterface(bytes4 interfaceId) external pure override returns (bool) {
        return
            interfaceId == type(IERC165).interfaceId ||
            interfaceId == type(IERC6551Account).interfaceId ||
            interfaceId == type(IERC6551Executable).interfaceId;
    }

    /**
     * @notice Returns the token that owns this account
     * @return chainId The chain ID where the token exists
     * @return tokenContract The address of the NFT contract
     * @return tokenId The token ID
     */
    function token()
        public
        view
        override
        returns (uint256, address, uint256)
    {
        bytes memory footer = new bytes(0x60);

        assembly {
            extcodecopy(address(), add(footer, 0x20), 0x4d, 0x60)
        }

        return abi.decode(footer, (uint256, address, uint256));
    }

    /**
     * @notice Returns the owner of this account (the NFT owner)
     * @return The owner address
     */
    function owner() public view returns (address) {
        (uint256 chainId, address tokenContract, uint256 tokenId) = token();
        if (chainId != block.chainid) return address(0);

        return IERC721(tokenContract).ownerOf(tokenId);
    }

    /**
     * @dev Internal function to check if a signer is valid
     */
    function _isValidSigner(address signer) internal view returns (bool) {
        return signer == owner();
    }
}
