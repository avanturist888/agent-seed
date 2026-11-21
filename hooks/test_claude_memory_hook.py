"""Isolated unit tests for claude_memory_hook.py."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK_SCRIPT = Path(__file__).resolve().parent / "claude_memory_hook.py"


def encode_path(path: Path | str) -> str:
    norm = os.path.normpath(str(path)).rstrip("\\/")
    return re.sub(r"[^A-Za-z0-9-]", "-", norm)


def create_memory(
    claude_dir: Path,
    project_path: Path | str,
    content: str,
    *,
    encoded_override: str | None = None,
) -> Path:
    encoded = encoded_override or encode_path(project_path)
    mem_dir = claude_dir / "projects" / encoded / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_file = mem_dir / "MEMORY.md"
    mem_file.write_text(content, encoding="utf-8")
    return mem_file


class ClaudeMemoryHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.claude_dir = self.root / "claude"
        self.fake_home = self.root / "home"
        self.fake_home.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["USERPROFILE"] = str(self.fake_home)
        env["HOME"] = str(self.fake_home)
        return env

    def _run_hook(
        self,
        stdin_text: str,
        *,
        fmt: str = "antigravity",
        via_cmd: bool = False,
        pass_claude_dir: bool = True,
        extra_args: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        env = self._base_env()
        if extra_env:
            env.update(extra_env)
        if via_cmd:
            script_posix = HOOK_SCRIPT.as_posix()
            claude_posix = self.claude_dir.as_posix()
            cmdline = (
                f'cmd /c py -I "{script_posix}" --format {fmt} --claude-dir "{claude_posix}"'
            )
            proc = subprocess.run(
                cmdline,
                input=stdin_text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )
        else:
            cmd = [
                sys.executable,
                "-I",
                str(HOOK_SCRIPT),
                "--format",
                fmt,
            ]
            if pass_claude_dir:
                cmd.extend(["--claude-dir", str(self.claude_dir)])
            if extra_args:
                cmd.extend(extra_args)
            proc = subprocess.run(
                cmd,
                input=stdin_text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )
        out_text = proc.stdout.decode("utf-8")
        return proc.returncode, json.loads(out_text)

    def test_direct_project_match_antigravity_and_workspace_fallback(self) -> None:
        proj = self.fake_home / "work" / "alpha"
        proj.mkdir(parents=True)
        mem = create_memory(self.claude_dir, proj, "# Alpha Memory\nKey decision: KISS.\n")

        rc, data = self._run_hook(json.dumps({"cwd": str(proj)}))
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn(str(mem), msg)
        self.assertIn(str(mem.parent), msg)
        self.assertIn("Key decision: KISS.", msg)

        # Empty cwd -> fallback to first non-empty workspacePaths entry.
        rc2, data2 = self._run_hook(json.dumps({"cwd": "", "workspacePaths": ["", str(proj)]}))
        self.assertEqual(rc2, 0)
        self.assertEqual(data2, data)

    def test_drive_letter_case_insensitive_match(self) -> None:
        proj = self.fake_home / "work" / "CaseProj"
        proj.mkdir(parents=True)
        upper_encoded = encode_path(proj)
        if upper_encoded[0].islower():
            upper_encoded = upper_encoded[0].upper() + upper_encoded[1:]
        create_memory(self.claude_dir, proj, "Case match OK\n", encoded_override=upper_encoded)

        lower_cwd = str(proj)
        if len(lower_cwd) >= 2 and lower_cwd[1] == ":":
            lower_cwd = lower_cwd[0].lower() + lower_cwd[1:]

        rc, data = self._run_hook(json.dumps({"cwd": lower_cwd}))
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("Case match OK", msg)

    def test_git_subdirectory_resolves_to_repo_root_and_stops(self) -> None:
        outer = self.fake_home / "work" / "outer"
        repo = outer / "myrepo"
        sub = repo / "pkg" / "sub"
        sub.mkdir(parents=True)
        (repo / ".git").mkdir()
        create_memory(self.claude_dir, outer, "OUTER MEMORY SHOULD NOT BE USED\n")
        create_memory(self.claude_dir, repo, "REPO ROOT MEMORY\n")

        rc, data = self._run_hook(json.dumps({"cwd": str(sub)}))
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("REPO ROOT MEMORY", msg)
        self.assertNotIn("OUTER MEMORY", msg)

        # If repo root has NO memory, must NOT walk above repo root to outer!
        repo_no_mem = outer / "emptyrepo"
        sub2 = repo_no_mem / "nested"
        sub2.mkdir(parents=True)
        (repo_no_mem / ".git").mkdir()

        rc2, data2 = self._run_hook(json.dumps({"cwd": str(sub2)}))
        self.assertEqual(rc2, 0)
        self.assertEqual(data2, {})

    def test_git_worktree_commondir_resolves_to_main_repo(self) -> None:
        main_repo = self.fake_home / "work" / "mainrepo"
        wt_gitdir = main_repo / ".git" / "worktrees" / "wt1"
        wt_gitdir.mkdir(parents=True)
        (wt_gitdir / "commondir").write_text("../..\n", encoding="utf-8")

        worktree = self.fake_home / ".t3" / "worktrees" / "mainrepo" / "wt1"
        wt_sub = worktree / "src" / "app"
        wt_sub.mkdir(parents=True)
        (worktree / ".git").write_text(f"gitdir: {wt_gitdir.as_posix()}\n", encoding="utf-8")

        create_memory(self.claude_dir, main_repo, "MAIN REPO MEMORY VIA WORKTREE\n")

        # From worktree root
        rc, data = self._run_hook(json.dumps({"cwd": str(worktree)}))
        self.assertEqual(rc, 0)
        self.assertIn(
            "MAIN REPO MEMORY VIA WORKTREE",
            data["injectSteps"][0]["systemMessage"]["systemMessage"],
        )

        # From nested subdir inside worktree
        rc2, data2 = self._run_hook(json.dumps({"cwd": str(wt_sub)}))
        self.assertEqual(rc2, 0)
        self.assertIn(
            "MAIN REPO MEMORY VIA WORKTREE",
            data2["injectSteps"][0]["systemMessage"]["systemMessage"],
        )

        # Fallback without commondir file (pure .git/worktrees/<name> layout)
        (wt_gitdir / "commondir").unlink()
        rc3, data3 = self._run_hook(json.dumps({"cwd": str(worktree)}))
        self.assertEqual(rc3, 0)
        self.assertIn(
            "MAIN REPO MEMORY VIA WORKTREE",
            data3["injectSteps"][0]["systemMessage"]["systemMessage"],
        )

    def test_nested_new_project_inside_home_does_not_inherit_home_memory(self) -> None:
        create_memory(self.claude_dir, self.fake_home, "STEWARD HOME MEMORY\n")
        # Even if home itself has a .git directory, nested projects must NOT inherit it.
        (self.fake_home / ".git").mkdir()

        new_proj = self.fake_home / "work" / "new-project"
        new_proj.mkdir(parents=True)

        rc, data = self._run_hook(json.dumps({"cwd": str(new_proj)}))
        self.assertEqual(rc, 0)
        self.assertEqual(data, {})

    def test_home_directory_itself_finds_home_memory(self) -> None:
        create_memory(self.claude_dir, self.fake_home, "STEWARD HOME MEMORY\n")

        rc, data = self._run_hook(json.dumps({"cwd": str(self.fake_home)}))
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("STEWARD HOME MEMORY", msg)

    def test_truncation_over_200_lines(self) -> None:
        proj = self.fake_home / "work" / "many-lines"
        proj.mkdir(parents=True)
        content = "\n".join(f"Line {i}" for i in range(1, 251))
        mem = create_memory(self.claude_dir, proj, content)

        rc, data = self._run_hook(json.dumps({"cwd": str(proj)}))
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("Line 1", msg)
        self.assertIn("Line 200", msg)
        self.assertNotIn("Line 201", msg)
        self.assertIn("Truncated", msg)
        self.assertIn(str(mem), msg)

    def test_truncation_over_24kb_utf8(self) -> None:
        proj = self.fake_home / "work" / "big-bytes"
        proj.mkdir(parents=True)
        # Multi-byte UTF-8 characters (2 bytes each), fewer than 200 lines but > 30,000 bytes.
        line = "Кириллица " * 40  # ~760 bytes per line
        content = "\n".join(f"{i}: {line}" for i in range(50))
        self.assertGreater(len(content.encode("utf-8")), 30_000)
        mem = create_memory(self.claude_dir, proj, content)

        rc, data = self._run_hook(json.dumps({"cwd": str(proj)}))
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("Truncated", msg)
        self.assertIn(str(mem), msg)
        # Body must be capped at 24,000 bytes; total with header + notice stays well under 25,000 bytes.
        self.assertLess(len(msg.encode("utf-8")), 25_000)

    def test_invalid_or_empty_stdin_returns_empty_json_and_exit_0(self) -> None:
        for bad in ("", "   ", "{not json", "null", "[]", "{}"):
            rc, data = self._run_hook(bad)
            self.assertEqual(rc, 0, f"failed for stdin={bad!r}")
            self.assertEqual(data, {}, f"failed for stdin={bad!r}")

    def test_codex_format(self) -> None:
        proj = self.fake_home / "work" / "codex-proj"
        proj.mkdir(parents=True)
        mem = create_memory(self.claude_dir, proj, "Memory for Codex — résumé / Кириллица\n")

        rc, data = self._run_hook(json.dumps({"cwd": str(proj)}), fmt="codex")
        self.assertEqual(rc, 0)
        hso = data["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "SessionStart")
        self.assertIn("Memory for Codex — résumé / Кириллица", hso["additionalContext"])
        self.assertIn(str(mem), hso["additionalContext"])

    @unittest.skipUnless(os.name == "nt", "Windows cmd /c invocation test")
    def test_cmd_c_py_isolated_invocation_utf8(self) -> None:
        proj = self.fake_home / "work" / "cmd-proj"
        proj.mkdir(parents=True)
        create_memory(self.claude_dir, proj, "UTF-8 check via cmd /c: Кириллица\n")

        rc, data = self._run_hook(json.dumps({"cwd": str(proj)}), fmt="antigravity", via_cmd=True)
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("UTF-8 check via cmd /c: Кириллица", msg)

    def test_encoded_path_collision_without_metadata_does_not_inject(self) -> None:
        proj_hyphen = self.fake_home / "work" / "team-a"
        proj_slash = self.fake_home / "work" / "team" / "a"
        proj_hyphen.mkdir(parents=True)
        proj_slash.mkdir(parents=True)
        create_memory(self.claude_dir, proj_hyphen, "TEAM-A MEMORY\n")

        # Without session metadata to disambiguate, neither colliding project gets ambiguous memory.
        rc1, data1 = self._run_hook(json.dumps({"cwd": str(proj_slash)}))
        self.assertEqual(rc1, 0)
        self.assertEqual(data1, {})

        rc2, data2 = self._run_hook(json.dumps({"cwd": str(proj_hyphen)}))
        self.assertEqual(rc2, 0)
        self.assertEqual(data2, {})

        # Multi-separator collision (a/b/c/d vs a-b/c-d) must also be caught.
        multi_a = self.fake_home / "work" / "a" / "b" / "c" / "d"
        multi_b = self.fake_home / "work" / "a-b" / "c-d"
        multi_a.mkdir(parents=True)
        multi_b.mkdir(parents=True)
        create_memory(self.claude_dir, multi_a, "MULTI COLLISION MEMORY\n")
        self.assertEqual(self._run_hook(json.dumps({"cwd": str(multi_a)}))[1], {})
        self.assertEqual(self._run_hook(json.dumps({"cwd": str(multi_b)}))[1], {})

    def test_encoded_path_collision_resolved_by_session_metadata(self) -> None:
        proj_hyphen = self.fake_home / "work" / "team-a"
        proj_slash = self.fake_home / "work" / "team" / "a"
        proj_hyphen.mkdir(parents=True)
        proj_slash.mkdir(parents=True)
        mem = create_memory(self.claude_dir, proj_hyphen, "TEAM-A VERIFIED MEMORY\n")
        idx_path = mem.parent.parent / "sessions-index.json"
        idx_path.write_text(
            json.dumps({"version": 1, "originalPath": str(proj_hyphen), "entries": []}),
            encoding="utf-8",
        )

        # Matching project receives memory; colliding project gets empty output.
        rc_ok, data_ok = self._run_hook(json.dumps({"cwd": str(proj_hyphen)}))
        self.assertEqual(rc_ok, 0)
        self.assertIn(
            "TEAM-A VERIFIED MEMORY",
            data_ok["injectSteps"][0]["systemMessage"]["systemMessage"],
        )

        rc_other, data_other = self._run_hook(json.dumps({"cwd": str(proj_slash)}))
        self.assertEqual(rc_other, 0)
        self.assertEqual(data_other, {})

        # If metadata mixes BOTH colliding paths (even past entry 50), neither project loads it.
        idx_path.write_text(
            json.dumps({
                "version": 1,
                "originalPath": str(proj_hyphen),
                "entries": [{"projectPath": str(proj_hyphen)}] * 55
                + [{"projectPath": str(proj_slash)}],
            }),
            encoding="utf-8",
        )
        self.assertEqual(self._run_hook(json.dumps({"cwd": str(proj_hyphen)}))[1], {})
        self.assertEqual(self._run_hook(json.dumps({"cwd": str(proj_slash)}))[1], {})

    def test_claude_config_dir_env_var_is_honored(self) -> None:
        proj = self.fake_home / "work" / "custom-cfg"
        proj.mkdir(parents=True)
        stale_dir = self.fake_home / ".claude"
        custom_dir = self.root / "custom-claude"
        create_memory(stale_dir, proj, "STALE MEMORY\n")
        create_memory(custom_dir, proj, "CUSTOM CONFIG DIR MEMORY\n")

        rc, data = self._run_hook(
            json.dumps({"cwd": str(proj)}),
            pass_claude_dir=False,
            extra_env={"CLAUDE_CONFIG_DIR": str(custom_dir)},
        )
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("CUSTOM CONFIG DIR MEMORY", msg)
        self.assertNotIn("STALE MEMORY", msg)

    def test_separate_git_dir_with_core_worktree_resolves_main_repo(self) -> None:
        main_repo = self.fake_home / "work" / "sep-main"
        main_repo.mkdir(parents=True)
        # Even when the separate git dir is literally named ".git", core.worktree must win
        # and quoted values with trailing inline comments must parse cleanly.
        sep_parent = self.root / "meta-holder"
        sep_git = sep_parent / ".git"
        wt_gitdir = sep_git / "worktrees" / "wt1"
        wt_gitdir.mkdir(parents=True)
        (sep_git / "config").write_text(
            f'[core]\n\tbare = false\n\tworktree = "{main_repo.as_posix()}" # main checkout\n',
            encoding="utf-8",
        )
        (wt_gitdir / "commondir").write_text("../..\n", encoding="utf-8")

        worktree = self.fake_home / "worktrees" / "sep-wt1"
        worktree.mkdir(parents=True)
        (worktree / ".git").write_text(f"gitdir: {wt_gitdir.as_posix()}\n", encoding="utf-8")
        create_memory(self.claude_dir, sep_parent, "WRONG HOLDER MEMORY\n")
        create_memory(self.claude_dir, main_repo, "SEPARATE GIT DIR MAIN MEMORY\n")

        rc, data = self._run_hook(json.dumps({"cwd": str(worktree)}))
        self.assertEqual(rc, 0)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("SEPARATE GIT DIR MAIN MEMORY", msg)
        self.assertNotIn("WRONG HOLDER MEMORY", msg)

    def test_invalid_cli_args_return_empty_json_and_exit_0(self) -> None:
        rc, data = self._run_hook(
            json.dumps({"cwd": str(self.fake_home)}),
            extra_args=["--unknown-flag"],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(data, {})


if __name__ == "__main__":
    unittest.main()
