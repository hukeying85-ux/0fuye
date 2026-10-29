"""Structural sanity for the PowerShell runners (no Windows required).

There is no PowerShell in CI, and a single unbalanced brace in the watcher means
silent failure on the workstation until a human notices.  This is not a parser:
it strips comments, single/double quoted strings and here-strings, then checks
that every bracket closes and that no stray `}` appears.
"""

import glob
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER_GLOB = os.path.join(ROOT, "skills", "cgmd-hub", "**", "*.ps1")
PAIRS = {"(": ")", "[": "]", "{": "}"}


def strip_noise(source):
    """Remove comments and string literals, keeping line structure."""
    out = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        nxt = source[index + 1] if index + 1 < length else ""
        if char == "<" and nxt == "#":                      # block comment
            end = source.find("#>", index + 2)
            end = length if end < 0 else end + 2
            out.append("\n" * source.count("\n", index, end))
            index = end
            continue
        if char == "#":                                     # line comment
            end = source.find("\n", index)
            index = length if end < 0 else end
            continue
        if char in "@'@\"" and char == "@" and nxt in ("'", "\""):
            terminator = "\n" + nxt + "@"
            end = source.find(terminator, index + 2)
            end = length if end < 0 else end + len(terminator)
            out.append("\n" * source.count("\n", index, end))
            index = end
            continue
        if char == "'":                                     # single quoted
            index += 1
            while index < length:
                if source[index] == "'":
                    if index + 1 < length and source[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            out.append('""')
            continue
        if char == '"':                                     # double quoted
            index += 1
            while index < length:
                if source[index] == "`":
                    index += 2
                    continue
                if source[index] == '"':
                    index += 1
                    break
                index += 1
            out.append('""')
            continue
        out.append(char)
        index += 1
    return "".join(out)


def check_balance(path):
    source = open(path, "rb").read().decode("ascii")
    stripped = strip_noise(source)
    stack = []
    line = 1
    for char in stripped:
        if char == "\n":
            line += 1
        elif char in PAIRS:
            stack.append((char, line))
        elif char in PAIRS.values():
            if not stack:
                pytest.fail("%s:%d stray %r" % (os.path.basename(path), line, char))
            opener, opened_at = stack.pop()
            if PAIRS[opener] != char:
                pytest.fail("%s:%d %r closes %r from line %d"
                            % (os.path.basename(path), line, char, opener, opened_at))
    if stack:
        opener, opened_at = stack[-1]
        pytest.fail("%s: %r opened on line %d is never closed"
                    % (os.path.basename(path), opener, opened_at))


@pytest.mark.parametrize("path", sorted(glob.glob(RUNNER_GLOB, recursive=True)))
def test_brackets_balance(path):
    check_balance(path)


@pytest.mark.parametrize("path", sorted(glob.glob(RUNNER_GLOB, recursive=True)))
def test_every_runner_is_pure_ascii(path):
    raw = open(path, "rb").read()
    bad = [index for index, byte in enumerate(raw) if byte > 127]
    assert not bad, "%s has %d non-ASCII bytes" % (os.path.basename(path), len(bad))


@pytest.mark.parametrize("path", sorted(glob.glob(RUNNER_GLOB, recursive=True)))
def test_scripts_declare_ps51_and_param_block(path):
    text = open(path, "rb").read().decode("ascii")
    if "param(" not in text and "[CmdletBinding()]" not in text:
        return
    assert "[CmdletBinding()]" in text, os.path.basename(path)
    assert "param(" in text, os.path.basename(path)
