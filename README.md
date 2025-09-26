# jetlag-mcp
A Model Context Protocol Server for jetlag
Jetlag MCP Server
=================

This directory contains a Model Context Protocol (MCP) server that exposes helpers for the `jetlag` project:

- List and run Ansible playbooks in `jetlag/ansible`
- List roles in `jetlag/ansible/roles`
- List and read docs under `jetlag/docs`
- Read arbitrary text files inside the `jetlag` repository

Quick start
-----------

1. Bootstrap (creates venv and installs deps):

```
./bootstrap.sh
```

2. Run the server over stdio (typical for local MCP clients):

```
python server.py
```

Client configuration
--------------------

Point your MCP client to run this server via stdio. Example client config snippet:

```json
{
  "mcpServers": {
    "jetlag-mcp": {
      "command": "python",
      "args": [
        "/absolute/path/to/your/checkout/jetlag-mcp/server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

Tools
-----

- `list_playbooks()` → Returns objects with `name` and `path` under `jetlag/ansible`.
- `list_roles()` → Returns array of role directory names.
- `list_docs()` → Returns markdown file paths under `jetlag/docs`.
- `read_text_file(relative_path)` → Reads a UTF-8 text file within `jetlag`.
- `run_playbook(playbook_name, inventory_relpath?, limit?, tags?, extra_vars_json?, check?, timeout_seconds?)` → Executes `ansible-playbook` from the `jetlag` repo root, honoring `ansible.cfg`.
- `create_all_yml_vars_file(lab, lab_cloud, cluster_type, ocp_build, ocp_version, public_vlan?, sno_use_lab_dhcp?, ssh_private_key_file?, ssh_public_key_file?, sno_install_disk?, control_plane_install_disk?, worker_install_disk?, pull_secret_lookup?, extra_vars_json?)` → Creates/overwrites `ansible/vars/all.yml` with provided values (supports SNO and MNO install disk settings). Pull secret is set using a Jinja file lookup path (default `../pull_secret.txt`).

Notes
-----

- The server assumes the `jetlag` repository is a sibling of this directory.
- Paths outside `jetlag` are rejected for safety.
- Ensure Ansible is installed and available in `PATH` to run playbooks.