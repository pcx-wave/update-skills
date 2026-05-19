# update-skills

Scan and update manually installed Claude Code skills in ~/.claude/skills/.

## When to use
- user says: check skill updates, update my skills, are my skills up to date
- user says: find source for skills, resolve skill repos
- user says: update <skill-name>, update all skills
- user says: revert <skill-name>

## Full interactive flow

### Step 1 — Check GITHUB_TOKEN

```bash
echo ${GITHUB_TOKEN:+set} ${GITHUB_TOKEN:-(not set)}
```

If not set: tell the user to add it to ~/.bashrc and ~/.zshrc, then reload with:
```bash
export $(grep GITHUB_TOKEN ~/.bashrc | head -1)
```

### Step 2 — Count skills missing .skill-source

```bash
ls ~/.claude/skills/*/.skill-source 2>/dev/null | wc -l
ls -d ~/.claude/skills/*/ 2>/dev/null | wc -l
```

If all skills have .skill-source → skip to Step 4.

### Step 3 — Resolve missing sources (Claude does this, not a script)

For each skill missing .skill-source:

1. Read first 10 lines of local SKILL.md (or README.md if present)
2. Pick a verbatim phrase of 4-6 words from those lines
3. Search via DuckDuckGo (NOT Google — DuckDuckGo indexes more GitHub repos):
   WebFetch: https://html.duckduckgo.com/html/?q=github+<skill-name>+<verbatim+phrase+url-encoded>
   Extract all github.com URLs from results
4. For EACH candidate repo:
   - Fetch first 10 lines of remote SKILL.md or README
   - Compare verbatim with local first 10 lines
   - REJECT if no sentence matches verbatim
5. Among validated candidates → pick the one with most verbatim matches
6. If 0 validated → try a different verbatim phrase and repeat once
7. Write .skill-source only after verbatim validation:

```json
{
  "repo": "owner/repo",
  "path": "path/to/skill/in/repo",
  "confidence": "verbatim-match",
  "last_sha": null,
  "previous_sha": null
}
```

Do this for all unresolved skills before continuing.
If WebSearch finds nothing → mark as unresolvable, skip.

**Do skills in batches of 5** to avoid burning too many tokens at once.
Offer to continue to the next batch or stop after each batch.

### Step 4 — Check for updates

```bash
python ~/.claude/skills/update-skills/scripts/check_updates.py
```

Present results:
```
⬆️  Updates available (3):
   • vibe    (pcx-wave/vibe-skill)           a1b2c3 → d4e5f6  (5 commits behind)
   • geo     (owner/repo)                    111111 → 222222  (1 commit behind)
   • gemini  (pcx-wave/gemini-skill)         aaaaaa → bbbbbb  (3 commits behind)

✅ Up-to-date (30)
⚠️  No source found (3): skill-x, skill-y, skill-z
```

### Step 5 — Ask what to do

If updates available:
1. Update all
2. Choose specific skills
3. Skip

### Step 6 — Update

```bash
python ~/.claude/skills/update-skills/scripts/update_skill.py all
# or
python ~/.claude/skills/update-skills/scripts/update_skill.py vibe geo gemini
```

### Step 7 — Report

```
✅ Updated 3 skills:
   • vibe    a1b2c3 → d4e5f6  (14 files)
   • geo     111111 → 222222  (2 files)
   • gemini  aaaaaa → bbbbbb  (6 files)

Backups saved to ~/.claude/skills/.backups/
To revert: "revert vibe" or "revert all"
```

### Revert

```bash
python ~/.claude/skills/update-skills/scripts/update_skill.py --revert vibe
```

## Notes

### GITHUB_TOKEN
- **With token** (`export GITHUB_TOKEN=...` in ~/.bashrc and ~/.zshrc): full SHA-based comparison via GitHub API. Reliable for any number of checks. Recommended.
- **Without token**: fallback to SKILL.md content comparison (local vs remote raw file). Works for occasional use but GitHub unauthenticated API is rate-limited (60 req/hour) — results become inconsistent if run multiple times in quick succession.
- Token only needed for `check_updates.py` and `update_skill.py`. Source resolution (Step 3) uses DuckDuckGo — no token needed.
- To add token permanently: `echo 'export GITHUB_TOKEN=<token>' >> ~/.bashrc && echo 'export GITHUB_TOKEN=<token>' >> ~/.zshrc`

### Other
- Backups: one version per skill in ~/.claude/skills/.backups/<name>/<sha>/
- check_updates.py exits with code 1 if updates available (useful for scripting)
- update-skills itself has no .skill-source — it manages itself via git
