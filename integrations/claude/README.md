# Zephyrus Claude Code Integration

This directory contains the Claude Code skill bundle for Zephyrus.

## User Flow

1. Open Zephyrus Settings > Integrations.
2. Add a Claude Agent.
3. Copy the full setup commands shown after the generated token.
4. Toggle the tools Claude is allowed to use.
5. Configure the terminal Claude Code session:

```bash
export ZEPHYRUS_URL=http://your-zephyrus-host:7000
export ZEPHYRUS_API_TOKEN=ody_generated_token
mkdir -p ~/.claude
curl -fsSL -H "Authorization: Bearer $ZEPHYRUS_API_TOKEN" "$ZEPHYRUS_URL/api/claude/plugin.zip" -o /tmp/zephyrus-claude-skill.zip
python3 -m zipfile -e /tmp/zephyrus-claude-skill.zip ~/.claude/
```

Claude Code auto-loads anything under `~/.claude/skills/`, so the `zephyrus` skill is
available in any session that has `ZEPHYRUS_URL` and `ZEPHYRUS_API_TOKEN` in its
environment.

## What's in the bundle

- `skills/zephyrus/SKILL.md` — the skill definition Claude Code reads.
- `skills/zephyrus/scripts/zephyrus_api.py` — small helper that calls the scoped
  `/api/codex/*` endpoints (these are the canonical scope-gated agent API; the
  `codex` path is historic and shared by all agent integrations).

## Scope enforcement

The token is scope-gated. Every tool surface is checked server-side in Zephyrus,
so even if Claude tries to call a forbidden endpoint, it gets `403` until the
user enables the matching toggle in Settings > Integrations > Claude Agent.
