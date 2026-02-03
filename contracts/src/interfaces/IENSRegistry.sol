// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IENS
 * @notice Interface for the ENS Registry
 */
interface IENS {
    event NewOwner(bytes32 indexed node, bytes32 indexed label, address owner);
    event Transfer(bytes32 indexed node, address owner);
    event NewResolver(bytes32 indexed node, address resolver);
    event NewTTL(bytes32 indexed node, uint64 ttl);

    function setSubnodeOwner(
        bytes32 node,
        bytes32 label,
        address owner
    ) external returns (bytes32);

    function setSubnodeRecord(
        bytes32 node,
        bytes32 label,
        address owner,
        address resolver,
        uint64 ttl
    ) external;

    function setResolver(bytes32 node, address resolver) external;

    function setOwner(bytes32 node, address owner) external;

    function setTTL(bytes32 node, uint64 ttl) external;

    function owner(bytes32 node) external view returns (address);

    function resolver(bytes32 node) external view returns (address);

    function ttl(bytes32 node) external view returns (uint64);

    function recordExists(bytes32 node) external view returns (bool);
}

/**
 * @title IENSResolver
 * @notice Interface for ENS Resolver with address and text record support
 */
interface IENSResolver {
    event AddrChanged(bytes32 indexed node, address a);
    event TextChanged(
        bytes32 indexed node,
        string indexed indexedKey,
        string key,
        string value
    );

    /**
     * @notice Sets the address for a node
     * @param node The ENS node hash
     * @param _addr The address to set
     */
    function setAddr(bytes32 node, address _addr) external;

    /**
     * @notice Gets the address for a node
     * @param node The ENS node hash
     * @return The address
     */
    function addr(bytes32 node) external view returns (address payable);

    /**
     * @notice Sets a text record
     * @param node The ENS node hash
     * @param key The key (e.g., "score", "model", "last_audit")
     * @param value The value
     */
    function setText(bytes32 node, string calldata key, string calldata value) external;

    /**
     * @notice Gets a text record
     * @param node The ENS node hash
     * @param key The key
     * @return The value
     */
    function text(bytes32 node, string calldata key) external view returns (string memory);
}
