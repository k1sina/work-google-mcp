# Wiring the server into your MCP client

Once `--login` has succeeded ([setup.md](setup.md)), the server can be launched as a subprocess by any MCP client. Below are configs for the two most common clients.

In all cases, **set `WORK_GOOGLE_MCP_PINNED_EMAIL`** so the server refuses to start if it ever ends up with a token for the wrong account.

## Claude Code (`~/.claude.json`)

Add an entry under `mcpServers`. If you already have a personal Google MCP, **use a different key** (we recommend `work-google`) so they coexist.

```json
{
  "mcpServers": {
    "work-google": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/work-google-mcp",
        "run",
        "work-google-mcp"
      ],
      "env": {
        "WORK_GOOGLE_MCP_PINNED_EMAIL": "you@yourcompany.com"
      }
    }
  }
}
```

If you installed via `pip install -e .` into a venv instead of `uv`, use:

```json
{
  "mcpServers": {
    "work-google": {
      "command": "/absolute/path/to/work-google-mcp/.venv/bin/work-google-mcp",
      "args": [],
      "env": {
        "WORK_GOOGLE_MCP_PINNED_EMAIL": "you@yourcompany.com"
      }
    }
  }
}
```

Restart Claude Code. The server should appear as `work-google`, and its tools will be prefixed with `gmail_` in tool listings.

## Claude Desktop (`claude_desktop_config.json`)

Same shape, different file location:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

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

Quit Claude Desktop fully and reopen.

## Verifying it's the work account

In a chat, ask the agent something like:

> Call `gmail_whoami` from the work-google server and tell me which account is connected.

It should return your work email. If it returns anything else, the server would have failed to start — check the client's MCP logs for the `Account pin check failed` message.

## Coexisting with your personal Google MCP

The two servers must not share:

- the OAuth client (you created a fresh one in [setup.md](setup.md))
- the token file (default path is unique to this project)
- the MCP server key in the config (use `work-google` rather than overloading `google`)

That's it — they run as independent subprocesses and never see each other's state.
