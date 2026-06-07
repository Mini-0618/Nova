"""
Codex-Local Environment Manager
Create and manage Python venv, conda envs, npm workspaces.
Activate env, install packages, run in isolation.
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def run_cmd(cmd: List[str], cwd: str = None, timeout: int = 120) -> Dict[str, Any]:
    """Run a command and return structured result."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=True,
            cwd=cwd,
            env={**os.environ},
        )
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timeout after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}


# ─── Python venv ─────────────────────────────────────────────

def create_venv(path: str, python: str = None) -> Dict[str, Any]:
    """Create a Python virtual environment."""
    cmd = [python or sys.executable, "-m", "venv", path]
    result = run_cmd(cmd)
    if result["success"]:
        # Find the python in the venv
        venv_python = Path(path) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        result["python_path"] = str(venv_python)
    return result


def install_packages(venv_path: str, packages: List[str], pip_args: List[str] = None) -> Dict[str, Any]:
    """Install packages into a venv."""
    venv_python = Path(venv_path) / ("Scripts/python.exe" if os.name == "nt" else "bin/pip")
    if not venv_python.exists():
        # Try pip directly
        venv_python = Path(venv_path) / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")

    cmd = [str(venv_python), "-m", "pip", "install"] + packages
    if pip_args:
        cmd.extend(pip_args)
    return run_cmd(cmd)


def run_in_venv(venv_path: str, script: str, args: List[str] = None) -> Dict[str, Any]:
    """Run a script in a venv."""
    venv_python = Path(venv_path) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    cmd = [str(venv_python), script] + (args or [])
    return run_cmd(cmd)


# ─── Conda ─────────────────────────────────────────────────

def create_conda_env(name: str, python_version: str = "3.11", packages: List[str] = None) -> Dict[str, Any]:
    """Create a conda environment."""
    cmd = ["conda", "create", "-n", name, f"python={python_version}", "-y"]
    if packages:
        cmd.extend(packages)
    result = run_cmd(cmd, timeout=300)
    if result["success"] and packages:
        install_result = run_cmd(["conda", "install", "-n", name] + packages + ["-y"], timeout=300)
        result["install"] = install_result
    return result


def activate_conda_env(name: str) -> Dict[str, Any]:
    """Get conda env activation command."""
    return {
        "success": True,
        "activation_cmd": f"conda activate {name}",
        "env_path": f"conda envs location: {name}",
    }


# ─── npm/Node.js ───────────────────────────────────────────

def npm_install(package_json_dir: str, packages: List[str] = None, global_install: bool = False) -> Dict[str, Any]:
    """Install npm packages."""
    if global_install:
        cmd = ["npm", "install", "-g"] + (packages or [])
    else:
        cmd = ["npm", "install"] + (packages or [])
        if packages is None:
            cmd = ["npm", "install"]  # install from package.json
    result = run_cmd(cmd, cwd=package_json_dir)

    # Parse package-lock or installed list
    if result["success"] and not global_install:
        lock = Path(package_json_dir) / "package-lock.json"
        if lock.exists():
            try:
                lock_data = json.loads(lock.read_text())
                deps = lock_data.get("packages", {})
                installed = [p.replace("node_modules/", "") for p in deps.keys() if "node_modules/" in p]
                result["installed_packages"] = installed[:20]
            except Exception:
                pass

    return result


def npm_run(package_json_dir: str, script: str, args: List[str] = None) -> Dict[str, Any]:
    """Run an npm script (from package.json scripts)."""
    cmd = ["npm", "run", script] + (args or [])
    return run_cmd(cmd, cwd=package_json_dir, timeout=300)


def npm_new_project(dir: str, name: str = None, template: str = "javascript") -> Dict[str, Any]:
    """Scaffold a new npm project."""
    cmd = ["npm", "init", "-y"]
    if name:
        cmd[2] = f"-y"
    result = run_cmd(cmd, cwd=dir)
    if result["success"] and template:
        if template != "javascript":
            run_cmd(["npm", "install", f"-D", f"@{template}/bootstrap"], cwd=dir)
    return result


# ─── Environment Info ──────────────────────────────────────

def get_env_info() -> Dict[str, Any]:
    """Get current environment information."""
    info = {
        "python": sys.executable,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": os.name,
        "cwd": os.getcwd(),
        "path": os.environ.get("PATH", "").split(os.pathsep)[:5],
    }

    # Check conda
    conda_result = run_cmd(["conda", "--version"])
    if conda_result["success"]:
        info["conda"] = conda_result["stdout"].strip()

    # Check npm
    npm_result = run_cmd(["npm", "--version"])
    if npm_result["success"]:
        info["npm_version"] = npm_result["stdout"].strip()

    # Check node
    node_result = run_cmd(["node", "--version"])
    if node_result["success"]:
        info["node_version"] = node_result["stdout"].strip()

    return info


# ─── Unified Tool Interface ─────────────────────────────────

def env_tool(operation: str, path: str = None, **kwargs) -> Dict[str, Any]:
    """
    Environment management tool for executor.

    Operations:
    - venv_create: Create Python venv
    - venv_install: Install packages into venv
    - venv_run: Run script in venv
    - conda_create: Create conda env
    - npm_install: Install npm packages
    - npm_run: Run npm script
    - npm_init: Init new npm project
    - env_info: Get current environment
    """
    if operation == "venv_create":
        return create_venv(path or kwargs.get("venv_path", "D:/codex-local/venv"))

    elif operation == "venv_install":
        return install_packages(
            venv_path=kwargs["venv_path"],
            packages=kwargs.get("packages", []),
            pip_args=kwargs.get("pip_args"),
        )

    elif operation == "venv_run":
        return run_in_venv(
            venv_path=kwargs["venv_path"],
            script=kwargs["script"],
            args=kwargs.get("args"),
        )

    elif operation == "conda_create":
        return create_conda_env(
            name=kwargs["name"],
            python_version=kwargs.get("python_version", "3.11"),
            packages=kwargs.get("packages"),
        )

    elif operation == "npm_install":
        return npm_install(
            package_json_dir=path or kwargs.get("dir", "."),
            packages=kwargs.get("packages"),
            global_install=kwargs.get("global", False),
        )

    elif operation == "npm_run":
        return npm_run(
            package_json_dir=path or kwargs.get("dir", "."),
            script=kwargs["script"],
            args=kwargs.get("args"),
        )

    elif operation == "npm_init":
        return npm_new_project(
            dir=path or kwargs.get("dir", "."),
            name=kwargs.get("name"),
            template=kwargs.get("template", "javascript"),
        )

    elif operation == "env_info":
        return {"success": True, **get_env_info()}

    else:
        return {"success": False, "error": f"Unknown operation: {operation}"}


if __name__ == "__main__":
    print("Environment Info:")
    print(json.dumps(get_env_info(), indent=2))