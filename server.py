from __future__ import annotations

import json
import os
import shlex
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    # FastMCP is the simplest way to declare tools and run an MCP server
    from mcp.server.fastmcp import FastMCP
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "The 'mcp' package is required. Install with: pip install -r requirements.txt"
    ) from exc


# Resolve important project paths (assumes sibling directories: 'jetlag' and 'jetlag-mcp')
THIS_FILE = Path(__file__).resolve()
MCP_DIR = THIS_FILE.parent
REPO_DIR = MCP_DIR.parent
JETLAG_DIR = (REPO_DIR / "jetlag").resolve()

ANSIBLE_DIR = (JETLAG_DIR / "ansible").resolve()
DOCS_DIR = (JETLAG_DIR / "docs").resolve()
VARS_DIR = (JETLAG_DIR / "ansible" / "inventory").resolve()
ROLES_DIR = (ANSIBLE_DIR / "roles").resolve()


def _ensure_within(base: Path, candidate: Path) -> Path:
    candidate_resolved = candidate.resolve()
    base_resolved = base.resolve()
    if base_resolved not in candidate_resolved.parents and candidate_resolved != base_resolved:
        raise ValueError(f"Path escapes allowed base: {candidate_resolved} not within {base_resolved}")
    return candidate_resolved


def _run_command(command: List[str], cwd: Optional[Path] = None, timeout_seconds: int = 3600) -> Dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "command": " ".join(shlex.quote(p) for p in command),
        "cwd": str(cwd) if cwd else None,
    }


app = FastMCP("jetlag-mcp")


@dataclass
class PlaybookInfo:
    name: str
    path: str


@app.tool()
def list_playbooks() -> List[Dict[str, str]]:
    """List top-level Ansible playbooks under jetlag/ansible (excludes role internals)."""
    if not ANSIBLE_DIR.exists():
        return []
    results: List[PlaybookInfo] = []
    for entry in sorted(ANSIBLE_DIR.iterdir()):
        if entry.is_file() and entry.suffix in {".yml", ".yaml"}:
            results.append(PlaybookInfo(name=entry.name, path=str(entry)))
    return [asdict(r) for r in results]


@app.tool()
def list_roles() -> List[str]:
    """List Ansible role names available under jetlag/ansible/roles."""
    if not ROLES_DIR.exists():
        return []
    role_names: List[str] = []
    for entry in sorted(ROLES_DIR.iterdir()):
        if entry.is_dir():
            role_names.append(entry.name)
    return role_names


@app.tool()
def list_docs() -> List[str]:
    """List Markdown docs under jetlag/docs (excluding images)."""
    if not DOCS_DIR.exists():
        return []
    md_files: List[str] = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        # Skip image directory
        if "/img/" in str(path):
            continue
        md_files.append(str(path))
    return md_files


@app.tool()
def read_text_file(relative_path: str) -> str:
    """Read a text file from within the 'jetlag' project by relative path.

    Only files within the jetlag directory are allowed. Use forward slashes.
    """
    requested = (JETLAG_DIR / relative_path).resolve()
    safe_path = _ensure_within(JETLAG_DIR, requested)
    if not safe_path.exists() or not safe_path.is_file():
        raise FileNotFoundError(f"File not found: {safe_path}")
    try:
        return safe_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError("File is not UTF-8 text; refusing to read as text")


@app.tool()
def run_playbook(
    playbook_name: str,
    inventory_relpath: Optional[str] = None,
    limit: Optional[str] = None,
    tags: Optional[str] = None,
    extra_vars_json: Optional[str] = None,
    check: bool = False,
    timeout_seconds: int = 7200,
) -> Dict[str, Any]:
    """Run an Ansible playbook by name (top-level file under jetlag/ansible).

    - playbook_name: e.g., "sno-deploy.yml" (must be in jetlag/ansible)
    - inventory_relpath: optional relative path within jetlag (e.g., "ansible/inventory/inventory-sno.sample")
    - limit: optional Ansible --limit
    - tags: optional Ansible --tags
    - extra_vars_json: JSON string of variables to pass with -e
    - check: if True, runs with --check
    - timeout_seconds: process timeout
    """
    playbook_path = _ensure_within(ANSIBLE_DIR, ANSIBLE_DIR / playbook_name)
    if not playbook_path.exists():
        raise FileNotFoundError(f"Playbook not found: {playbook_path}")

    # Prefer the project's Ansible venv if present
    ansible_bin_path = (JETLAG_DIR / ".ansible" / "bin" / "ansible-playbook")
    ansible_executable = str(ansible_bin_path) if ansible_bin_path.exists() else "ansible-playbook"

    command: List[str] = [ansible_executable, str(playbook_path)]

    if inventory_relpath:
        inv_path = _ensure_within(JETLAG_DIR, JETLAG_DIR / inventory_relpath)
        if not inv_path.exists():
            raise FileNotFoundError(f"Inventory not found: {inv_path}")
        command += ["-i", str(inv_path)]

    if limit:
        command += ["--limit", limit]
    if tags:
        command += ["--tags", tags]

    if extra_vars_json:
        try:
            # Validate JSON is well-formed before passing to Ansible
            json.loads(extra_vars_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"extra_vars_json is not valid JSON: {exc}")
        command += ["-e", extra_vars_json]

    if check:
        command.append("--check")

    env = os.environ.copy()
    # Ensure Ansible honors project-specific config if present
    ansible_cfg = (JETLAG_DIR / "ansible.cfg")
    if ansible_cfg.exists():
        env["ANSIBLE_CONFIG"] = str(ansible_cfg)

    # Run from within the jetlag directory to respect relative paths inside playbooks
    result = _run_command(command, cwd=JETLAG_DIR, timeout_seconds=timeout_seconds)
    return result


@app.tool()
def create_all_yml_vars_file(
    lab: str,
    lab_cloud: str,
    cluster_type: str,
    ocp_build: str,
    ocp_version: str,
    public_vlan: bool = False,
    sno_use_lab_dhcp: bool = False,
    ssh_private_key_file: Optional[str] = None,
    ssh_public_key_file: Optional[str] = None,
    sno_install_disk: Optional[str] = None,
    control_plane_install_disk: Optional[str] = None,
    worker_install_disk: Optional[str] = None,
    pull_secret_lookup: Optional[str] = "../pull_secret.txt",
    extra_vars_json: Optional[str] = None,
    # Optional convenience (kept optional to preserve tool compatibility)
    worker_node_count: Optional[int] = None,
):
    """Create or overwrite ansible/vars/all.yml by copying the sample and editing keys.

    Behavior:
    - Copies ansible/vars/all.sample.yml VERBATIM first
    - Replaces only the specified keys IN-PLACE, preserving all comments and spacing
    - Appends override vars (extra vars) under the "Extra vars" section at the end
    """

    # Validate cluster_type
    allowed_cluster_types = {"sno", "mno", "vmno"}
    if cluster_type not in allowed_cluster_types:
        raise ValueError(f"cluster_type must be one of {sorted(allowed_cluster_types)}")

    target_dir = ANSIBLE_DIR / "vars"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "all.yml"
    sample_file = target_dir / "all.sample.yml"

    if not sample_file.exists():
        raise FileNotFoundError(f"Sample vars file not found: {sample_file}")

    original_text = sample_file.read_text(encoding="utf-8")

    def format_value(key: str, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return ""
        # Quote key string values where clarity helps
        if key in {"ocp_build", "ocp_version"}:
            return f'"{value}"'
        # Keep Jinja expressions quoted
        if isinstance(value, str) and "{{" in value and "}}" in value:
            return f'"{value}"'
        return str(value)

    def replace_or_append(text: str, key: str, value: Any) -> tuple[str, bool]:
        # Replace a 'key: ...' line wherever it appears, keeping indentation
        pattern = re.compile(rf"^(?P<indent>\s*){re.escape(key)}\s*:\s*.*$", re.MULTILINE)
        replacement = rf"\g<indent>{key}: {format_value(key, value)}"
        if pattern.search(text):
            return pattern.sub(replacement, text, count=1), True
        # If not found in sample, append under Extra vars section later via extra vars path
        return text, False

    # Build base replacements from provided params
    base_vars: Dict[str, Any] = {
        "lab": lab,
        "lab_cloud": lab_cloud,
        "cluster_type": cluster_type,
        "public_vlan": bool(public_vlan),
        "sno_use_lab_dhcp": bool(sno_use_lab_dhcp),
        "ocp_build": ocp_build,
        "ocp_version": ocp_version,
        "ssh_private_key_file": ssh_private_key_file or "~/.ssh/id_rsa",
        "ssh_public_key_file": ssh_public_key_file or "~/.ssh/id_rsa.pub",
        # Pull secret lookup string; quote to preserve Jinja
        "pull_secret": f"{{{{ lookup('file', '{pull_secret_lookup}') }}}}",
    }
    if worker_node_count is not None:
        base_vars["worker_node_count"] = worker_node_count
    if cluster_type == "sno" and sno_install_disk:
        base_vars["sno_install_disk"] = sno_install_disk
    if cluster_type != "sno":
        if control_plane_install_disk:
            base_vars["control_plane_install_disk"] = control_plane_install_disk
        if worker_install_disk:
            base_vars["worker_install_disk"] = worker_install_disk

    # Start from the sample and replace only matching lines (comments remain intact)
    updated_text = original_text
    updated_keys: List[str] = []
    for key, value in base_vars.items():
        updated_text, replaced = replace_or_append(updated_text, key, value)
        if replaced:
            updated_keys.append(f"{key} (replaced)")
        else:
            # If a base key did not exist in sample, we will append as override so it's visible
            pass

    # Parse extra vars (overrides) if provided
    extra_vars: Dict[str, Any] = {}
    if extra_vars_json:
        try:
            parsed = json.loads(extra_vars_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"extra_vars_json is not valid JSON: {exc}")
        if not isinstance(parsed, dict):
            raise ValueError("extra_vars_json must be a JSON object")
        extra_vars = parsed

    # Append any extra vars at the bottom under the Extra vars section
    if extra_vars:
        # Find the 'Extra vars' anchor. If not found, append at EOF.
        anchor_re = re.compile(r"^# Append override vars below\s*$", re.MULTILINE)
        m = anchor_re.search(updated_text)
        insertion_index = m.end() if m else len(updated_text)
        before = updated_text[:insertion_index]
        after = updated_text[insertion_index:]
        to_append_lines: List[str] = []
        # Ensure we start on a new line
        if not before.endswith("\n"):
            to_append_lines.append("")
        # Emit k: v lines for each extra var
        for k, v in extra_vars.items():
            to_append_lines.append(f"{k}: {format_value(k, v)}")
            updated_keys.append(f"{k} (appended override)")
        updated_text = before + "\n".join(to_append_lines) + ("\n" if not after.startswith("\n") else "") + after

    # Finally, write out the file
    target_file.write_text(updated_text, encoding="utf-8")
    return {"written": str(target_file), "updated": updated_keys}


if __name__ == "__main__":
    # Prefer stdio transport (typical for local MCP clients like Cursor/Claude)
    # Newer FastMCP exposes run(), older exposes run_stdio(). Try both safely.
    run_ok = False
    try:
        getattr(app, "run_stdio")()
        run_ok = True
    except AttributeError:
        try:
            getattr(app, "run")()
            run_ok = True
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"Failed to start MCP server: {exc}")
    if not run_ok:  # pragma: no cover
        raise SystemExit("Failed to start MCP server (no viable run method)")


