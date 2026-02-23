# Supabase Auth Setup (for local testing)

For sign up and login to work locally, configure your Supabase project:

## 1. Disable email confirmation (required for local dev)

1. Go to [Supabase Dashboard](https://supabase.com/dashboard) → your project
2. **Authentication** → **Providers** → **Email**
3. Turn **OFF** "Confirm email"

Without this, sign up creates an account but you cannot log in until you click the confirmation email (which may not arrive or go to spam).

## 2. Add redirect URLs

1. **Authentication** → **URL Configuration**
2. **Site URL**: `http://localhost:5001` (must match exactly, including port)
3. **Redirect URLs** — add each on its own line:
   - `http://localhost:5001`
   - `http://localhost:5001/auth/callback`
   - `http://127.0.0.1:5001`
   - `http://127.0.0.1:5001/auth/callback`

Use the same URL in your browser. If you open `http://127.0.0.1:5001`, Site URL should be `http://127.0.0.1:5001`.

## 3. For production (signal-au.com)

Add these redirect URLs as well:

- `https://signal-au.com`
- `https://signal-au.com/auth/callback`

## Troubleshooting

- **"Invalid redirect URL"** — The URL in Redirect URLs must match exactly (no trailing slash, correct port).
- **Sign up works but login fails** — Turn off "Confirm email" in step 1.
- **Magic link doesn't redirect** — Add the callback URL to Redirect URLs. Check spam for the email.
