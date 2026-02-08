# Deployment Guide

This guide covers deploying the OpenAudit platform:
- **Frontend** (Next.js) → Vercel
- **Backend** (FastAPI) → Fly.io

## Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **Fly.io Account**: Sign up at [fly.io](https://fly.io) and install the Fly CLI:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```
3. **Environment Variables**: Prepare all required environment variables (see `env.template`)

---

## Backend Deployment (Fly.io)

### 1. Initialize Fly.io App

From the project root directory:

```bash
fly launch --name openaudit-backend --region iad
```

When prompted:
- **Dockerfile path**: `Dockerfile` (already configured in fly.toml)
- **App name**: `openaudit-backend` (or your preferred name)
- **Region**: Choose closest to your users (e.g., `iad` for US East)

Note: The `fly.toml` and `Dockerfile` are already in the project root.

### 2. Set Environment Variables

Set all required environment variables in Fly.io:

```bash
# LLM Configuration
fly secrets set OPENAI_API_KEY=your_openai_key
fly secrets set OPENAI_MODEL=gpt-4o-mini
fly secrets set OPENAI_BASE_URL=https://api.openai.com/v1

# Optional: Ollama Configuration
fly secrets set OLLAMA_MODEL=llama3
fly secrets set OLLAMA_BASE_URL=http://localhost:11434

# Pinata IPFS
fly secrets set PINATA_JWT=your_pinata_jwt
fly secrets set PINATA_GATEWAY_URL=https://your-gateway.mypinata.cloud

# Coinbase AgentKit (if using)
fly secrets set CDP_API_KEY_ID=your_key_id
fly secrets set CDP_API_KEY_SECRET=your_key_secret
fly secrets set CDP_WALLET_SECRET=your_wallet_secret
fly secrets set CDP_NETWORK_ID=base-sepolia

# OpenAudit Registry
fly secrets set OPENAUDIT_REGISTRY_ADDRESS=your_registry_address
fly secrets set RPC_URL=your_rpc_url

# Add other required secrets from env.template
```

### 3. Deploy

```bash
fly deploy
```

### 4. Get Your Backend URL

After deployment, your backend will be available at:
```
https://openaudit-backend.fly.dev
```

Note this URL - you'll need it for the frontend configuration.

### 5. Verify Deployment

```bash
curl https://openaudit-backend.fly.dev/
```

Should return: `{"status":"ok","service":"OpenAudit API"}`

---

## Frontend Deployment (Vercel)

### Option 1: Deploy via Vercel Dashboard (Recommended)

1. **Import Project**:
   - Go to [vercel.com/dashboard](https://vercel.com/dashboard)
   - Click "Add New" → "Project"
   - Import your Git repository

2. **Configure Project**:
   - **Root Directory**: Set to `dashboard/frontend`
   - **Framework Preset**: Next.js (auto-detected)
   - **Build Command**: `npm run build` (default, or leave empty)
   - **Output Directory**: `.next` (default, or leave empty)
   - **Install Command**: `npm install` (default)

3. **Set Environment Variables**:
   - In project settings, add:
     ```
     NEXT_PUBLIC_API_BASE=https://openaudit-backend.fly.dev
     ```
   - Replace with your actual Fly.io backend URL
   - Optionally set:
     ```
     NEXT_PUBLIC_SHOW_NON_CHAT=true
     NEXT_PUBLIC_PINATA_GATEWAY=https://your-gateway.mypinata.cloud
     ```

4. **Deploy**: Click "Deploy"

### Option 2: Deploy via Vercel CLI

1. **Install Vercel CLI**:
   ```bash
   npm i -g vercel
   ```

2. **Login**:
   ```bash
   vercel login
   ```

3. **Deploy from Frontend Directory**:
   ```bash
   cd dashboard/frontend
   vercel
   ```
   
   When prompted:
   - **Set up and deploy?**: Yes
   - **Which scope?**: Your account
   - **Link to existing project?**: No (first time) or Yes (updates)
   - **Project name**: openaudit-frontend (or your choice)
   - **Directory**: `./` (current directory)
   - **Override settings?**: No (uses vercel.json)

4. **Set Environment Variables**:
   ```bash
   cd dashboard/frontend
   vercel env add NEXT_PUBLIC_API_BASE production
   # Enter: https://openaudit-backend.fly.dev
   ```

5. **Production Deploy**:
   ```bash
   vercel --prod
   ```

---

## Post-Deployment

### Update CORS (if needed)

If you encounter CORS issues, the backend already allows all origins. If you want to restrict it, edit `dashboard/server/app.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.vercel.app"],  # Your Vercel URL
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Verify Full Stack

1. **Frontend**: Visit your Vercel deployment URL
2. **Backend Health**: `https://openaudit-backend.fly.dev/`
3. **API Endpoint**: Test `/api/agent/chat` from the frontend

---

## Troubleshooting

### Backend Issues

**Port binding errors**:
- Ensure `fly.toml` has `internal_port = 8000`
- Check that the app listens on `0.0.0.0:8000`

**Missing dependencies**:
- Verify all packages in `requirements.txt` are installed
- Check Fly.io logs: `fly logs`

**Environment variables**:
- List secrets: `fly secrets list`
- View logs: `fly logs` to see runtime errors

### Frontend Issues

**API connection errors**:
- Verify `NEXT_PUBLIC_API_BASE` is set correctly
- Check browser console for CORS errors
- Ensure backend is running and accessible

**Build failures**:
- Check Vercel build logs
- Ensure all dependencies are in `package.json`
- Verify Node.js version compatibility

---

## Scaling

### Fly.io Scaling

```bash
# Scale to multiple instances
fly scale count 2

# Scale memory/CPU
fly scale vm shared-cpu-2x --memory 2048
```

### Vercel Scaling

Vercel automatically scales based on traffic. For high-traffic apps, consider:
- Upgrading to a paid plan
- Using Edge Functions for API routes
- Enabling caching strategies

---

## Monitoring

### Fly.io

```bash
# View logs
fly logs

# Monitor metrics
fly status
```

### Vercel

- View analytics in Vercel dashboard
- Check function logs in project settings
- Monitor API usage and performance

---

## Updates

### Update Backend

```bash
cd dashboard/server
fly deploy
```

### Update Frontend

- Push to your Git repository
- Vercel will auto-deploy on push (if connected)
- Or manually trigger: `vercel --prod` from `dashboard/frontend`

---

## Cost Estimation

- **Fly.io**: Free tier includes 3 shared-cpu-1x VMs with 256MB RAM. Paid plans start at ~$5/month.
- **Vercel**: Free tier includes 100GB bandwidth. Pro plan starts at $20/month.

---

## Security Notes

1. **Never commit secrets**: Use environment variables only
2. **Restrict CORS**: Update `allow_origins` in production
3. **Use HTTPS**: Both platforms provide HTTPS by default
4. **Rate limiting**: Consider adding rate limiting for production use
