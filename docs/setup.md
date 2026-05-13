# Setup: Google Cloud project and OAuth client

This server requires an OAuth client you control. You won't share credentials with anyone — the OAuth flow runs entirely on your laptop and only the resulting token (which represents *you*, signed in to your **work** account) is cached locally.

The recommended setup creates the GCP project under a **personal** Google account, so that if your employer ever revokes your work account, the OAuth client itself keeps working. The OAuth client is what's owned by the project — the *user identity* it authorizes is separate.

---

## 1. Create a Google Cloud project

1. Open https://console.cloud.google.com/ and sign in with the account that should **own** the GCP project (a personal account is fine; recommended).
2. Click the project picker (top bar) → **New Project**.
3. Name it something like `work-google-mcp` and create it.
4. Make sure the project is selected in the project picker before proceeding.

## 2. Enable the Gmail API

1. Go to https://console.cloud.google.com/apis/library/gmail.googleapis.com.
2. Click **Enable**.

(For Phase 2 you'll also enable the Drive API at https://console.cloud.google.com/apis/library/drive.googleapis.com.)

## 3. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**.
2. **User type**: External. (Internal is only available if the project is owned by a Workspace account; External works for everyone and is the simpler choice.)
3. **App information**:
   - App name: `work-google-mcp`
   - User support email: your email
   - Developer contact: your email
4. **Scopes**: skip — the application requests scopes at runtime; you don't need to pre-declare them on the consent screen for a Testing-mode app.
5. **Test users**: add your **work** email address. This is the account whose mailbox the server will read.
6. Save and exit. Keep the **Publishing status** as **Testing** — that's exactly what we want. Tokens for testing-mode apps expire after 7 days; the OAuth flow will simply prompt you again when that happens. (To remove the 7-day limit you'd publish the app, which requires Google's verification process — overkill for personal use.)

## 4. Create a Desktop OAuth client

1. Go to **APIs & Services → Credentials → + Create credentials → OAuth client ID**.
2. **Application type**: **Desktop app**.
3. Name it `work-google-mcp desktop`.
4. Click **Create**, then **Download JSON**.

## 5. Place the secrets file

```bash
mkdir -p ~/.config/work-google-mcp
mv ~/Downloads/client_secret_*.json ~/.config/work-google-mcp/client_secrets.json
chmod 600 ~/.config/work-google-mcp/client_secrets.json
```

If you'd rather keep it elsewhere, set `WORK_GOOGLE_MCP_CLIENT_SECRETS=/your/path` in your environment.

## 6. First-time authorization

```bash
export WORK_GOOGLE_MCP_PINNED_EMAIL=you@yourcompany.com
uv run work-google-mcp --login
```

A browser window opens. **Sign in with your work account** when prompted. (You may see an "unverified app" warning — click *Advanced → Go to work-google-mcp*. It's unverified because you control the project; only you can use it.)

On success the token is written to `~/.config/work-google-mcp/token.json` (chmod 600) and you'll see:

```
Authorized as you@yourcompany.com.
Token cached to /Users/you/.config/work-google-mcp/token.json.
```

## 7. Test the connection

```bash
uv run work-google-mcp
```

The server will start, print `authenticated as you@yourcompany.com` to stderr, then wait for MCP traffic on stdin. Press `Ctrl-C` to exit — this confirmed it can reach Google and the account-pin guard passes.

You're done. Continue with [claude-config.md](claude-config.md) to wire it into your MCP client.

---

## Troubleshooting

- **`OAuth client secrets not found at …`** — step 5 above. Either place the file at the default path or set `WORK_GOOGLE_MCP_CLIENT_SECRETS`.
- **`Account pin check failed: Authenticated as personal@gmail.com, but WORK_GOOGLE_MCP_PINNED_EMAIL=work@…`** — you signed in with the wrong account. Delete `~/.config/work-google-mcp/token.json` and re-run `--login`. Sign in with the work account this time.
- **Token expires every 7 days** — Testing-mode OAuth apps have a 7-day refresh-token TTL. When it expires you'll see a refresh failure on the next call; run `--login` again. (If this gets annoying, you can publish the app via Google's verification process.)
- **"This app isn't verified" warning** — expected; the app is yours. Click *Advanced → Go to <app name>*.
- **403 errors** — usually a missing scope. Check that the scope your tool needs is in `CURRENT_SCOPES` in `src/work_google_mcp/config.py`, then delete the token and re-run `--login` to grant the new scope.
