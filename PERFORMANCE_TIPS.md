# Performance Tips for OpenAudit Agent

## Why is the agent slow to start?

The agent initialization can be slow due to several factors:

### 1. **LLM Connection (Most Common)**

**If using Ollama:**
- If `OLLAMA_MODEL` is set but Ollama isn't running, it will try to connect and timeout
- **Fix**: Either start Ollama (`ollama serve`) or unset `OLLAMA_MODEL` in your `.env`

**If using OpenAI:**
- Initialization is usually fast (no network call during init)
- First actual request might be slow if network is slow

### 2. **Wallet Tool Initialization**

If `--no-wallet-tools` is not used, the agent tries to initialize coinbase-agentkit:
- This can be slow if it's trying to connect to networks
- On local networks (Anvil), it will fail and disable wallet tools (with a warning)

**Fix**: Use `--no-wallet-tools` flag for local development:
```bash
python -m agents agent --mode chat --no-wallet-tools
```

### 3. **LangChain Agent Creation**

The agent executor creation itself can take a moment, especially with many tools.

## Quick Optimization

### For Local Development (Fastest):

```bash
# 1. Unset OLLAMA_MODEL if you're using OpenAI
# In .env:
OPENAI_API_KEY=your_key
# OLLAMA_MODEL=  # Comment this out

# 2. Disable wallet tools
python -m agents agent --mode chat --no-wallet-tools
```

### Check What's Slow:

The agent now shows progress messages:
```
Initializing agent...
  - Loading LLM...
  - Loading tools...
  - Creating agent executor...
Agent ready!
```

If it hangs at "Loading LLM...", it's likely trying to connect to Ollama.
If it hangs at "Loading tools...", it's likely wallet initialization.

## Expected Startup Times

- **With OpenAI (no wallet tools)**: 1-3 seconds
- **With OpenAI (with wallet tools)**: 2-5 seconds
- **With Ollama (running)**: 2-4 seconds
- **With Ollama (not running)**: 10-30 seconds (timeout)

## Troubleshooting

1. **Check your `.env` file**:
   ```bash
   cat .env | grep -E "(OPENAI|OLLAMA|WALLET)"
   ```

2. **Test Ollama connection**:
   ```bash
   curl http://localhost:11434/api/tags
   ```

3. **Use verbose mode** to see what's happening:
   ```bash
   python -m agents agent --mode chat --verbose --no-wallet-tools
   ```
