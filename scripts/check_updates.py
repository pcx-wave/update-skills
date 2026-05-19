#!/usr/bin/env python3
"""
Check ~/.claude/skills/ for updates via GitHub API using .skill-source metadata.

Usage:
    python scripts/check_updates.py
    python scripts/check_updates.py --json
    python scripts/check_updates.py --skill vibe
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


SKILLS_DIR = Path.home() / ".claude" / "skills"
SOURCE_FILENAME = ".skill-source"


def github_get(url: str, token: str) -> dict | None:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Request failed: {e}", file=sys.stderr)
        return None


def fetch_raw(url: str) -> str | None:
    """Fetch raw content from a URL, no auth needed."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def check_skill_no_token(skill_dir: Path, repo: str, path: str, last_sha: str | None) -> dict:
    """Fallback: compare local SKILL.md content vs remote. No API, no token."""
    name = skill_dir.name
    skill_md_path = f"{path}/SKILL.md" if path else "SKILL.md"
    raw_url = f"https://raw.githubusercontent.com/{repo}/main/{skill_md_path}"

    remote_content = fetch_raw(raw_url)
    if remote_content is None:
        # Try lowercase skill.md as fallback
        skill_md_path_lower = skill_md_path.replace("SKILL.md", "skill.md")
        raw_url = f"https://raw.githubusercontent.com/{repo}/main/{skill_md_path_lower}"
        remote_content = fetch_raw(raw_url)
    if remote_content is None:
        return {"name": name, "status": "error", "repo": repo, "error": "could not fetch remote SKILL.md"}

    local_skill_md = skill_dir / "SKILL.md"
    try:
        local_content = local_skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"name": name, "status": "error", "repo": repo, "error": "could not read local SKILL.md"}

    if local_content.strip() == remote_content.strip():
        return {
            "name": name,
            "status": "up_to_date",
            "repo": repo,
            "local_sha": "current",
            "remote_sha": "current",
            "method": "content-compare",
        }
    return {
        "name": name,
        "repo": repo,
        "status": "update_available",
        "local_sha": "local",
        "remote_sha": "remote",
        "commits_behind": 1,
        "approximate": True,
        "method": "content-compare",
    }


def check_skill(skill_dir: Path, token: str) -> dict:
    name = skill_dir.name
    source_file = skill_dir / SOURCE_FILENAME

    if not source_file.exists():
        return {"name": name, "status": "no_source"}

    try:
        with open(source_file) as f:
            source = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"name": name, "status": "error", "error": str(e)}

    repo = source.get("repo", "")
    path = source.get("path", "")
    last_sha = source.get("last_sha")

    if not repo:
        return {"name": name, "status": "no_source", "error": "repo field empty"}

    if not token:
        return check_skill_no_token(skill_dir, repo, path, last_sha)

    # With token: fetch last 10 commits on the skill path — precise SHA comparison
    commits_url = f"https://api.github.com/repos/{repo}/commits?path={path}&per_page=10"
    commits_data = github_get(commits_url, token)
    if not isinstance(commits_data, list) or len(commits_data) == 0:
        # API failed despite token — fall back to content compare
        return check_skill_no_token(skill_dir, repo, path, last_sha)

    latest_sha = commits_data[0].get("sha", "")
    if not latest_sha:
        return {"name": name, "status": "error", "error": "empty sha in response"}

    if last_sha is not None and latest_sha == last_sha:
        return {
            "name": name,
            "status": "up_to_date",
            "repo": repo,
            "local_sha": last_sha[:7],
            "remote_sha": latest_sha[:7],
        }

    shas = [c.get("sha", "") for c in commits_data]
    if last_sha in shas:
        commits_behind = shas.index(last_sha)
        approximate = False
    else:
        commits_behind = 10
        approximate = True

    return {
        "name": name,
        "repo": repo,
        "status": "update_available",
        "local_sha": (last_sha or "")[:7] or "none",
        "remote_sha": latest_sha[:7],
        "commits_behind": commits_behind,
        "approximate": approximate,
    }


def print_report(results: list[dict]):
    up_to_date = [r for r in results if r["status"] == "up_to_date"]
    updates = [r for r in results if r["status"] == "update_available"]
    no_source = [r for r in results if r["status"] == "no_source"]
    errors = [r for r in results if r["status"] == "error"]

    print(f"\nSkills Status")
    print(f"{'=' * 40}")

    if up_to_date:
        print(f"\nUp-to-date ({len(up_to_date)}):")
        for r in sorted(up_to_date, key=lambda x: x["name"]):
            print(f"   {r['name']} ({r['local_sha'][:7]})")

    if updates:
        print(f"\nUpdates Available ({len(updates)}):")
        for r in sorted(updates, key=lambda x: x["name"]):
            behind = r.get("commits_behind", "?")
            approx = r.get("approximate", False)
            count_str = f"{behind}+" if approx else str(behind)
            commits_label = f"{count_str} commit{'s' if behind != 1 else ''} behind"
            print(f"   {r['name']} ({r.get('repo', '?')})")
            print(f"     {r.get('local_sha', 'N/A')} → {r['remote_sha']}  ({commits_label})")

    if no_source:
        print(f"\nNo source ({len(no_source)}):")
        for r in sorted(no_source, key=lambda x: x["name"]):
            print(f"   {r['name']}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for r in sorted(errors, key=lambda x: x["name"]):
            print(f"   {r['name']}: {r.get('error', '')}")

    print(f"\n{'=' * 40}")
    print(f"Total: {len(results)} skills | {len(updates)} update{'s' if len(updates) != 1 else ''} available")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Output as JSON array")
    parser.add_argument("--skill", type=str, help="Check only this skill name")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")

    if not SKILLS_DIR.exists():
        print(f"Skills directory not found: {SKILLS_DIR}", file=sys.stderr)
        sys.exit(1)

    skill_dirs = sorted(
        [d for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
    )
    if args.skill:
        target = SKILLS_DIR / args.skill
        if target in skill_dirs:
            skill_dirs = [target]
        else:
            print(f"Skill '{args.skill}' not found", file=sys.stderr)
            sys.exit(1)

    results = []
    for i, skill_dir in enumerate(skill_dirs):
        result = check_skill(skill_dir, token)
        results.append(result)
        if i < len(skill_dirs) - 1:
            time.sleep(0.5)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)

    has_updates = any(r["status"] == "update_available" for r in results)
    sys.exit(1 if has_updates else 0)


if __name__ == "__main__":
    main()
