// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IENSRegistry.sol";

/**
 * @title MockENSRegistry
 * @notice Mock ENS Registry for testing
 */
contract MockENSRegistry is IENS {
    mapping(bytes32 => address) private _owners;
    mapping(bytes32 => address) private _resolvers;
    mapping(bytes32 => uint64) private _ttls;

    constructor() {
        // Set deployer as owner of root
        _owners[bytes32(0)] = msg.sender;
    }

    function setSubnodeOwner(
        bytes32 node,
        bytes32 label,
        address ownerAddr
    ) external override returns (bytes32) {
        bytes32 subnode = keccak256(abi.encodePacked(node, label));
        _owners[subnode] = ownerAddr;
        emit NewOwner(node, label, ownerAddr);
        return subnode;
    }

    function setSubnodeRecord(
        bytes32 node,
        bytes32 label,
        address ownerAddr,
        address resolver,
        uint64 ttl
    ) external override {
        bytes32 subnode = keccak256(abi.encodePacked(node, label));
        _owners[subnode] = ownerAddr;
        _resolvers[subnode] = resolver;
        _ttls[subnode] = ttl;
        emit NewOwner(node, label, ownerAddr);
        emit NewResolver(subnode, resolver);
        emit NewTTL(subnode, ttl);
    }

    function setResolver(bytes32 node, address resolver) external override {
        _resolvers[node] = resolver;
        emit NewResolver(node, resolver);
    }

    function setOwner(bytes32 node, address ownerAddr) external override {
        _owners[node] = ownerAddr;
        emit Transfer(node, ownerAddr);
    }

    function setTTL(bytes32 node, uint64 ttl) external override {
        _ttls[node] = ttl;
        emit NewTTL(node, ttl);
    }

    function owner(bytes32 node) external view override returns (address) {
        return _owners[node];
    }

    function resolver(bytes32 node) external view override returns (address) {
        return _resolvers[node];
    }

    function ttl(bytes32 node) external view override returns (uint64) {
        return _ttls[node];
    }

    function recordExists(bytes32 node) external view override returns (bool) {
        return _owners[node] != address(0);
    }

    // Helper to set up a parent node for testing
    function setNodeOwner(bytes32 node, address ownerAddr) external {
        _owners[node] = ownerAddr;
    }
}

/**
 * @title MockENSResolver
 * @notice Mock ENS Resolver for testing
 */
contract MockENSResolver is IENSResolver {
    mapping(bytes32 => address) private _addresses;
    mapping(bytes32 => mapping(string => string)) private _texts;

    function setAddr(bytes32 node, address _addr) external override {
        _addresses[node] = _addr;
        emit AddrChanged(node, _addr);
    }

    function addr(bytes32 node) external view override returns (address payable) {
        return payable(_addresses[node]);
    }

    function setText(bytes32 node, string calldata key, string calldata value) external override {
        _texts[node][key] = value;
        emit TextChanged(node, key, key, value);
    }

    function text(bytes32 node, string calldata key) external view override returns (string memory) {
        return _texts[node][key];
    }
}
