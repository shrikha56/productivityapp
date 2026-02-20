# Deploy Signal landing page (Supabase + custom domain)

## 1. Supabase

1. Go to [supabase.com](https://supabase.com) and create a project.
2. In **SQL Editor**, run the contents of `supabase-setup.sql` (creates `signups` table).
3. In **Project Settings → API** copy:
   - **Project URL** → use as `SUPABASE_URL`
   - **service_role** key (under "Project API keys") → use as `SUPABASE_SERVICE_ROLE_KEY`  
   Keep the service role key secret (backend only).

## 2. Deploy backend (Render)

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) and sign in with GitHub.
3. **New → Web Service**, connect the repo, then:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn server:app`
   - **Instance type:** Free
4. In **Environment** add:
   - `SUPABASE_URL` = your Supabase project URL
   - `SUPABASE_SERVICE_ROLE_KEY` = your service_role key
5. Deploy. You’ll get a URL like `https://signal-landing.onrender.com`.

## 3. Custom domain (cheap domain)

**Buy a domain** from any registrar (e.g. Namecheap, Google Domains, Cloudflare, Porkbun).  
Then attach it to Render:

1. In Render: your service → **Settings → Custom Domains → Add custom domain**.
2. Enter your domain (e.g. `signalyourcareer.com` or `www.signalyourcareer.com`).
3. Render will show either:
   - A **CNAME** target (e.g. `signal-landing.onrender.com`), or
   - An **A** record IP.
4. In your domain registrar’s DNS:
   - For **root** (e.g. `signalyourcareer.com`): add the A record Render gives you, or a CNAME to the Render hostname if the registrar allows CNAME on root (e.g. Cloudflare).
   - For **www** (e.g. `www.signalyourcareer.com`): add a CNAME to `signal-landing.onrender.com` (or whatever Render shows).
5. Wait for DNS to propagate (minutes to 48 hours). Render will issue SSL for your domain.

After that, open your domain in a browser; the landing page and “Request Access” / “Join Beta” will hit the same backend and store emails in Supabase.
