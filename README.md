# update-skills

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![stdlib only](https://img.shields.io/badge/stdlib-only-brightgreen)
![no token required](https://img.shields.io/badge/no%20token%20required-green)
![Claude Code skill](https://img.shields.io/badge/claude%20code-skill-purple)

**Stop losing track of where your Claude Code skills came from.**

## The problem

You've installed 30+ Claude Code skills. Some from GitHub. Some from gists. Some from that blog post you bookmarked but can't find again.

There's no `pip list` equivalent. No plugin marketplace. No update manager. Just a pile of `SKILL.md` files with no connection to their source. When a skill ships a bugfix, you won't know. Neither will Claude.

This is the gap between "it works" and "I can maintain it."

## What this skill does

- Discovers the canonical GitHub repo for each of your manually installed skills
- Tracks the exact commit SHA of what you have installed vs what's upstream
- Updates any skill — or all of them — with one command
- Rolls back if an update breaks something
- Zero pip dependencies. Zero API keys required. You're not locked into anything.

## Install

```bash
git clone https://github.com/pcx-wave/update-skills ~/.claude/skills/update-skills
```

## Usage

### Step 1 — Resolve sources (first time only)

Tell Claude to find where each skill originally came from:

> *"find the source repos for my skills"*

Claude reads each `SKILL.md`, searches verbatim phrases on DuckDuckGo, and writes a `.skill-source` file per skill. No script, no token. Done once.

### Step 2 — Check for updates

```bash
# Check all skills
python ~/.claude/skills/update-skills/scripts/check_updates.py

# Check a specific skill
python ~/.claude/skills/update-skills/scripts/check_updates.py --skill vibe
```

Compares local skill content against upstream (with `GITHUB_TOKEN`: SHA-by-SHA precision; without: content comparison via SKILL.md).

### Step 3 — Update

```bash
# Update every outdated skill at once
python ~/.claude/skills/update-skills/scripts/update_skill.py all

# Update specific skills
python ~/.claude/skills/update-skills/scripts/update_skill.py vibe geo
```

### Revert if something breaks

```bash
python ~/.claude/skills/update-skills/scripts/update_skill.py --revert vibe
python ~/.claude/skills/update-skills/scripts/update_skill.py --revert all
```

Previous versions are backed up automatically before each update.

## How source resolution works

1. Reads the `# Title` from each `SKILL.md` — that's the skill name
2. Searches DuckDuckGo for the skill name + common identifying phrases from the file
3. Matches results against `filename:SKILL.md` on GitHub or direct repo patterns
4. Ranks candidates by star count and path depth — the canonical repo usually wins
5. Writes a `.skill-source` file so this is a one-time cost

## `.skill-source` format

Each resolved skill directory gets a hidden JSON file:

```json
{
  "repo": "owner/repo",
  "path": "skills/vibe",
  "confidence": "unique",
  "last_sha": "a1b2c3d4e5f6789abcdef1234567890abcdef12",
  "previous_sha": "9f8e7d6c5b4a3210fedcba9876543210fedcba98"
}
```

## `GITHUB_TOKEN` — with vs without

| Without token | With `GITHUB_TOKEN` |
|---|---|
| DuckDuckGo + content comparison | GitHub API search + SHA comparison |
| Content-sensitive (detects actual file diffs) | SHA-sensitive (detects any upstream commit) |
| Works immediately, no config | Add to `.bashrc`/`.zshrc` for precision |

Either way works. The token just gives you SHA-level precision instead of content-level.

## Requirements

- **Python 3.10+** — no pip dependencies, no virtualenv, no node_modules
