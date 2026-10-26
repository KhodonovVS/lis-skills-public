---
name: proxmox-lxc-management
description: Manage Proxmox LXC containers via REST API — auth, creation, lifecycle, network config, and container operations.
tags: [proxmox, lxc, api, network, container, virtualization]
---

# Proxmox LXC Management

Manage Proxmox LXC containers programmatically through the REST API: authentication, container lifecycle (start/stop/reboot), configuration changes (especially networking), and `pct`-level operations via SSH.

## Triggers

- User asks to create a new container on Proxmox or set up a development/testing environment
- User asks to start/stop/restart a container on Proxmox
- User needs to change container network config (IP, gateway, DHCP ↔ static)
- User mentions `pct exec`, `pct push`, `pct pull` or other Proxmox container commands
- Task involves modifying container configuration files (`/etc/pve/lxc/<vmid>.conf`)
- User references `https://<proxmox_ip>:8006` or the Proxmox VE API

## Authentication

All Proxmox API calls need a ticket (auth cookie) and CSRF token:

```bash
# Get ticket + CSRF token in one step
RESPONSE=<результат команды>

TICKET=<результат команды> -c "import sys,json; print(json.load(sys.stdin)['data']['ticket'])")
CSRF=<результат команды> -c "import sys,json; print(json.load(sys.stdin)['data']['CSRFPreventionToken'])")
```

Use `-k` (insecure TLS) because Proxmox uses self-signed certs. All subsequent API calls need:
```
Cookie: PVEAuthCookie=$TICKET
CSRFPreventionToken: $CSRF
```

## Core API Endpoints

```
Base: https://<proxmox_ip>:8006/api2/json
```

| Endpoint | Method | Purpose |
|---|---|---|
| `/nodes/{node}/lxc` | GET | List all containers |
| `/nodes/{node}/lxc/{vmid}` | GET | Container details + config |
| `/nodes/{node}/lxc/{vmid}/status/start` | POST | Start container |
| `/nodes/{node}/lxc/{vmid}/status/stop` | POST | Stop container |
| `/nodes/{node}/lxc/{vmid}/status/reboot` | POST | Reboot container |
| `/nodes/{node}/lxc/{vmid}/config` | PUT | Update container configuration |

### Listing containers

```bash
HTTP-запрос к \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc"
```

Returns array of containers with `vmid`, `name`, `status`, `maxdisk`, `uptime`, etc.

### Getting container details

```bash
HTTP-запрос к \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc/<vmid>"
```

Returns full config including `net0`, `mp0`..`mpN`, `hostname`, root filesystem size, etc.

## Template Management

LXC containers are created from templates. There are two key facts:
- **Templates live on `dir`-type storages** (e.g. `TEMPLATES`, `local`), NOT on `zfspool` or block storages
- **Root filesystem goes on a pool storage** (e.g. `LXCCONT` on `zfspool`, or `local-lvm`)

### Finding available templates (from remote repository)

```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pveam available --section system | grep ubuntu"
```

This lists downloadable templates. Key Ubuntu LTS templates: `ubuntu-24.04-standard_24.04-2_amd64.tar.zst`, `ubuntu-22.04-standard_22.04-2_amd64.tar.zst`.

### Checking what's already downloaded

```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pveam list <storage>"
# Example:
sshpass -p '<pass>' ssh root@<proxmox_ip> "pveam list TEMPLATES"
```

### Downloading a template

```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pveam download <storage> <template-name>"
# Example:
sshpass -p '<pass>' ssh root@<proxmox_ip> "pveam download TEMPLATES ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
```

### Pitfall: wrong storage type

If you get `Storage does not support templates!`, the storage you specified is not a `dir` type. Use `pvesm status` to see storage types and pick a `dir` one:

```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pvesm status"
# Look for type=dir storages (e.g. TEMPLATES, local, backups)
```

## Container Creation

Two methods: REST API (preferred for automation) or `pct create` via SSH.

### Finding the next available VMID

List existing containers and pick the first gap, or use the next-available API:

```bash
HTTP-запрос к \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc" \
  (разбор ответа) -c "import sys,json; ids=[c['vmid'] for c in json.load(sys.stdin)['data']]; print(f'Max: {max(ids)}, Next: {max(ids)+1}')"
```

Proxmox API also provides `/nodes/{node}/lxc?nextid=1`:

```bash
HTTP-запрос к \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/nextid"
```

### Method 1: REST API (POST /nodes/{node}/lxc)

This is the preferred method for scripting — it returns a UPID for task tracking.

```bash
HTTP-запрос к -X POST \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  -H "Content-Type: application/json" \
  -d '{
    "vmid": 138,
    "hostname": "sonar-dev",
    "ostemplate": "TEMPLATES:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst",
    "storage": "LXCCONT",
    "rootfs": "LXCCONT:8",
    "memory": 4096,
    "cores": 2,
    "net0": "name=eth0,bridge=vmbr0,ip=dhcp,type=veth",
    "password": "sonar2024",
    "unprivileged": 0,
    "start": 1
  }' \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc"
```

**Required parameters:**
| Field | Description | Example |
|---|---|---|
| `vmid` | Container ID (must be free) | `138` |
| `hostname` | Container hostname | `"sonar-dev"` |
| `ostemplate` | Template reference: `<storage>:vztmpl/<file>` | `"TEMPLATES:vztmpl/ubuntu-24.04...tar.zst"` |
| `storage` | Storage for root filesystem | `"LXCCONT"` |
| `rootfs` | Root filesystem: `<storage>:<size_gb>` | `"LXCCONT:8"` |
| `password` | Root password for the container | `"sonar2024"` |

**Optional parameters:**
| Field | Default | Description |
|---|---|---|
| `memory` | 512 | RAM in MB |
| `cores` | 1 | CPU cores |
| `net0` | — | Network config: `name=<if>,bridge=<bridge>,ip=dhcp,type=veth` |
| `unprivileged` | 0 | 0 = privileged, 1 = unprivileged |
| `start` | 0 | 1 = auto-start after creation |

### Method 2: pct create (via SSH)

```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct create <vmid> <template-path> \\
  --hostname <name> \\
  --storage <pool> \\
  --rootfs <pool>:<size> \\
  --memory <mb> \\
  --cores <n> \\
  --net0 name=eth0,bridge=vmbr0,ip=dhcp,type=veth \\
  --password <password> \\
  --unprivileged 0"
```

### Waiting for creation to complete

Check container status (polling):

```bash
sleep 15 && sshpass -p '<pass>' ssh root@<proxmox_ip> "pct list | grep <vmid>"
```

Look for `running` status. If still `stopped`, the template is still extracting.

## Post-Creation Setup

### Enabling SSH root login

New containers may have `PermitRootLogin` set to `prohibit-password`. Fix this:

```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct exec <vmid> -- bash -c '
  sed -i \"s/#PermitRootLogin prohibit-password/PermitRootLogin yes/\" /etc/ssh/sshd_config
  systemctl restart sshd
'"
```

Then test SSH:
```bash
sshpass -p '<container_password>' ssh -o StrictHostKeyChecking=no root@<container_ip> "echo SSH_OK"
```

If SSH still fails with `Permission denied`, install/enable SSH server:
```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct exec <vmid> -- bash -c '
  apt-get update -qq && apt-get install -y -qq openssh-server
  systemctl enable ssh --now
'"
```

### Getting the container IP

After creation with DHCP, the IP is assigned by the DHCP server:

```bash
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct exec <vmid> -- ip -4 addr show eth0 | grep inet"
```

Or via Proxmox API:
```bash
HTTP-запрос к \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc/<vmid>/interfaces"
```

## Network Configuration

### Changing container network config (DNS-safe)

To change IP, gateway, or switch between DHCP and static, you MUST stop the container first. The Proxmox API rejects network config changes on running containers.

**Full workflow:**

```bash
# 1. Stop container
HTTP-запрос к -X POST \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc/<vmid>/status/stop"

# Wait for stop (check with GET /nodes/{node}/lxc/{vmid}/status/current)

# 2. Update network config
HTTP-запрос к -X PUT \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  -H "Content-Type: application/json" \
  -d '{"net0": "name=eth0,bridge=vmbr0,gw=<адрес из окружения>,hwaddr=BC:24:11:XX:XX:XX,ip=dhcp,type=veth"}' \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc/<vmid>/config"

# 3. Start container
HTTP-запрос к -X POST \
  -H "CSRFPreventionToken: $CSRF" \
  -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/<node>/lxc/<vmid>/status/start"
```

**Config field format** (`net<N>` parameter):
```
name=eth0,bridge=vmbr0,gw=<gateway_ip>,hwaddr=<mac>,ip=<dhcp|static_ip/cidr>,type=veth
```

Examples:
```
# DHCP with explicit gateway hint
net0=name=eth0,bridge=vmbr0,gw=<адрес из окружения>,hwaddr=BC:24:11:C1:49:58,ip=dhcp,type=veth

# Static IP
net0=name=eth0,bridge=vmbr0,gw=<адрес из окружения>,hwaddr=BC:24:11:C1:49:58,ip=<адрес из окружения>/20,type=veth
```

### Pitfall: DHCP + explicit gateway

When `ip=dhcp` is set, the `gw=` field in Proxmox config is only a **hint** written to the LXC config file. The actual default gateway is determined by the DHCP server response inside the container. If the DHCP server advertises a different gateway, the container will use that one, ignoring the Proxmox `gw=` setting.

To **guarantee** a specific gateway:
- Use `ip=<static_ip>/<cidr>,gw=<gateway>` (static addressing) — but this requires knowing the correct CIDR and avoiding IP conflicts
- OR configure the gateway inside the container via SSH/pct exec after boot: `ip route replace default via <gw>`

### Pitfall: static IP breaks container services

If the container's services bind to a specific IP that changes, they may fail to start. After switching DHCP→static, verify service health:
```bash
timeout 3 bash -c 'echo >/dev/tcp/<new_ip>/<port>' && echo "OK" || echo "DEAD"
```

If the service is dead after a network change, SSH into the container and restart it:
```bash
sshpass -p '<password>' ssh root@<container_ip> systemctl restart <service>
```

## `/nodes/{node}/execute` — NOT for shell commands

The Proxmox API endpoint `/nodes/{node}/execute` expects Proxmox API method objects, **NOT** arbitrary shell commands. It is designed for executing Proxmox-internal API calls programmatically, not for running `pct exec` or bash.

Do NOT attempt to pass shell commands to this endpoint. The correct format is:
```json
{"commands": [{"path": "/nodes/pve/lxc/106/status/start", "method": "POST"}]}
```
...which would start container 106. This is equivalent to calling the endpoint directly.

For shell access to containers, use one of:
- **SSH + pct exec** (if SSH access to Proxmox host is available)
- **Proxmox web console** (browser — `https://<proxmox_ip>:8006`, navigate to container → Console)
- **sshpass directly to container** (if container SSH password is known)

## Container Operations via SSH (pct)

When SSH to the Proxmox host is available, use `pct` commands for direct container access:

```bash
# Execute command inside container
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct exec <vmid> -- <command>"

# Push file into container
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct push <vmid> /host/path /container/path"

# Pull file from container
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct pull <vmid> /container/path /host/path"

# List all containers
sshpass -p '<pass>' ssh root@<proxmox_ip> "pct list"
```

## MacOS Compatibility

The `timeout` command on macOS does not support `-v` (verbose). Use `timeout 3 bash -c 'echo >/dev/tcp/<ip>/<port>' 2>/dev/null && echo UP || echo DOWN` for TCP connectivity checks. The `bash -c` wrapper with `/dev/tcp` works on both Linux and macOS.

## Verification

After any container config change:
1. Check the container started: `GET /api2/json/nodes/<node>/lxc/<vmid>/status/current` → look for `"status":"running"`
2. Test TCP connectivity: `timeout 3 bash -c 'echo >/dev/tcp/<ip>/<port>' && echo "OK" || echo "DEAD"`
3. Verify the service health endpoint: `HTTP-запрос к --connect-timeout 5 http://<ip>:<port>/`

## References

- `references/lxc-creation-example.md` — full real-world example of creating a development container (CT 138, Sonarr), including template download, API payload, post-creation SSH setup, and software stack installation.

## Common Pitfalls

### Multi-node cluster: check ALL nodes
Proxmox может быть кластером из нескольких узлов. Если CT/VM не найден на текущем узле, проверь другие узлы через `/cluster/status`. В инфраструктуре BOSS: pve (<адрес из окружения>) + dbase (<адрес из окружения>). VM 129/130 живут на dbase.

### Stale SSH host keys

If SSH fails with "Host key verification failed" (after Proxmox reinstall or IP reassignment):
```bash
ssh-keygen -R <proxmox_ip> -f ~/.ssh/known_hosts
```

### API 401 Unauthorized

Ticket expired (typical lifetime ~2 hours). Re-authenticate with `POST /access/ticket`.

### API 400 on config update

The container is likely still running. Stop it first: `POST /nodes/{node}/lxc/{vmid}/status/stop`.

### Container starts but service unreachable

After network config changes, services may not auto-restart or may bind to old IP. SSH into the container and check:
```bash
systemctl status <service>
ip addr show
ip route show default
```
