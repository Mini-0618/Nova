"""Test 7: Git integration (skipped if git not in PATH)"""
import sys
sys.path.insert(0, r'D:\codex-local')

import subprocess
import tempfile
import os

def test_git_integration():
    # Check if git is available
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("SKIP: git not found in PATH")
        return

    tmp = tempfile.mkdtemp()

    # Init git repo
    subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp, capture_output=True)

    # Create a file
    with open(os.path.join(tmp, "hello.txt"), "w") as f:
        f.write("hello")

    from tools.git_integration import GitRepo
    repo = GitRepo(tmp)
    try:
        assert repo.is_repo() == True, "not a repo"

        s = repo.status()
        assert s.branch == "master" or s.branch == "main", f"branch={s.branch}"

        # Stage and commit
        repo.add(["hello.txt"])
        h = repo.commit("initial commit")
        assert len(h) > 0, f"commit hash={h}"

        commits = repo.log(max_count=5)
        assert len(commits) >= 1, f"commits={commits}"
        assert commits[0].message == "initial commit"
    finally:
        repo.close()
        import shutil
        shutil.rmtree(tmp)
    print("PASS: git integration")

if __name__ == "__main__":
    test_git_integration()
