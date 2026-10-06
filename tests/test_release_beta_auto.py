# tests/test_release_beta_auto.py — `release.sh beta auto` picks the beta base from existing tags.
import os
import subprocess

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..")
SCRIPT = os.path.abspath(os.path.join(REPO, "scripts", "release.sh"))


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo_with_tags(tmp_path, tags):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "commit", "--allow-empty", "-m", "init")
    for t in tags:
        _git(tmp_path, "tag", t)


@pytest.mark.parametrize("tags,expected", [
    ([], "v0.1.0-beta.1"),                                           # no tags: existing fallback base
    (["v0.2.0"], "v0.2.1-beta.1"),                                   # latest released -> next patch
    (["v0.2.0", "v0.2.0-beta.18"], "v0.2.1-beta.1"),                 # betas of a released version don't count
    (["v0.2.0", "v0.3.0-beta.1", "v0.3.0-beta.2"], "v0.3.0-beta.3"), # open series continues
    (["v0.2.0", "v0.2.1-beta.1"], "v0.2.1-beta.2"),                  # open patch series continues
    (["v0.9.0", "v0.10.0-beta.1"], "v0.10.0-beta.2"),                # version sort, not lexical
])
def test_beta_auto_resolves_base(tmp_path, tags, expected):
    _repo_with_tags(tmp_path, tags)
    res = subprocess.run([SCRIPT, "beta", "auto"], cwd=tmp_path,
                         env={**os.environ, "DRY_RUN": "1"}, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == expected


def test_release_skill_documents_beta_auto():
    skill = open(os.path.join(REPO, ".opencode", "skills", "release-workflow", "SKILL.md")).read()
    assert "scripts/release.sh beta auto" in skill
    assert "requirements.txt" in skill
