"""Repository hygiene: heavy MD artefacts must never be committable."""

from __future__ import annotations

import fnmatch
import os
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

HEAVY_SUFFIXES = (".xtc", ".trr", ".tpr", ".cpt", ".gro", ".edr", ".h5", ".dcd")


def _gitignore_patterns():
    patterns = []
    with open(os.path.join(REPO_ROOT, ".gitignore"), encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


def test_heavy_extensions_are_ignored():
    patterns = _gitignore_patterns()
    assert "*.xtc" in patterns
    assert "*.trr" in patterns
    assert "*.tpr" in patterns
    assert "*.cpt" in patterns
    assert "*.gro" in patterns


def test_local_secrets_and_state_are_ignored():
    patterns = _gitignore_patterns()
    joined = "\n".join(patterns)
    assert "skills/cgmd-hub/state/" in joined
    assert "skills/cgmd-hub/logs/" in joined
    assert "cgmd_hub.local.json" in joined


def test_no_heavy_file_is_tracked():
    """`git ls-files` must not contain a single trajectory artefact."""
    try:
        output = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git in sandbox
        return
    if output.returncode != 0:
        return
    offenders = [
        name for name in output.stdout.split()
        if name.lower().endswith(HEAVY_SUFFIXES)
    ]
    assert offenders == [], "tracked heavy files: {}".format(offenders)


def test_summary_files_stay_small():
    """Anything under results/ must stay below 1 MB (summary_metrics contract)."""
    results = os.path.join(REPO_ROOT, "results")
    if not os.path.isdir(results):
        return
    for root, _dirs, files in os.walk(results):
        for name in files:
            path = os.path.join(root, name)
            assert os.path.getsize(path) < 1_000_000, path


def test_desktop_scripts_are_pure_ascii():
    """Windows PowerShell 5.1 in a non-UTF8 code page must parse these files."""
    hub = os.path.join(REPO_ROOT, "skills", "cgmd-hub")
    if not os.path.isdir(hub):
        return
    for root, _dirs, files in os.walk(hub):
        for name in files:
            if not name.lower().endswith((".ps1", ".vbs", ".cs", ".cmd", ".bat")):
                continue
            path = os.path.join(root, name)
            with open(path, "rb") as handle:
                data = handle.read()
            offenders = [(index, byte) for index, byte in enumerate(data) if byte > 127]
            assert offenders == [], "non-ASCII byte in {}: {}".format(path, offenders[:3])


def test_docs_are_chinese_and_cover_the_deliverables():
    path = os.path.join(REPO_ROOT, "README.md")
    text = open(path, encoding="utf-8").read()
    assert "bootstrap_desktop.ps1" in text
    assert "arena-beacon-95bc796a66" in text
    assert "POPE:POPG" in text or "POPE" in text
    chinese = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    assert chinese > 500, "README should be written in Chinese"


def test_powershell_scripts_are_balanced():
    """Very small static check: balanced (), [] and {} plus closed quotes.

    It is not a parser, but it reliably catches the copy/paste class of syntax
    errors that would otherwise only show up on the Windows machine.
    """
    hub = os.path.join(REPO_ROOT, "skills", "cgmd-hub")
    if not os.path.isdir(hub):
        return
    for root, _dirs, files in os.walk(hub):
        for name in files:
            if not name.lower().endswith(".ps1"):
                continue
            path = os.path.join(root, name)
            text = open(path, encoding="ascii").read()
            stack = []
            quote = None
            index = 0
            pairs = {")": "(", "]": "[", "}": "{"}
            while index < len(text):
                char = text[index]
                if quote:
                    if char == "`":           # PowerShell escape inside strings
                        index += 2
                        continue
                    if char == quote:
                        # doubled quote is an escaped quote
                        if index + 1 < len(text) and text[index + 1] == quote:
                            index += 2
                            continue
                        quote = None
                    index += 1
                    continue
                if char == "<" and text[index:index + 2] == "<#":
                    end = text.find("#>", index)
                    assert end != -1, "unterminated block comment in {}".format(path)
                    index = end + 2
                    continue
                if char == "#":
                    newline = text.find("\n", index)
                    index = len(text) if newline == -1 else newline + 1
                    continue
                if char == "`":
                    index += 2
                    continue
                if char in ("'", '"'):
                    quote = char
                    index += 1
                    continue
                if char in "([{":
                    stack.append(char)
                elif char in ")]}":
                    assert stack, "unbalanced '{}' at offset {} in {}".format(char, index, path)
                    assert stack.pop() == pairs[char], "mismatched '{}' at offset {} in {}".format(char, index, path)
                index += 1
            assert quote is None, "unterminated {} string in {}".format(quote, path)
            assert not stack, "unclosed {} in {}".format(stack, path)
