# work-google-mcp

A local MCP server that connects Claude (or any MCP client) to a **second, isolated Google account** — built specifically for the case where you already have one Google account wired up and need a separate one for work.

- **Strict account isolation**: separate OAuth client, separate token file, server name, and an account-pin guard that refuses to start if the cached credentials match a different email than the one you pinned.
- **Phase 1 (current)**: Gmail read-only.
- **Phased roadmap**: Drive read → Gmail write → Drive write / Calendar.
- **Local stdio transport**: runs as a subprocess of your MCP client. No remote service, no shared state.
- **Python + FastMCP**: official MCP Python SDK, official Google API client.

> Status: 🟡 Phase 1 (Gmail read-only). See [roadmap](#roadmap).

---

## Quickstart

### 1. Create a Google Cloud project + OAuth client

See [docs/setup.md](docs/setup.md) for the full walkthrough. Summary:

1. Create a new GCP project (recommended: under a **personal** Google account so revoking your work account never breaks the OAuth client).
2. Enable the **Gmail API**.
3. Configure the OAuth consent screen: User type = External, Publishing status = Testing, add your **work** email as a test user.
4. Create an OAuth client of type **Desktop app** and download the JSON.
5. Save the JSON to `~/.config/work-google-mcp/client_secrets.json` (chmod 600).

### 2. Install

Requires Python 3.11+. We use [uv](https://docs.astral.sh/uv/) but `pip` works equally well.

```bash
git clone https://github.com/k1sina/work-google-mcp.git
cd work-google-mcp
uv sync                   # or: python -m venv .venv && .venv/bin/pip install -e .
```

### 3. First-run authorization

```bash
export WORK_GOOGLE_MCP_PINNED_EMAIL=you@yourcompany.com
uv run work-google-mcp --login
```

A browser window opens, you sign in with your **work** Google account, and the token is cached to `~/.config/work-google-mcp/token.json`. From now on the server starts silently.

### 4. Add to your MCP client

See [docs/claude-config.md](docs/claude-config.md) for Claude Code and Claude Desktop snippets.

For Claude Code (`~/.claude.json`):

```json
{
  "mcpServers": {
    "work-google": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/work-google-mcp", "run", "work-google-mcp"],
      "env": {
        "WORK_GOOGLE_MCP_PINNED_EMAIL": "you@yourcompany.com"
      }
    }
  }
}
```

Restart Claude. Ask it: *"Use the work-google MCP — search my work email for unread messages from today."*

---

## Tools (Phase 1)

| Tool | What it does |
|---|---|
| `gmail_whoami` | Returns the authenticated email + signature. Use it to confirm you're on the right account. |
| `gmail_list_labels` | Lists label IDs and names. |
| `gmail_search_messages` | Searches messages with Gmail query syntax (`from:`, `to:`, `subject:`, `is:unread`, `after:YYYY/MM/DD`, etc.). Header-only results; supports pagination. |
| `gmail_search_threads` | Same but thread-grouped. |
| `gmail_get_message` | Returns a full message by ID. Decodes MIME parts and lists attachments (does not download in Phase 1). Cap body length with `max_body_chars`. |
| `gmail_get_thread` | Returns a full thread by ID with per-message ordering. |

All tools are read-only and annotated as such. Inputs are validated with Pydantic.

---

## Account isolation

This is the whole point of the project. Three layers:

1. **Separate OAuth client.** You create a dedicated Desktop OAuth client in your own GCP project. It has no relationship to whatever your primary Google MCP uses.
2. **Separate token file.** Default `~/.config/work-google-mcp/token.json`. Path is configurable per environment.
3. **Account-pin guard.** Set `WORK_GOOGLE_MCP_PINNED_EMAIL=you@yourcompany.com`. On every startup, the server calls `users().getProfile(userId='me')` and asserts the returned email matches the pin. If it doesn't, the process exits with a loud error instead of silently leaking your other account into agent responses.

If you ever suspect drift, delete the token file and re-run `--login`.

---

## Roadmap

- **Phase 1** ✅ Gmail read-only (this release).
- **Phase 2** Drive read-only: `drive_search_files`, `drive_get_file_metadata`, `drive_read_file_content` (with Google Docs/Sheets/Slides export), `drive_list_recent_files`, `drive_get_file_permissions`.
- **Phase 3** Gmail write: drafts, send, label modification, trash. `destructiveHint: true` where appropriate.
- **Phase 4** Drive write + Calendar.

Each phase adds an incremental OAuth scope — you'll re-authorize once when scopes change.

---

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy
uv run pytest
```

CI runs all three on every PR.

---

## License

MIT. See [LICENSE](LICENSE).
