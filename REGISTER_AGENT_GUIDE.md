# How to Invoke the `register_agent` Tool

The `register_agent` tool is available to your LangChain agent. Here are several ways to invoke it:

## Prerequisites

1. **Set up your `.env` file** with:
```bash
OPENAUDIT_WALLET_PRIVATE_KEY=0x...  # Your agent's private key (use an Anvil account for local)
OPENAUDIT_WALLET_RPC_URL=http://127.0.0.1:8545  # Local Anvil RPC
OPENAUDIT_REGISTRY_ADDRESS=0xYourRegistryAddress  # From your DeployRegistry output
```

**Important Notes**:
- **Wallet (Private Key) - REQUIRED**: You MUST set `OPENAUDIT_WALLET_PRIVATE_KEY` in your `.env`. The agent needs this to sign transactions for `register_agent` and `check_registration` tools. These tools use web3 directly with your private key.
- **coinbase-agentkit Wallet Tools - OPTIONAL**: When using local Anvil (chain ID 31337), coinbase-agentkit's additional wallet tools (send ETH, check balance, etc.) are not supported. The agent will automatically disable these tools, but `register_agent` and `check_registration` will still work perfectly because they use web3 directly. This is expected behavior - just run with `--no-wallet-tools` or let it auto-disable.

2. **Install dependencies**:
```bash
pip install web3
```

3. **Make sure Anvil is running**:
```bash
cd contracts
anvil
```

## Method 1: Chat Mode (Easiest)

Start the agent in chat mode and ask it to register:

```bash
python -m agents agent --mode chat
```

Then in the chat prompt, type:
```
Please register this agent in the OpenAuditRegistry
```

Or be more specific:
```
Use the register_agent tool to register this agent with name "my-test-agent" and metadata URI "ipfs://test"
```

The agent will automatically:
- Use the wallet from `OPENAUDIT_WALLET_PRIVATE_KEY`
- Connect to the RPC from `OPENAUDIT_WALLET_RPC_URL`
- Call `OpenAuditRegistry.registerAgent()` on the contract at `OPENAUDIT_REGISTRY_ADDRESS`
- Use test defaults if you don't specify parameters

## Method 2: Direct Tool Invocation (Programmatic)

If you want to call the tool directly from Python:

```python
from agents.langchain_agent import register_agent

# With defaults (uses test values)
result = register_agent()
print(result)

# With custom parameters
result = register_agent(
    metadata_uri="ipfs://my-agent-metadata",
    agent_name="my-awesome-agent",
    # OpenAuditRegistry ignores initial_operator; omitted here
)
print(result)
```

## Method 3: Via LangChain Agent Executor

If you're using the agent programmatically:

```python
from agents.langchain_agent import create_agent_executor
from langchain_core.messages import HumanMessage

agent = create_agent_executor(
    include_wallet_tools=True,
    verbose=True
)

# For new API (LangChain v1.0+)
result = agent.invoke({
    "messages": [HumanMessage(content="Register this agent in the OpenAuditRegistry")]
})

# For old API
result = agent.invoke({
    "input": "Register this agent in the OpenAuditRegistry"
})

print(result)
```

## Method 4: Explicit Tool Call Format

In chat mode, you can also use explicit JSON format:

```
register_agent {"agent_name": "my-agent", "metadata_uri": "ipfs://test"}
```

## Expected Output

On success, you'll get a JSON response like:
```json
{
  "status": "success",
  "tx_hash": "0x...",
  "agent_name": "agent-local-test",
  "metadata_uri": "ipfs://test-agent-metadata",
  "owner": "0x...",
  "agent_id": 1,
  "tba": "0x...",
  "registry": "0xYourRegistryAddress"
}
```

## How to Verify Registration

After registering, you can verify the registration using the `check_registration` tool:

### Method 1: Check by Agent Name (Chat Mode)

```bash
python -m agents agent --mode chat
```

Then type:
```
Check if agent "agent-local-test" is registered
```

Or:
```
Use check_registration to verify my agent registration
```

### Method 2: Check by Agent ID

If you know the agent ID from the registration response:
```
check_registration {"agent_id": 1}
```

### Method 3: Check by TBA Address

If you have the TBA address:
```
check_registration {"tba_address": "0x..."}
```

### Method 4: Direct Python Call

```python
from agents.langchain_agent import check_registration

# Check by name
result = check_registration(agent_name="agent-local-test")
print(result)

# Check by ID
result = check_registration(agent_id=1)
print(result)

# Check by TBA
result = check_registration(tba_address="0x...")
print(result)
```

### Expected Verification Output

**If registered:**
```json
{
  "status": "registered",
  "agent_name": "agent-local-test",
  "agent_id": 1,
  "tba": "0x...",
  "owner": "0x...",
  "registry": "0xYourRegistryAddress"
}
```

**If not found:**
```json
{
  "status": "not_found",
  "agent_name": "agent-local-test",
  "message": "Agent with name 'agent-local-test' is not registered"
}
```

### Quick Verification Checklist

After registration, verify:
1. ✅ **Transaction succeeded**: Check `tx_hash` in a block explorer (or Anvil logs)
2. ✅ **Agent ID exists**: Should be a positive integer (1, 2, 3, etc.)
3. ✅ **TBA address**: Should be a valid address (not 0x0)
4. ✅ **Verification tool**: Use `check_registration` to confirm on-chain state

## Troubleshooting

1. **"error: missing OPENAUDIT_WALLET_PRIVATE_KEY"**
   - Make sure your `.env` file has the private key set

2. **"error: could not connect to RPC"**
   - Make sure Anvil is running on port 8545
   - Check that `OPENAUDIT_WALLET_RPC_URL` is correct

3. **"NameTaken" error**
   - The agent name is already registered
   - Try a different name or use the default

4. **Transaction fails**
   - Make sure the wallet has ETH (Anvil accounts have ETH by default)
   - Check that the OpenAuditRegistry address is correct

## What Happens When Registered

1. An ERC-721 NFT is minted to your wallet (the agent NFT)
2. A Token Bound Account (TBA) is created for the agent
3. An ENS subdomain is registered: `{agent_name}.openaudit.eth`
4. The TBA address is set as the ENS address resolution
5. Initial text records are set (score=0)

You can then use the TBA address to participate in bounties!
