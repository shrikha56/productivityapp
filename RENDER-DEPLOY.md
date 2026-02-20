# Deploy Signal to Render — step-by-step

## 1. Push to GitHub

If the `productivity` folder isn't its own GitHub repo yet:

```bash
cd /Users/shrikha/productivity
git init
git add .
git commit -m "Signal landing page + Supabase backend"
```

Create a new repo on [github.com/new](https://github.com/new) (e.g. `signal-landing`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/signal-landing.git
git branch -M main
git push -u origin main
```

## 2. Deploy on Render

1. Go to **[render.com](https://render.com)** and sign in with GitHub.
2. **New +** → **Web Service**.
3. Connect the `signal-landing` repo (or the repo that contains this folder).
4. If the repo root is different, set **Root Directory** to `productivity` (or leave blank if the repo root is this folder).
5. Use:
   - **Name:** signal-landing
   - **Region:** Oregon (or closest)
   - **Branch:** main
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn server:app`
   - **Instance Type:** Free
6. **Environment** → **Add Environment Variable:**
   - `SUPABASE_URL` = `https://xmxzunophhboyfidicof.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY` = your service_role key from Supabase (Project Settings → API)
7. **Create Web Service**. Wait for the build and deploy.
8. Your app will be at `https://signal-landing.onrender.com` (or the URL Render shows).

## 3. Add custom domain (signal-au.com)

1. In Render: your service → **Settings** → **Custom Domains** → **Add Custom Domain**.
2. Enter `signal-au.com` and `www.signal-au.com`.
3. In GoDaddy → **DNS** for signal-au.com:
   - For **www**: CNAME, Name `www`, Value `signal-landing.onrender.com`
   - For **root** (`@`): add the A record Render provides (or use GoDaddy redirect so `signal-au.com` → `www.signal-au.com`).
4. After DNS propagates, Render will provision SSL.
