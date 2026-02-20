# Deploy Signal to Vercel + signal-au.com

## 1. Push to GitHub

```bash
cd /Users/shrikha/productivity
git init
git add .
git commit -m "Signal landing page"
```

Create a repo at [github.com/new](https://github.com/new) (e.g. `signal-landing`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/signal-landing.git
git branch -M main
git push -u origin main
```

## 2. Deploy on Vercel

1. Go to **[vercel.com](https://vercel.com)** and sign in with GitHub.
2. **Add New** → **Project**.
3. Import the `signal-landing` repo.
4. **Environment Variables** → add:
   - `SUPABASE_URL` = `https://xmxzunophhboyfidicof.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY` = your service_role key from Supabase (Project Settings → API)
5. **Deploy**. You’ll get a URL like `https://signal-landing.vercel.app`.

## 3. Add domain signal-au.com

1. In Vercel: your project → **Settings** → **Domains**.
2. **Add** → enter `signal-au.com` and `www.signal-au.com`.
3. Vercel will show DNS records. In **GoDaddy** (Domains → signal-au.com → DNS):
   - For **www**: CNAME, Name `www`, Value `cname.vercel-dns.com` (or what Vercel shows)
   - For **root** (`@`): A record, Value `76.76.21.21` (Vercel’s IP) — or use Vercel’s exact instructions
4. Wait for DNS to propagate. Vercel will issue SSL automatically.
