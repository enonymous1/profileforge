"""Verbatim copy of the legacy `format_event` from `update_activity.py`.

Test-only golden master for byte-parity checks (see
`tests/test_legacy_parity.py`). Never import this in production code.
"""

import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

README_PATH = os.environ.get("TARGET_FILE", "README.md")

EVENT_ICONS = {
    "PushEvent": "📦",
    "CreateEvent": "🌱",
    "ForkEvent": "🍴",
    "WatchEvent": "⭐",
    "IssuesEvent": "🐛",
    "IssueCommentEvent": "💬",
    "PullRequestEvent": "🔀",
    "ReleaseEvent": "🚀",
    "DeleteEvent": "🗑️",
    "PublicEvent": "📢",
}


def format_event(event):
    etype = event.get("type", "")
    repo = event.get("repo", {}).get("name", "unknown/unknown")
    repo_url = f"https://github.com/{repo}"
    icon = EVENT_ICONS.get(etype, "🔧")
    created_at = event.get("created_at", "")

    try:
        dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        date_str = dt.strftime("%b %d, %Y")
    except ValueError:
        date_str = created_at[:10]

    payload = event.get("payload", {})

    if etype == "PushEvent":
        commits = payload.get("commits", [])
        count = len(commits)
        noun = "commit" if count == 1 else "commits"
        branch = payload.get("ref", "refs/heads/main").replace("refs/heads/", "")
        return f"{icon} Pushed {count} {noun} to [`{repo}`]({repo_url}) on `{branch}` — {date_str}"

    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "repository")
        ref = payload.get("ref", "")
        if ref_type == "repository":
            return f"{icon} Created repository [`{repo}`]({repo_url}) — {date_str}"
        return f"{icon} Created {ref_type} `{ref}` in [`{repo}`]({repo_url}) — {date_str}"

    if etype == "ForkEvent":
        forkee = payload.get("forkee", {}).get("full_name", repo)
        return f"{icon} Forked [`{forkee}`](https://github.com/{forkee}) — {date_str}"

    if etype == "IssuesEvent":
        action = payload.get("action", "opened")
        issue = payload.get("issue", {})
        title = issue.get("title", "an issue")
        url = issue.get("html_url", repo_url)
        return f"{icon} {action.capitalize()} issue [{title}]({url}) in [`{repo}`]({repo_url}) — {date_str}"

    if etype == "IssueCommentEvent":
        issue = payload.get("issue", {})
        title = issue.get("title", "an issue")
        url = payload.get("comment", {}).get("html_url", repo_url)
        return f"{icon} Commented on [{title}]({url}) in [`{repo}`]({repo_url}) — {date_str}"

    if etype == "PullRequestEvent":
        action = payload.get("action", "opened")
        pr = payload.get("pull_request", {})
        title = pr.get("title", "a pull request")
        url = pr.get("html_url", repo_url)
        return f"{icon} {action.capitalize()} PR [{title}]({url}) in [`{repo}`]({repo_url}) — {date_str}"

    if etype == "ReleaseEvent":
        release = payload.get("release", {})
        tag = release.get("tag_name", "")
        url = release.get("html_url", repo_url)
        return f"{icon} Released [`{tag}`]({url}) in [`{repo}`]({repo_url}) — {date_str}"

    return None


def update_readme(lines):
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!--START_SECTION:activity-->"
    end_marker = "<!--END_SECTION:activity-->"

    if start_marker not in content or end_marker not in content:
        print("ERROR: Activity markers not found in README.", file=sys.stderr)
        sys.exit(1)

    new_section = start_marker + "\n"
    if lines:
        new_section += "\n".join(f"- {line}" for line in lines) + "\n"
    new_section += end_marker

    updated = re.sub(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        new_section,
        content,
        flags=re.DOTALL,
    )

    if updated == content:
        print("No changes to README.")
        return False

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"Updated README with {len(lines)} activity line(s).")
    return True


# --- Verbatim from export_to_md.py (interactive __main__ block omitted) ---

# Common deep or auxiliary directories to automatically skip during traversal
EXCLUDED_DIRS: set[str] = {
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".idea",
    ".vscode",
}


def generate_tree_markdown(py_files: list[Path], src_dir: Path) -> str:
    """Generate a hierarchical markdown tree representation of the codebase.

    Args:
        py_files: List of filtered Python file paths.
        src_dir: Root source directory.

    Returns:
        Formatted markdown code block representing directory tree hierarchy.
    """
    tree_lines = [
        "# Project File Structure (Python Scripts)\n",
        f"**Source Directory:** `{src_dir}`\n",
        "```text",
    ]

    tree: dict[str, Any] = {}
    for py_file in py_files:
        rel_path = py_file.relative_to(src_dir)
        current = tree
        for part in rel_path.parts:
            current = current.setdefault(part, {})

    def _add_to_tree(node: dict[str, Any], prefix: str = "") -> None:
        # Sort directories first (bool(node) is True for dirs, False for files),
        # then alphabetically
        items = sorted(node.keys(), key=lambda k: (not bool(node[k]), k.lower()))

        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            sub_node = node[item]

            if not sub_node:
                tree_lines.append(f"{prefix}{connector}{item}")
            else:
                tree_lines.append(f"{prefix}{connector}📁 {item}")
                extension = "    " if is_last else "│   "
                _add_to_tree(sub_node, prefix + extension)

    tree_lines.append(f"📁 {src_dir.name}")
    _add_to_tree(tree)
    tree_lines.append("```")
    return "\n".join(tree_lines)


def mirror_py_to_md(
    src_path: str | Path | None = None,
    dest_path: str | Path | None = None,
    rollup_dirs: bool = True,
) -> None:
    """Convert Python source files into Markdown documentation files, skipping junk paths.

    Args:
        src_path: Source code root directory.
        dest_path: Target directory for mirrored markdown files.
        rollup_dirs: If True, combines all .py files in a directory into a single
            Markdown file named after the directory.
    """
    src_dir = Path(src_path).resolve() if src_path else Path.cwd()
    dest_dir = (
        Path(dest_path).resolve() if dest_path else src_dir / "reports" / "markdown_src_directory"
    )

    if not src_dir.exists():
        LOGGER.warning("Source directory %s does not exist.", src_dir)
        return

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Recursively collect .py files while filtering out excluded directories
    raw_files = sorted(src_dir.rglob("*.py"))
    py_files: list[Path] = []

    for file_path in raw_files:
        # Check if any parent folder component matches our exclusion list
        if any(part in EXCLUDED_DIRS for part in file_path.parts):
            continue
        py_files.append(file_path)

    if not py_files:
        LOGGER.warning("No valid .py files discovered in %s after filtering.", src_dir)
        return

    # 1. Generate and persist project layout tree
    structure_content = generate_tree_markdown(py_files, src_dir)
    structure_file = dest_dir / "project_structure.md"
    structure_file.write_text(structure_content, encoding="utf-8")
    LOGGER.info("Created structure file: %s", structure_file)

    # 2. Mirror Python scripts to Markdown
    if rollup_dirs:
        # Group files by their parent directory
        grouped_files: dict[Path, list[Path]] = defaultdict(list)
        for py_file in py_files:
            grouped_files[py_file.parent].append(py_file)

        for directory, files in grouped_files.items():
            rel_dir = directory.relative_to(src_dir)

            # If it's the root source directory, name it after the root.
            # Otherwise, name it after the subdirectory.
            if rel_dir == Path("."):
                md_filename = f"{src_dir.name}.md"
                md_file = dest_dir / md_filename
            else:
                md_filename = f"{directory.name}.md"
                md_file = dest_dir / rel_dir.parent / md_filename

            md_file.parent.mkdir(parents=True, exist_ok=True)

            md_content = [f"# Directory: `{directory.name}`\n", f"**Path:** `{rel_dir}`\n", "---\n"]

            for file_path in files:
                try:
                    code = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    LOGGER.error("Skipping %s due to decode error.", file_path.name)
                    continue

                # Partition each file into its own section
                md_content.append(f"## `📄 {file_path.name}`\n")
                md_content.append(f"```python\n{code}\n```\n")
                md_content.append("---\n")

            md_file.write_text("\n".join(md_content), encoding="utf-8")

    else:
        # Standard 1-to-1 mirroring
        for py_file in py_files:
            rel_path = py_file.relative_to(src_dir)
            md_file = dest_dir / rel_path.with_suffix(".md")
            md_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                code = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                LOGGER.error("Skipping %s due to decode error.", py_file.name)
                continue

            md_content = f"# `{py_file.name}`\n\n**Project Path:** `{rel_path}`\n\n---\n\n```python\n{code}\n```\n"
            md_file.write_text(md_content, encoding="utf-8")

    mode = "rolled up" if rollup_dirs else "mirrored"
    LOGGER.info("Successfully %s %d filtered Python files into %s", mode, len(py_files), dest_dir)


# --- Verbatim from update_activity.py (config globals + build_activity_lines) ---

USERNAME = os.environ.get("GH_USERNAME", "enonymous1")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MAX_LINES = int(os.environ.get("MAX_LINES", "5"))

# Events to skip entirely (noisy or uninteresting)
SKIP_EVENTS = {"WatchEvent", "DeleteEvent", "MemberEvent"}

# Skip events on the profile repo itself to avoid infinite loops
SKIP_REPO = f"{USERNAME}/{USERNAME}"


def build_activity_lines(events):
    lines = []
    seen_repos_for_push = {}  # collapse multiple pushes to the same repo/branch

    for event in events:
        etype = event.get("type", "")
        repo = event.get("repo", {}).get("name", "")

        if etype in SKIP_EVENTS:
            continue
        if repo == SKIP_REPO:
            continue

        # Collapse consecutive pushes to the same repo+branch into one entry
        if etype == "PushEvent":
            payload = event.get("payload", {})
            branch = payload.get("ref", "").replace("refs/heads/", "")
            key = f"{repo}:{branch}"
            if key in seen_repos_for_push:
                # Accumulate commit count on the existing entry instead
                seen_repos_for_push[key]["payload"]["commits"] = seen_repos_for_push[key][
                    "payload"
                ].get("commits", []) + payload.get("commits", [])
                continue
            seen_repos_for_push[key] = event

        line = format_event(event)
        if line:
            lines.append(line)

        if len(lines) >= MAX_LINES:
            break

    return lines
