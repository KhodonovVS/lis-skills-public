# Installing Docker-Based Applications in Proxmox LXC

When community-scripts (formerly Proxmox VE Helper-Scripts) fail due to TTY / whiptail requirements, install the application manually via Docker inside a manually created LXC container.

## When to Use This Pattern

- Community-script uses `whiptail` / dialog menus and fails with "TERM environment variable not set" or "User exited script" when run via SSH
- The application is available as a Docker image (check: `docker search <app>` or Docker Hub)
- You need full control over container resources, IP, or storage location

## Step 1: Find a Storage Pool for Container RootFS

Not all storages support LXC root filesystems. Check which ones do:

```bash
ssh root@pve "pvesh get /storage" | grep -v '^$'
```

Look for storages with `rootdir` in their content type:

```bash
ssh root@pve "pvesh get /nodes/pve/storage"
# Look for lines containing "rootdir" — those support LXC containers
```

**Example output:**
```
│ rootdir,images │ LXCCONT     │ zfspool │ 73% │
│ rootdir,images │ SSD-F120    │ lvmthin │  0% │  ← empty pool, good choice
│ rootdir,images │ SSD-K120    │ lvmthin │  0% │
```

**Pitfall:** `local` and `local-lvm` may NOT support LXC rootfs. Verify with the output above, not by guessing.

## Step 2: Check Template Availability

```bash
# List already-downloaded templates
ssh root@pve "pveam list TEMPLATES" | grep debian

# Or search for available ones
ssh root@pve "pveam available --section system | grep debian"

# Download if needed
ssh root@pve "pveam download TEMPLATES debian-12-standard_12.12-1_amd64.tar.zst"
```

**OS version matters:** Some apps only support specific Debian/Ubuntu versions. Check the app's docs.

## Step 3: Create the LXC Container

### Find next free CT ID

```bash
ssh root@pve "pvesh get /cluster/nextid"
# Example output: 143
```

### Create via pct

```bash
ssh root@pve "pct create <CTID> TEMPLATES:vztmpl/<template-name> \
  --hostname <hostname> \
  --rootfs <STORAGE>:<size_gb> \
  --memory <ram_mb> \
  --cores <cpu_cores> \
  --net0 'name=eth0,bridge=vmbr0,ip=<static_ip>/<cidr>,gw=<gateway>' \
  --unprivileged 1 \
  --password <root_password> \
  --features keyctl=1,fuse=1,nesting=1 \
  --searchdomain <domain>"
```

**Key parameters:**
| Flag | Purpose | Example |
|------|---------|---------|
| `--rootfs STORAGE:8` | 8 GB on the chosen pool | `--rootfs SSD-F120:8` |
| `--net0` | Network config with static IP | `--net0 'name=eth0,bridge=vmbr0,ip=<адрес из окружения>/20,gw=<адрес из окружения>'` |
| `--features` | Enable Docker-required features | `keyctl=1,fuse=1,nesting=1` |
| `--unprivileged 0` | **Must be 0** for Docker inside LXC | Unprivileged containers cannot run Docker |

**Pitfall: Unprivileged vs Docker:** Many hosts require privileged containers (`--unprivileged 0`) for Docker. However, on some Proxmox/LXC setups, Docker works fine with `--unprivileged 1` when `keyctl=1,fuse=1,nesting=1` features are enabled. If Docker fails to start (AppArmor errors, cgroup errors, `failed to connect to containerd`), switch `--unprivileged 0`. Test first with unprivileged + features — fewer security warnings.

### Handle locks on creation timeout

`pct create` can timeout (90s default) while the template is still extracting. Check and unlock:

```bash
ssh root@pve "pct list | grep <CTID>"
# If stopped, remove stale lock and start
ssh root@pve "rm -f /run/lock/lxc/pve-config-<CTID>.lock && pct start <CTID>"
```

## Step 4: Install Docker Inside Container

```bash
# Inside the container
ssh root@pve "pct exec <CTID> -- bash -c '
  HTTP-запрос к -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh
'"

# Or via apt (slower but more reliable if get.docker.com is blocked)
ssh root@pve "pct exec <CTID> -- apt-get update -qq && apt-get install -y -qq docker.io"
```

**Verify:**
```bash
ssh root@pve "pct exec <CTID> -- docker --version"
```

## Step 5: Run Application via Docker

### Generate strong secret keys

```bash
# Generate on PVE host, pass into container
ssh root@pve "openssl rand -hex 64 > /tmp/app_key.txt"
# Then read and use in docker run
KEY=<результат команды>
ssh root@pve "pct exec <CTID> -- docker run -d ... -e SECRET_KEY_BASE=*** ..."
```

**Pitfall: Passing variables through SSH:** When passing bash variables like `$KEY` through nested SSH + pct exec commands, use single quotes for the outer script and let the variable expand at the correct level. Example:

```bash
# WRONG — $KEY expands on the local host before SSH
ssh root@pve "pct exec <CTID> -- docker run -d -e SECRET_KEY_BASE=*** ..."

# RIGHT — write key to file, read via SSH
ssh root@pve "openssl rand -hex 64 > /tmp/app_key.txt"
ssh root@pve 'KEY=<результат команды> && pct exec <CTID> -- docker run -d -e SECRET_KEY_BASE="$KEY" ...'
```

### Common docker run patterns

```bash
# Basic — single port, one volume
pct exec <CTID> -- docker run -d --name <app> \
  -p 80:80 \
  -e KEY=VALUE \
  -v /opt/<app>/data:/app/data \
  --restart unless-stopped \
  <image>:<tag>

# With HTTPS disabled and hostname set (e.g. OpenProject)
pct exec <CTID> -- docker run -d --name openproject \
  -p 80:80 \
  -e OPENPROJECT_HOST__NAME=<ip_or_hostname> \
  -e OPENPROJECT_HTTPS=false \
  -e SECRET_KEY_BASE=*** \
  -v /opt/openproject/pgdata:/var/openproject/pgdata \
  -v /opt/openproject/assets:/var/openproject/assets \
  --restart unless-stopped \
  openproject/openproject:17
```

## Step 6: Verify and Access

```bash
# Wait for initialization
sleep 30

# Check container status
ssh root@pve "pct exec <CTID> -- docker ps --filter name=<app> --format '{{.Status}}'"

# Check application health
ssh root@pve "pct exec <CTID> -- HTTP-запрос к -o /dev/null -w '%{http_code}' -H 'Host: <ip_or_hostname>' http://localhost/"

# Test from outside
HTTP-запрос к -sL -o /dev/null -w '%{http_code}' -H 'Host: <ip_or_hostname>' http://<container_ip>/
```

**Pitfall: 400 Bad Request:** Some apps (OpenProject, nginx-based) validate the `Host` header. Use `-H 'Host: <configured_hostname>'` in HTTP-запрос к requests. If the Host is a bare IP, pass it explicitly.

**Pitfall: 503 Service Unavailable on first run:** Docker apps often need time for database migrations on first startup (especially CMS/ERP apps). Wait 1-3 minutes before the first check. Check logs:
```bash
ssh root@pve "pct exec <CTID> -- docker logs <app> --tail 20"
```

## Worked Example: OpenProject on PVE

See `proxmox-management` → CT 143 (<адрес из окружения>):
- Debian 12 (bookworm) LXC
- 2 CPU, 4 GB RAM, 8 GB SSD
- Docker with OpenProject 17.5
- URL: http://<адрес из окружения> (with Host header `<адрес из окружения>`)
- Credentials: stored in Qdrant (`hermes_memory` collection)
