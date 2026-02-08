#!/bin/bash

# Base Sepolia Contract Verification Script
# Make sure BASESCAN_API_KEY is set in your environment

set -e

CHAIN="base-sepolia"
API_KEY="${BASESCAN_API_KEY}"

if [ -z "$API_KEY" ]; then
    echo "Error: BASESCAN_API_KEY environment variable is not set"
    exit 1
fi

echo "Verifying contracts on Base Sepolia..."
echo "Using API Key: ${API_KEY:0:10}..."

# 1. ERC6551Account (no constructor args)
echo ""
echo "Verifying ERC6551Account..."
forge verify-contract \
    0xa35be9c3dcd5b40242af1f54dfadbdac04d23eb6 \
    src/ERC6551Account.sol:ERC6551Account \
    --chain $CHAIN \
    --etherscan-api-key $API_KEY

# 2. MockERC6551Registry (no constructor args)
echo ""
echo "Verifying MockERC6551Registry..."
forge verify-contract \
    0xa5ade68a3f346d3909bb25200a4cf698cccba660 \
    src/mocks/MockERC6551Registry.sol:MockERC6551Registry \
    --chain $CHAIN \
    --etherscan-api-key $API_KEY

# 3. MockENSRegistry (no constructor args)
echo ""
echo "Verifying MockENSRegistry..."
forge verify-contract \
    0x65450ec8eee3f4b396e9189f86c5c3967cc889c7 \
    src/mocks/MockENS.sol:MockENSRegistry \
    --chain $CHAIN \
    --etherscan-api-key $API_KEY

# 4. MockENSResolver (no constructor args)
echo ""
echo "Verifying MockENSResolver..."
forge verify-contract \
    0x96eea63adc8e4f48fa415d8b8b0f7f571665b860 \
    src/mocks/MockENS.sol:MockENSResolver \
    --chain $CHAIN \
    --etherscan-api-key $API_KEY

# 5. OpenAuditRegistry (with constructor args)
# Constructor args: erc6551Reg, tbaImpl, ensReg, ensRes, parentNode
echo ""
echo "Verifying OpenAuditRegistry..."
forge verify-contract \
    0x62fbee8b9d90e80ae6cd8d914aa43448842b00bc \
    src/OpenAuditRegistry.sol:OpenAuditRegistry \
    --chain $CHAIN \
    --etherscan-api-key $API_KEY \
    --constructor-args $(cast abi-encode "constructor(address,address,address,address,bytes32)" \
        0xA5aDE68a3f346D3909bb25200A4cf698ccCBA660 \
        0xa35Be9c3DCd5B40242af1F54dFADbDaC04D23Eb6 \
        0x65450eC8eee3F4B396e9189F86C5c3967Cc889C7 \
        0x96eEa63adc8e4F48fA415d8B8B0F7f571665b860 \
        0xd4e6ceea15b206c81bfe9e8c8ab356840bc07d6fb7f1c3b3666173ee367db290)

echo ""
echo "All contracts verified!"
