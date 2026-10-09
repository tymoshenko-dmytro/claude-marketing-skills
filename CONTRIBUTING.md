# Contributing

Thanks for helping. This kit is a set of templates, so the most useful contributions are small and concrete.

## What helps most

- **A fix** to a skill that gave a wrong result, with the request you made and what came back.
- **A connection guide update** when a vendor changes its setup, pricing or API (`connections/`).
- **A new "Adapt it" note**: how you changed a skill for your own work, so others can do the same.
- **Docs**: a step that confused you, written more clearly.

New skills are welcome too. Open a [discussion](https://github.com/tymoshenko-dmytro/claude-marketing-skills/discussions) first, so we can agree on the scope before you write it.

## How to send a change

1. Fork the repository and make a branch.
2. Keep one change per pull request.
3. Test it: run the skill on a real task in Claude Code, and run any script you touched.
4. Never commit API keys, client data or research output (`raw/`, `dist/`, catalogues).
5. Open the pull request and say what you changed, why, and how you tested it.

## Skill style

- `SKILL.md` stays short. Long material goes to `references/`.
- Scripts use the Python standard library where possible.
- Keys are read from `~/.config/marketing-agent-kit/.env`, never from the chat.
- Plain English: a stranger should understand each line in one read.

## Questions

Ask in [Discussions](https://github.com/tymoshenko-dmytro/claude-marketing-skills/discussions). Report bugs as [issues](https://github.com/tymoshenko-dmytro/claude-marketing-skills/issues/new/choose).
