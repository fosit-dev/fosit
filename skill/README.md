# FOSIT skill for Claude

A [Claude skill](https://docs.claude.com/en/docs/claude-code/skills) that lets Claude plan, lock and read FOSIT geo-lift tests for you: it interviews you, checks your data, runs FOSIT's own engine, locks the plan with a fingerprint, and explains results in plain English (including a CFO summary). Every number comes from the same engine as the web app; plans made with the skill and with the web app read each other.

## Install (Claude Code)

```bash
git clone https://github.com/fosit-dev/fosit
mkdir -p ~/.claude/skills && cp -R fosit/skill/fosit ~/.claude/skills/fosit
```

Or, if you were given the packaged `fosit.skill` file, install that. Then just ask, for example: *"We want two CTV vendors to split the country 40/40 with a 20% no-CTV group. Here's our daily sales by state: can you plan it?"*

Requirements: Python 3.12+ (or [`uv`](https://docs.astral.sh/uv/), which fetches Python itself) and internet on first use, when the skill installs FOSIT's engine (pinned version) into `~/.fosit`.

## Privacy

The web app never uploads your data. With the skill, **Claude reads what you give it**. FOSIT only needs daily totals by market (no customer data), and the skill works from the engine's summaries rather than reading raw rows; it says so before it opens anything. If nothing may leave your machine, use the web app.

## What's inside

- `fosit/SKILL.md`: how Claude runs a test, and the rules it protects (pre-registration, "inconclusive" is allowed, vendor-neutral).
- `fosit/scripts/fosit_cli.py`: the command-line wrapper around FOSIT's engine (`check`, `orders`, `sample`, `plan`, `lock`, `verify`, `read`).
- `fosit/references/`: choosing a design, data formats, explaining results.
- `fosit/evals/`: test cases (run with `claude plugin eval fosit --scaffold --allow-tools Write,Edit,Bash`).
