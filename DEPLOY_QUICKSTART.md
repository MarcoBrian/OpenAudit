# Quick Deployment Checklist

## Backend (Fly.io) - 5 minutes

```bash
# 1. Install Fly CLI (if not installed)
curl -L https://fly.io/install.sh | sh

# 2. Login
fly auth login

# 3. Initialize (from project root)
fly launch --name openaudit-backend --region iad

# 4. Set secrets (replace with your values)
fly secrets set OPENAI_API_KEY=your_key
fly secrets set PINATA_JWT=your_jwt
fly secrets set PINATA_GATEWAY_URL=https://your-gateway.mypinata.cloud
# ... add other required secrets from env.template

# 5. Deploy
fly deploy

# 6. Get your backend URL
fly status
# Note the URL: https://openaudit-backend.fly.dev
```

## Frontend (Vercel) - 3 minutes

### Via Dashboard:
1. Go to [vercel.com/dashboard](https://vercel.com/dashboard)
2. Import Git repository
3. Set **Root Directory** to `dashboard/frontend`
4. Add environment variable:
   - `NEXT_PUBLIC_API_BASE` = `https://openaudit-backend.fly.dev`
5. Deploy

### Via CLI:
```bash
cd dashboard/frontend
npm i -g vercel
vercel login
vercel
# Follow prompts, then:
vercel env add NEXT_PUBLIC_API_BASE production
# Enter: https://openaudit-backend.fly.dev
vercel --prod
```

## Verify

1. Backend health: `curl https://openaudit-backend.fly.dev/`
2. Frontend: Visit your Vercel URL
3. Test chat functionality

## Required Environment Variables

### Backend (Fly.io secrets):
- `OPENAI_API_KEY` (required)
- `PINATA_JWT` (required for IPFS)
- `PINATA_GATEWAY_URL` (optional)
- `CDP_API_KEY_ID`, `CDP_API_KEY_SECRET`, `CDP_WALLET_SECRET` (if using Coinbase AgentKit)
- `OPENAUDIT_REGISTRY_ADDRESS`, `RPC_URL` (if using on-chain features)

### Frontend (Vercel):
- `NEXT_PUBLIC_API_BASE` (required) - Your Fly.io backend URL
- `NEXT_PUBLIC_SHOW_NON_CHAT` (optional) - Set to "true" to show non-chat UI
- `NEXT_PUBLIC_PINATA_GATEWAY` (optional) - Pinata gateway URL

See `env.template` for complete list.
