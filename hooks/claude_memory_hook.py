#!/usr/bin/env python3
"""SessionStart hook that injects Claude Code project memory (MEMORY.md).

Supports Antigravity (--format antigravity) and Codex (--format codex).
Uses only Python 3.9+ stdlib and is safe to run under `py -I` / `python3 -I`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Iterable

MAX_LINES = 200
MAX_BYTES = 24_000
_ENCODE_RE = re.compile(r"[^A-Za-z0-9-]")


def _normalize_path(path: str) -> str:
    p = path.strip()
    if not p:
        return ""
    if p.startswith("\\\\?\\UNC\\"):
        p = "\\\\" + p[8:]
    elif p.startswith("\\\\?\\") and len(p) >= 6 and p[5] == ":":
        p = p[4:]
    p = os.path.normpath(p)
    if len(p) > 1:
        trimmed = p.rstrip("\\/")
        if trimmed:
            p = trimmed
    return p


def encode_project_path(path: str) -> str:
    cleaned = _normalize_path(path)
    return _ENCODE_RE.sub("-", cleaned)


def _home_keys() -> set[str]:
    keys: set[str] = set()
    home = os.path.expanduser("~")
    if home and home != "~":
        h_norm = _normalize_path(home)
        if h_norm:
            keys.add(os.path.normcase(h_norm))
        try:
            h_real = _normalize_path(os.path.realpath(home))
            if h_real:
                keys.add(os.path.normcase(h_real))
        except OSError:
            pass
    return keys


def _parse_git_config_value(raw: str) -> str:
    """Parse a single-line Git config value, handling quotes and inline comments."""
    s = raw.strip()
    if not s:
        return ""
    if s[0] == '"':
        out: list[str] = []
        i = 1
        while i < len(s):
            ch = s[i]
            if ch == "\\" and i + 1 < len(s):
                nxt = s[i + 1]
                out.append(nxt if nxt in ('"', "\\") else "\\" + nxt)
                i += 2
                continue
            if ch == '"':
                break
            out.append(ch)
            i += 1
        return "".join(out).strip()
    for idx, ch in enumerate(s):
        if ch in ("#", ";"):
            s = s[:idx]
            break
    return s.strip()


def _read_core_worktree(common_git: str) -> str | None:
    config_file = os.path.join(common_git, "config")
    if not os.path.isfile(config_file):
        return None
    try:
        with open(config_file, "r", encoding="utf-8-sig", errors="replace") as f:
            in_core = False
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if line.startswith("[") and "]" in line:
                    section = line[1:line.index("]")].strip().casefold()
                    in_core = section == "core"
                    continue
                if in_core and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip().casefold() == "worktree":
                        val = _parse_git_config_value(v)
                        if not val:
                            return None
                        if os.path.isabs(val):
                            return _normalize_path(val)
                        return _normalize_path(os.path.join(common_git, val))
    except OSError:
        return None
    return None


def _resolve_worktree_main_repo(worktree_root: str, git_file: str) -> str | None:
    try:
        with open(git_file, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return None

    raw_gitdir = ""
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("gitdir:"):
            raw_gitdir = stripped.split(":", 1)[1].strip()
            break
    if not raw_gitdir:
        return None

    if os.path.isabs(raw_gitdir):
        gitdir = _normalize_path(raw_gitdir)
    else:
        gitdir = _normalize_path(os.path.join(worktree_root, raw_gitdir))

    commondir_file = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondir_file):
        try:
            with open(commondir_file, "r", encoding="utf-8-sig", errors="replace") as f:
                raw_common = f.read().strip()
        except OSError:
            raw_common = ""
        if raw_common:
            if os.path.isabs(raw_common):
                common_git = _normalize_path(raw_common)
            else:
                common_git = _normalize_path(os.path.join(gitdir, raw_common))
            core_wt = _read_core_worktree(common_git)
            if core_wt:
                return core_wt
            if os.path.basename(common_git).casefold() == ".git":
                return _normalize_path(os.path.dirname(common_git))

    # Fallback: standard <main-repo>/.git/worktrees/<name> layout.
    worktrees_dir = os.path.dirname(gitdir)
    dot_git_dir = os.path.dirname(worktrees_dir)
    if (
        os.path.basename(worktrees_dir).casefold() == "worktrees"
        and os.path.basename(dot_git_dir).casefold() == ".git"
    ):
        core_wt = _read_core_worktree(dot_git_dir)
        if core_wt:
            return core_wt
        return _normalize_path(os.path.dirname(dot_git_dir))

    return None


def _find_git_candidates(start_dir: str, home_keys: set[str], allow_home: bool) -> list[str]:
    found: list[str] = []
    cur = start_dir
    while cur:
        if not allow_home and os.path.normcase(cur) in home_keys:
            break
        git_entry = os.path.join(cur, ".git")
        try:
            is_file = os.path.isfile(git_entry)
            is_dir = not is_file and os.path.isdir(git_entry)
        except OSError:
            is_file = False
            is_dir = False

        if is_file:
            main_repo = _resolve_worktree_main_repo(cur, git_entry)
            if cur != start_dir:
                found.append(cur)
            if main_repo:
                found.append(main_repo)
                try:
                    found.append(_normalize_path(os.path.realpath(main_repo)))
                except OSError:
                    pass
            break
        if is_dir:
            found.append(cur)
            try:
                found.append(_normalize_path(os.path.realpath(cur)))
            except OSError:
                pass
            break

        parent = _normalize_path(os.path.dirname(cur))
        if not parent or os.path.normcase(parent) == os.path.normcase(cur):
            break
        cur = parent
    return found


def candidate_project_dirs(cwd: str) -> list[str]:
    cwd_norm = _normalize_path(cwd)
    if not cwd_norm:
        return []

    try:
        cwd_real = _normalize_path(os.path.realpath(cwd_norm))
    except OSError:
        cwd_real = cwd_norm

    home_keys = _home_keys()
    is_self_home = (
        os.path.normcase(cwd_norm) in home_keys
        or os.path.normcase(cwd_real) in home_keys
    )

    candidates: list[str] = []
    seen: set[str] = set()

    def add(path: str, *, allow_home: bool) -> None:
        norm = _normalize_path(path)
        if not norm:
            return
        key = os.path.normcase(norm)
        if not allow_home and key in home_keys:
            return
        if key not in seen:
            seen.add(key)
            candidates.append(norm)

    # 1. Exact cwd and its realpath (junction / symlink target).
    add(cwd_norm, allow_home=True)
    if cwd_real:
        add(cwd_real, allow_home=True)

    # 2 & 3. Git worktree main repo or enclosing git repository root.
    git_roots = _find_git_candidates(cwd_norm, home_keys, allow_home=is_self_home)
    if not git_roots and cwd_real and os.path.normcase(cwd_real) != os.path.normcase(cwd_norm):
        git_roots = _find_git_candidates(cwd_real, home_keys, allow_home=is_self_home)

    for root in git_roots:
        add(root, allow_home=is_self_home)

    return candidates


def _path_keys(path: str) -> set[str]:
    norm = _normalize_path(path)
    if not norm:
        return set()
    keys = {os.path.normcase(norm)}
    try:
        real = _normalize_path(os.path.realpath(norm))
        if real:
            keys.add(os.path.normcase(real))
    except OSError:
        pass
    return keys


def _recorded_project_path_groups(proj_dir: str) -> list[set[str]]:
    """Extract recorded project/session paths from Claude Code metadata in proj_dir.

    Each recorded path becomes its own set of normalized keys (norm + realpath) so
    we can verify that ALL recorded paths belong exclusively to one candidate project.
    """
    groups: list[set[str]] = []
    seen_raw: set[str] = set()

    def _add(raw: object) -> None:
        if not isinstance(raw, str) or not raw.strip():
            return
        norm = _normalize_path(raw)
        if not norm:
            return
        k = os.path.normcase(norm)
        if k in seen_raw:
            return
        seen_raw.add(k)
        keys = _path_keys(norm)
        if keys:
            groups.append(keys)

    idx_file = os.path.join(proj_dir, "sessions-index.json")
    if os.path.isfile(idx_file):
        try:
            with open(idx_file, "r", encoding="utf-8-sig", errors="replace") as f:
                idx = json.load(f)
            if isinstance(idx, dict):
                _add(idx.get("originalPath"))
                entries = idx.get("entries")
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            _add(entry.get("projectPath"))
        except (OSError, ValueError):
            pass

    if groups:
        return groups

    # Fall back to session transcripts (*.jsonl) which record `cwd`.
    jsonl_files: list[str] = []
    try:
        with os.scandir(proj_dir) as it:
            for entry in it:
                if entry.name.endswith(".jsonl") and entry.is_file():
                    jsonl_files.append(entry.path)
    except OSError:
        return groups

    for jpath in jsonl_files[:10]:
        try:
            with open(jpath, "r", encoding="utf-8-sig", errors="replace") as f:
                for line_no, line in enumerate(f):
                    if line_no >= 20:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(obj, dict):
                        cwd_val = obj.get("cwd")
                        if isinstance(cwd_val, str) and cwd_val.strip():
                            _add(cwd_val)
                            break
        except OSError:
            continue
    return groups


def _candidate_matches_recorded(candidate: str, recorded_groups: list[set[str]]) -> bool:
    cand_keys = _path_keys(candidate)
    if not cand_keys or not recorded_groups:
        return False
    prefixes = tuple(ck.rstrip("\\/") + os.sep for ck in cand_keys)
    for grp in recorded_groups:
        matched = any(
            rk in cand_keys or rk.startswith(prefixes)
            for rk in grp
        )
        if not matched:
            return False
    return True


def _has_ambiguous_disk_collision(candidate: str, encoded: str) -> bool:
    """Return True if any other distinct existing directory encodes to the same key.

    Because every path separator encodes to '-', every descendant of directory E has
    encode(D) starting with encode(E) + '-'. Prefix-pruned traversal from the filesystem
    root therefore finds all multi-separator, hyphen, and non-alnum collisions cleanly.
    """
    cand_norm = _normalize_path(candidate)
    if not cand_norm:
        return False
    cand_keys = _path_keys(cand_norm)
    target = encoded.casefold()

    drive, tail = os.path.splitdrive(cand_norm)
    if tail.startswith(("\\", "/")):
        root_dir = drive + os.sep
    elif drive:
        root_dir = drive + os.sep
    else:
        return False

    if not os.path.isdir(root_dir):
        return False

    stack: list[str] = [root_dir]
    visited: set[str] = set()
    budget = 256

    while stack and budget > 0:
        cur = stack.pop()
        budget -= 1
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if not entry.is_dir():
                            continue
                    except OSError:
                        continue
                    entry_norm = _normalize_path(entry.path)
                    if not entry_norm:
                        continue
                    entry_enc = encode_project_path(entry_norm).casefold()
                    if entry_enc == target:
                        if _path_keys(entry_norm).isdisjoint(cand_keys):
                            return True
                        continue
                    if target.startswith(entry_enc + "-"):
                        try:
                            visit_key = os.path.normcase(_normalize_path(os.path.realpath(entry_norm)))
                        except OSError:
                            visit_key = os.path.normcase(entry_norm)
                        if visit_key not in visited:
                            visited.add(visit_key)
                            stack.append(entry_norm)
        except OSError:
            continue

    # Fail closed if the traversal budget was exhausted with unexplored branches remaining.
    return bool(stack)


def find_memory_file(candidates: Iterable[str], claude_dir: str) -> str | None:
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects_dir):
        return None

    exact_map: dict[str, str] = {}
    fold_map: dict[str, list[str]] = {}
    try:
        with os.scandir(projects_dir) as it:
            for entry in it:
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                exact_map[entry.name] = entry.path
                fold_map.setdefault(entry.name.casefold(), []).append(entry.path)
    except OSError:
        return None

    for candidate in candidates:
        encoded = encode_project_path(candidate)
        if not encoded:
            continue
        matched_dirs: list[str] = []
        exact = exact_map.get(encoded)
        if exact:
            matched_dirs.append(exact)
        for p in fold_map.get(encoded.casefold(), ()):
            if p not in matched_dirs:
                matched_dirs.append(p)
        for proj_dir in matched_dirs:
            memory_path = os.path.join(proj_dir, "memory", "MEMORY.md")
            if not os.path.isfile(memory_path):
                continue
            recorded = _recorded_project_path_groups(proj_dir)
            if recorded:
                if not _candidate_matches_recorded(candidate, recorded):
                    continue
            elif _has_ambiguous_disk_collision(candidate, encoded):
                continue
            return memory_path

    return None


def read_and_format_memory(memory_path: str) -> str | None:
    try:
        with open(memory_path, "r", encoding="utf-8-sig", errors="replace") as f:
            raw_text = f.read()
    except OSError:
        return None

    if not raw_text.strip():
        return None

    lines = raw_text.splitlines()
    truncated = False
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        truncated = True

    body = "\n".join(lines)
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_BYTES:
        truncated = True
        cut = encoded[:MAX_BYTES].decode("utf-8", errors="ignore")
        last_nl = cut.rfind("\n")
        if last_nl >= len(cut) // 2:
            cut = cut[:last_nl]
        body = cut

    memory_dir = os.path.dirname(memory_path)
    parts = [
        f"Claude Code project memory loaded from: {memory_path}",
        f"Memory directory (topic files & updates): {memory_dir}",
        "",
        body,
    ]
    if truncated:
        parts.append("")
        parts.append(
            f"[Truncated at {MAX_LINES} lines / {MAX_BYTES} bytes. Full file: {memory_path}]"
        )
    return "\n".join(parts)


def extract_cwd(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()
    workspace_paths = payload.get("workspacePaths")
    if isinstance(workspace_paths, list):
        for item in workspace_paths:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def build_output(message: str, fmt: str) -> dict:
    if fmt == "codex":
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": message,
            }
        }
    return {
        "injectSteps": [
            {
                "systemMessage": {
                    "systemMessage": message,
                }
            }
        ]
    }


def _write_json(obj: dict) -> None:
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


class _QuietArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _QuietArgumentParser(add_help=True)
        parser.add_argument(
            "--format",
            choices=("antigravity", "codex"),
            default="antigravity",
        )
        parser.add_argument("--claude-dir", default=None)
        args = parser.parse_args(argv)

        raw_stdin = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace").strip()
        if not raw_stdin:
            _write_json({})
            return 0

        payload = json.loads(raw_stdin)
        cwd = extract_cwd(payload)
        if not cwd:
            _write_json({})
            return 0

        raw_claude_dir = (
            args.claude_dir
            or os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
            or "~/.claude"
        )
        claude_dir = _normalize_path(os.path.expanduser(raw_claude_dir))
        candidates = candidate_project_dirs(cwd)
        memory_path = find_memory_file(candidates, claude_dir)
        if not memory_path:
            _write_json({})
            return 0

        message = read_and_format_memory(memory_path)
        if not message:
            _write_json({})
            return 0

        _write_json(build_output(message, args.format))
        return 0
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        try:
            _write_json({})
        except Exception:
            pass
        return 0
    except Exception:
        try:
            _write_json({})
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
