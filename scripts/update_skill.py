#!/usr/bin/env python3
"""
Download latest files from GitHub for skills with .skill-source metadata.

Usage:
    python scripts/update_skill.py all
    python scripts/update_skill.py vibe geo
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


SKILLS_DIR = Path.home() / ".claude" / "skills"
BACKUPS_DIR = SKILLS_DIR / ".backups"
SOURCE_FILENAME = ".skill-source"
CHECK_UPDATES_SCRIPT = Path(__file__).resolve().parent / "check_updates.py"


def backup_skill(skill_dir: Path, sha: str) -> Path:
    backup_path = BACKUPS_DIR / skill_dir.name / sha[:7]
    if backup_path.exists():
        shutil.rmtree(backup_path)
    shutil.copytree(skill_dir, backup_path)
    return backup_path


def revert_skill(skill_dir: Path) -> tuple[bool, str]:
    name = skill_dir.name
    source_file = skill_dir / SOURCE_FILENAME

    try:
        with open(source_file) as f:
            source = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"{name}: failed to read source: {e}"

    previous_sha = source.get("previous_sha")
    if not previous_sha:
        return False, f"{name}: no previous version to revert to"

    backup_path = BACKUPS_DIR / name / previous_sha[:7]
    if not backup_path.exists():
        return False, f"{name}: backup for {previous_sha[:7]} not found"

    shutil.rmtree(skill_dir)
    shutil.copytree(backup_path, skill_dir)
    return True, f"{name}: reverted to {previous_sha[:7]}"


def github_get(url: str, token: str) -> dict | list | None:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Request failed: {e}", file=sys.stderr)
        return None


def update_one_skill(skill_dir: Path, token: str) -> tuple[bool, str, int]:
    """
    Update a single skill from its .skill-source.
    Returns (success, message, files_updated_count).
    """
    name = skill_dir.name
    source_file = skill_dir / SOURCE_FILENAME

    if not source_file.exists():
        return False, f"{name}: no .skill-source", 0

    try:
        with open(source_file) as f:
            source = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"{name}: failed to read source: {e}", 0

    repo = source.get("repo", "")
    repo_path = source.get("path", "")
    old_sha = source.get("last_sha")
    previous_sha = source.get("previous_sha")

    if not repo:
        return False, f"{name}: repo field empty", 0

    # Step 1: get latest commit SHA
    commit_url = f"https://api.github.com/repos/{repo}/commits?path={repo_path}&per_page=1"
    commit_data = github_get(commit_url, token)
    if not isinstance(commit_data, list) or len(commit_data) == 0:
        return False, f"{name}: no commits found", 0

    latest_sha = commit_data[0].get("sha", "")
    if not latest_sha:
        return False, f"{name}: empty SHA", 0

    # Step 2: get file tree at latest commit
    tree_url = f"https://api.github.com/repos/{repo}/git/trees/{latest_sha}?recursive=1"
    tree_data = github_get(tree_url, token)
    if not isinstance(tree_data, dict) or "tree" not in tree_data:
        return False, f"{name}: no tree data", 0

    # Step 3: filter tree items
    prefix = repo_path.strip("/")
    prefix_slash = prefix + "/" if prefix else ""

    items = tree_data["tree"]
    relevant = [it for it in items if it.get("type") == "blob"]
    if prefix:
        relevant = [it for it in relevant if it["path"].startswith(prefix_slash)]

    if not relevant:
        return False, f"{name}: no files found in tree", 0

    # Step 4: backup current version before overwriting
    if old_sha:
        backup_skill(skill_dir, old_sha)

    # Step 5: download each file
    raw_base = f"https://raw.githubusercontent.com/{repo}/{latest_sha}"
    updated_count = 0

    for item in relevant:
        file_path = item["path"]
        # Compute relative path within the skill
        if prefix:
            rel_path = file_path[len(prefix_slash):]
        else:
            rel_path = file_path

        local_path = skill_dir / rel_path
        raw_url = f"{raw_base}/{file_path}"

        try:
            req = urllib.request.Request(raw_url)
            if token:
                req.add_header("Authorization", f"token {token}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()

            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)
            updated_count += 1

        except Exception as e:
            print(f"  Warning: failed to download {file_path}: {e}", file=sys.stderr)

    # Step 6: update .skill-source with new SHA, keep previous for revert
    source["previous_sha"] = old_sha
    source["last_sha"] = latest_sha
    with open(source_file, "w") as f:
        json.dump(source, f, indent=2)
        f.write("\n")

    old_display = old_sha[:7] if old_sha else "None"
    new_display = latest_sha[:7]
    return True, f"{name}: {old_display} -> {new_display} ({updated_count} files)", updated_count


def get_skills_with_updates(token: str) -> list[str]:
    """Run check_updates.py --json to find skills with update_available."""
    try:
        result = subprocess.run(
            [sys.executable, str(CHECK_UPDATES_SCRIPT), "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode not in (0, 1):
            print(f"check_updates.py failed: {result.stderr}", file=sys.stderr)
            return []
        data = json.loads(result.stdout)
        return [r["name"] for r in data if r.get("status") == "update_available"]
    except Exception as e:
        print(f"Failed to get updates list: {e}", file=sys.stderr)
        return []


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/update_skill.py <skill_name> [skill_name ...] | all", file=sys.stderr)
        print("       python scripts/update_skill.py --revert <skill_name> [skill_name ...]", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("GITHUB_TOKEN", "")

    if sys.argv[1] == "--revert":
        names = sys.argv[2:]
        if not names:
            print("Usage: --revert <skill_name> [skill_name ...]", file=sys.stderr)
            sys.exit(1)
        for name in names:
            skill_dir = SKILLS_DIR / name
            ok, msg = revert_skill(skill_dir)
            print(f"  {'[OK]' if ok else '[FAIL]'} {msg}")
        return

    target_names = sys.argv[1:]

    if "all" in target_names:
        target_names = get_skills_with_updates(token)
        if not target_names:
            print("No skills with updates available.")
            return

    if not SKILLS_DIR.exists():
        print(f"Skills directory not found: {SKILLS_DIR}", file=sys.stderr)
        sys.exit(1)

    results = []
    for i, name in enumerate(target_names):
        skill_dir = SKILLS_DIR / name
        if not skill_dir.is_dir():
            print(f"Warning: skill '{name}' not found, skipping", file=sys.stderr)
            results.append((name, False, "not found", 0))
            continue

        success, msg, count = update_one_skill(skill_dir, token)
        icon = "OK" if success else "FAIL"
        print(f"  [{icon}] {msg}")
        results.append((name, success, msg, count))

        if i < len(target_names) - 1:
            time.sleep(0.5)

    total_updated = sum(r[3] for r in results if r[1])
    total_failed = sum(1 for r in results if not r[1])
    print(f"\nDone. {total_updated} files updated across {len(target_names)} skills"
          f"{f' ({total_failed} failed)' if total_failed else ''}.")

    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
