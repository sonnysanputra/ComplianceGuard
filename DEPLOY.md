# Deploying ComplianceGuard AI (Frontend on Vercel + Backend on your laptop)

**Architecture:** the Next.js **frontend** is hosted publicly on **Vercel**; the **backend + Ollama/Qwen** run on **your laptop**, exposed to the internet through a free **Cloudflare Tunnel**. Anyone with the Vercel URL can use the system — as long as your laptop (backend + tunnel) is running.

```
  Other people ─▶  https://your-app.vercel.app   (Vercel: frontend)
                          │  browser calls the API over HTTPS
                          ▼
                   https://xxxx.trycloudflare.com  (Cloudflare Tunnel)
                          │
                          ▼
                   http://localhost:8000           (your laptop: FastAPI)
                          │
                          ▼
                   Ollama + Qwen 2.5, ChromaDB, EasyOCR, Supabase
```

> Note: `NEXT_PUBLIC_API_BASE` is baked in at build time, so if the tunnel URL changes you must update it on Vercel and redeploy. Start the tunnel first, then deploy the frontend with that URL — and keep the tunnel running for your whole demo.

---

## STEP 1 — Run the backend locally (as usual)

Terminal 1 — make sure **Ollama** is running (desktop app, or `ollama list`).

Terminal 2 — start the backend:
```powershell
cd d:\Hacakthons\NexHack\backend
..\venv\Scripts\Activate.ps1
python server.py
```
Confirm it's up: open http://localhost:8000/health/ready

---

## STEP 2 — Expose the backend with a Cloudflare Tunnel (free, no account)

Install `cloudflared` once:
```powershell
winget install --id Cloudflare.cloudflared -e
```
(If `winget` isn't available, download `cloudflared.exe` from Cloudflare's GitHub releases and put it on your PATH.)

Terminal 3 — start the tunnel pointing at your backend:
```powershell
cloudflared tunnel --url http://localhost:8000
```
It prints a public URL like:
```
https://random-words-1234.trycloudflare.com
```
**Copy that URL.** Test it: open `https://random-words-1234.trycloudflare.com/health/ready` in a browser — you should see the backend respond. **Leave this terminal running.**

---

## STEP 3 — Deploy the frontend to Vercel

1. Push the repo to GitHub (you do this):
   ```powershell
   cd d:\Hacakthons\NexHack
   git add -A
   git commit -m "Deploy config"
   git push
   ```
2. Go to **vercel.com** → **Add New… → Project** → import your GitHub repo.
3. **Important settings:**
   - **Root Directory:** `frontend`  ← the app lives in a subfolder
   - **Framework Preset:** Next.js (auto-detected)
   - **Environment Variable:** add
     - Name: `NEXT_PUBLIC_API_BASE`
     - Value: your Cloudflare Tunnel URL from Step 2 (e.g. `https://random-words-1234.trycloudflare.com`) — **no trailing slash**
4. Click **Deploy**. After ~1–2 min you get `https://your-app.vercel.app`.

---

## STEP 4 — Share it

Send people **`https://your-app.vercel.app`**. Their browser loads the frontend from Vercel and calls your laptop's backend through the tunnel. Everything (investigations, uploads, OCR, SAR export) runs on your machine.

**Keep running the whole time:** Ollama · `python server.py` · `cloudflared tunnel`. If any stops, the app can't reach the backend.

---

## Troubleshooting

- **Frontend loads but shows "Cannot reach backend"** → the tunnel or backend stopped, or `NEXT_PUBLIC_API_BASE` on Vercel doesn't match the current tunnel URL. Re-check the URL and redeploy on Vercel.
- **Tunnel URL changed after a restart** → update `NEXT_PUBLIC_API_BASE` in Vercel → Settings → Environment Variables → **Redeploy**.
- **Investigations hang** → Ollama isn't running on your laptop.
- **Slow** → the LLM runs on your laptop's CPU/GPU; performance depends on your machine. Fine for a demo.
- **Everything works locally but not for others** → make sure you tested the *tunnel* URL (Step 2), not `localhost`.

---

## Want an always-on, stable URL later?

The free `trycloudflare.com` URL changes each restart. For a stable custom domain that survives restarts, create a **named Cloudflare Tunnel** (free Cloudflare account + a domain):
```powershell
cloudflared tunnel login
cloudflared tunnel create compliguard
# map a hostname (e.g. api.yourdomain.com) to http://localhost:8000, then:
cloudflared tunnel run compliguard
```
Then point `NEXT_PUBLIC_API_BASE` at `https://api.yourdomain.com` once and never touch it again.
For 24/7 hosting without your laptop, move the backend + Ollama to a GPU VM (see the deck's roadmap) — but for the hackathon, laptop + tunnel is the fastest path.
```
