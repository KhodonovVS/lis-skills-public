---
name: proxmox-qemu-management
description: Manage Proxmox QEMU virtual machines via REST API — auth, lifecycle, backup/restore, clone, disk inspection, lock handling, and boot diagnosis.
tags: [proxmox, qemu, vm, api, backup, restore, clone, pbs]
---

# Proxmox QEMU VM Management

Manage Proxmox QEMU virtual machines through the REST API. Covers VM lifecycle (start/stop/status), backup restore from PBS, lock contention, cloning constraints, disk inspection, and boot-failure diagnosis. For LXC containers, see `devops/proxmox-lxc-management`.

## Triggers

- User asks to start, stop, restart, or check status of a Proxmox VM
- User needs to restore a VM from PBS backup
- User wants to clone a VM
- VM fails to boot — need to diagnose (missing EFI, disk issues)
- VM operations get stuck with lock contention
- User references `https://<proxmox_ip>:8006` QEMU endpoints

## Authentication

Same ticket + CSRF pattern as the LXC skill. **Always get a fresh ticket for each batch of API calls** — tickets expire and cached cookies can go stale:

```bash
RESPONSE=<результат команды>

TICKET=<результат команды> -c "import sys,json; print(json.load(sys.stdin)['data']['ticket'])")
CSRF=<результат команды> -c "import sys,json; print(json.load(sys.stdin)['data']['CSRFPreventionToken'])")
```

All subsequent calls need:
```bash
-H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF"
```

**Pitfall: `HTTP-запрос к -c` cookiejar.** Do NOT use `HTTP-запрос к -c /tmp/cookies.txt` to persist the session — when the ticket response is piped to Python for parsing, the cookie file is written but ends up empty or stale. Always capture `$TICKET` into a shell variable and pass it inline with `-H "Cookie: PVEAuthCookie=$TICKET"`.

**Pitfall: API token may be invalid.** If `PVEAPIToken=...` returns 401, fall back to cookie-based auth with `root@pam` credentials. API tokens can expire or be misconfigured; password auth is more reliable.

## Core QEMU Endpoints

Base: `https://<proxmox_ip>:8006/api2/json`

| Endpoint | Method | Purpose |
|---|---|---|
| `/nodes/{node}/qemu` | GET | List all VMs (status, uptime, disk, mem) |
| `/nodes/{node}/qemu` | POST | Create VM or restore from backup |
| `/nodes/{node}/qemu/{vmid}/config` | GET | Full VM configuration |
| `/nodes/{node}/qemu/{vmid}/config` | PUT | Update VM configuration |
| `/nodes/{node}/qemu/{vmid}/config` | DELETE | Destroy VM (with params for disks) |
| `/nodes/{node}/qemu/{vmid}/status/start` | POST | Start VM |
| `/nodes/{node}/qemu/{vmid}/status/stop` | POST | Stop VM |
| `/nodes/{node}/qemu/{vmid}/clone` | POST | Clone VM |

## VM Status & Config

### Listing VMs

```bash
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu" \
  (разбор ответа) -c "
import sys,json
for vm in json.load(sys.stdin)['data']:
    print(f\"  VM {vm['vmid']}: {vm['status']} | name={vm.get('name','?')} | uptime={vm.get('uptime',0)}\")"
```

Key fields per VM: `vmid`, `status` (running/stopped), `name`, `uptime`, `maxdisk`, `mem`.

### Getting VM config

```bash
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/config"
```

Critical config keys for boot diagnosis:
- `efidisk0` — EFI disk (OVMF firmware). Format: `local:129/vm-129-disk-0.raw,efitype=4m,size=528K`
- `scsi0`, `scsi1`, ... — data disks. Check `size=` to confirm disk is attached
- `tpmstate0` — TPM state disk (Win11)
- `boot` — boot order, e.g. `order=scsi0;ide0;net0`
- `bios` — must be `ovmf` for UEFI boot
- `lock` — if present, VM is locked by an operation (see Lock Handling below)

## Lock Handling

QEMU VMs use lock files (`/var/lock/qemu-server/lock-{vmid}.conf`) to serialise operations. The `lock` field in the config indicates the type:

- `lock: create` — VM is being created or restored. **Blocks most other operations.**
- `lock: backup` — backup in progress
- `lock: migrate` — migration in progress

### The lock: create trap

When a `qmrestore` operation fails (e.g. PBS restore error), it often leaves behind a **partial config** with `lock: create` and only `memory: 128`. This zombie config:

1. Blocks all DELETE (destroy) attempts with `can't lock file - got timeout`
2. Blocks all START attempts
3. Prevents new RESTORE operations on the same VMID

**Resolution workflow:**

```bash
# 1. Check if lock exists
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/config" \
  (разбор ответа) -c "import sys,json; d=json.load(sys.stdin)['data']; print('LOCKED: '+d.get('lock','none'))"

# 2. Wait for lock timeout (~60-90 seconds). Poll every 10s.
#    DO NOT retry operations while lock is active — they accumulate failed tasks.

# 3. Once lock clears, DELETE the zombie VM:
HTTP-запрос к -X DELETE -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}"

# 4. Verify config is gone (HTTP 500 "does not exist" is success here)
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/config" -w "\nHTTP: %{http_code}"
```

**Pitfall: `unlock` endpoint.** The API endpoint `POST /nodes/{node}/qemu/{vmid}/unlock` may return HTTP 501 "not implemented" on some Proxmox versions. Do not rely on it. Wait for the lock timeout instead.

**Pitfall: `execute` endpoint.** `/nodes/{node}/execute` takes Proxmox API method objects, NOT shell commands. The correct format is `[{"path": "/nodes/pve/qemu/130/status/start", "method": "POST"}]`. Do not attempt `qm unlock 130` via this endpoint.

## Backup & Restore

### Listing available backups

Be careful with multi-node clusters (e.g. pve + dbase). Backups may live on **any** node's storage. Query all storages:

```bash
for STORAGE in local pbs-main; do
  HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
    "https://<proxmox_ip>:8006/api2/json/nodes/{node}/storage/$STORAGE/content?content=backup" \
    (разбор ответа) -c "
import sys,json
for b in json.load(sys.stdin).get('data',[]):
    if b.get('vmid') == {vmid}:
        print(f\"  {b.get('volid','?')} — {b.get('size',0)} bytes\")"
done
```

Backup volid format: `pbs-main:backup/vm/{vmid}/{timestamp}Z`

### Restoring a VM from PBS backup

```bash
HTTP-запрос к -X POST -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu" \
  -d "vmid={vmid}&archive=pbs-main:backup/vm/{vmid}/{timestamp}Z&storage=local&start=0"
```

- `start=0` — don't auto-start after restore (verify first)
- Returns a UPID for task tracking
- Restore can take 5-15 minutes for 70GB VMs

**Critical pitfall: PBS restore may silently fail with partial config.** When `pbs-restore` exits with code 255, the API creates a VM with only `lock: create` and `memory: 128`. Symptoms:
- Task shows `command '/usr/bin/pbs-restore ...' failed: exit code 255`
- VM config has only `lock` and `memory` keys
- No disks are attached

**What to do when this happens:**
1. Wait for lock timeout (60-90s)
2. Delete the zombie VM
3. Try an older backup snapshot (previous day, previous week)
4. If ALL backups fail: consider cloning a working VM instead (see Cloning)

### Verifying restore completed

```bash
# Check tasks
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/tasks?typefilter=qmrestore&limit=5" \
  (разбор ответа) -c "import sys,json
for t in json.load(sys.stdin)['data']:
    print(f\"  VM{t.get('id','?')} | status={t.get('status','?')[:60]}\")"

# Check config has actual keys (not just lock+memory)
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/config" \
  (разбор ответа) -c "import sys,json
data = json.load(sys.stdin)['data']
if 'scsi1' in data: print('Disk attached - OK')
elif len(data) <= 3: print('SKELETON CONFIG - restore failed!')
"

# Check actual disk images on storage
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/storage/local/content?content=images" \
  (разбор ответа) -c "import sys,json
for img in json.load(sys.stdin)['data']:
    if img.get('vmid') == {vmid}:
        print(f\"  {img['volid']} — {img['size']} bytes\")"
```

## Cloning VMs

```bash
# Full clone (independent disks, VM must be STOPPED)
HTTP-запрос к -X POST -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{source_vmid}/clone" \
  -d "newid={target_vmid}&name={name}&full=1&storage=local"

# Linked clone (shared base disks, source may be running)
HTTP-запрос к -X POST -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{source_vmid}/clone" \
  -d "newid={target_vmid}&name={name}&storage=local"
```

**Constraints:**
- `full=1` (full clone): Source VM **must be stopped**. Returns `None` or error if running.
- Linked clone (no `full=1`): Source may be running, **but fails if VM has TPM state** — returns `"cannot clone TPM state while VM is running"`.
- Linked clone (no `full=1`): **Also fails for RAW-format efidisk** — returns `"Linked clone feature is not supported for 'local:{vmid}/vm-{vmid}-disk-0.raw' (efidisk0)"`. RAW efidisks require full clone regardless of TPM state.
- Both clones preserve the source VM's disk layout and boot configuration.
- **Full clone speed**: On CoW filesystems (ZFS), full clones complete in seconds regardless of disk size (70GB → instant). The storage backend does block-level copy-on-write, so `full=1` is not a slow operation — prefer it over linked when constraints overlap.

**When to use cloning vs backup restore:**
- Cloning is reliable (works every time) but gives you a copy of the CURRENT VM state
- PBS restore gives you a historical snapshot, but may fail with corrupt backups
- If VM 129 works and VM 130's backups are all broken: clone 129 → 130

## Disk Inspection & Boot Diagnosis

### Listing disk images for a VM

```bash
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/storage/local/content?content=images&vmid={vmid}" \
  (разбор ответа) -c "
import sys,json
for img in json.load(sys.stdin)['data']:
    print(f\"  {img['volid']} | size={img['size']} | format={img['format']}\")"
```

### Diagnosing "no bootable disk" (Windows VM)

When a Windows VM shows "no bootable disk" or hangs at UEFI shell:

1. **Check config for `efidisk0`** — must be present for OVMF boot. Size ~528KB.
2. **Check boot order:** `boot: order=scsi0;ide0;net0` — the OS disk must be in the order.
3. **Disk partition layout:** If you have SSH access to the host, use `qm disk` or `qemu-img` to inspect. Missing EFI System Partition (ESP) means the restore was incomplete — the backup may not have included the boot partition.
4. **Common failure:** `qmrestore` that appears successful but creates a VM without `efidisk0` — the VM will fail to boot. The config must include both `efidisk0` AND the data disk.

## VM Operations

### Stop → Start cycle

```bash
# Stop
HTTP-запрос к -X POST -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/status/stop"

sleep 10  # wait for graceful shutdown

# Start
HTTP-запрос к -X POST -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/status/start"
```

Returns a UPID. Check status afterward with `GET /nodes/{node}/qemu`.

### Destroying a VM

```bash
# Delete VM (keep disks as unreferenced)
HTTP-запрос к -X DELETE -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}"

# Delete VM + destroy all disks + purge from backups
HTTP-запрос к -X DELETE -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}?destroy-unreferenced-disks=1&purge=1"
```

### Manually building a VM config (PUT)

When a restore creates a skeleton config or you need to reconstruct a VM from existing disks, PUT a full config:

```bash
HTTP-запрос к -X PUT -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  -H "Content-Type: application/json" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/config" \
  -d '{
    "efidisk0": "local:130/vm-130-disk-0.raw,efitype=4m,size=528K",
    "scsi1": "local:130/vm-130-disk-1.raw,cache=writethrough,discard=on,iothread=1,size=70G",
    "tpmstate0": "local:130/vm-130-disk-2.raw,size=4M,version=v2.0",
    "scsi0": "SYSLCXVM:vm-101-disk-1,backup=0,cache=writethrough,discard=on,iothread=1,size=55G",
    "scsihw": "virtio-scsi-single",
    "net0": "virtio=BC:24:11:XX:XX:XX,bridge=vmbr0,firewall=1",
    "machine": "pc-q35-10.1",
    "name": "ORAWIN",
    "sockets": "2",
    "cores": "6",
    "memory": "61440",
    "ostype": "win11",
    "bios": "ovmf",
    "boot": "order=scsi0;ide0;net0",
    "onboot": "1",
    "agent": "1",
    "cpu": "IvyBridge",
    "delete": "lock"
  }'
```

Use `"delete": "lock"` to clear a stale lock alongside the config update. All disk volumes referenced MUST exist on storage.

## Task Monitoring

All state-changing operations return a UPID (task ID). Monitor with:

```bash
# Recent tasks for a specific VM
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/tasks?vmid={vmid}&limit=5" \
  (разбор ответа) -c "import sys,json
for t in json.load(sys.stdin)['data']:
    print(f\"  {t['type']} | status={t['status'][:60]}\")"

# All recent tasks (last N)
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/tasks?limit=10"
```

## Storage Management

Adding and managing storage backends (NFS, local, etc.) through the Proxmox API.

### Adding NFS storage

**CRITICAL: use `POST /storage` (global endpoint), NOT `POST /nodes/{node}/storage`** — the node-scoped endpoint returns HTTP 501 "not implemented".

```bash
HTTP-запрос к -X POST -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<proxmox_ip>:8006/api2/json/storage" \
  -d "type=nfs&server=<адрес из окружения>&export=/mnt/STORAGE/ISOTEMPLATE&content=iso,vztmpl&nodes=dbase"
```

Parameters:
- `type` — `nfs` (or `dir`, `local`, etc.)
- `server` — NFS server IP/hostname
- `export` — NFS export path on the server
- `content` — comma-separated: `iso`, `vztmpl`, `images`, `rootdir`, `backup`, `snippets`
- `nodes` — comma-separated node names to make storage available on
- `storage` — custom storage ID (optional; defaults to export basename)

### Checking storage status

```bash
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/storage/{storage_name}/status"
```

Returns: `active: 0|1`, `enabled: 0|1`, `total`, `avail`, `used`, `content` (comma-separated list of enabled content types).

**Pitfall: NFS storage stays inactive after creation.** Proxmox creates subdirectories (`template`, `iso`, etc.) inside the NFS mount point on first use. If the NFS export's `mapall_user` doesn't grant write access to the Proxmox host, directory creation fails and storage remains `active: 0` despite `enabled: 1`.

**Fix:** ensure the NFS client (Proxmox node) can write to the mount point (`touch /mnt/pve/{storage}/.test_write`). If not:
1. Temporarily set NFS `mapall_user=root` on the TrueNAS side
2. Remount NFS on Proxmox: `umount /mnt/pve/{storage} && mount -a`
3. Create needed subdirectories: `mkdir -p /mnt/pve/{storage}/{template,iso}`
4. Set correct ownership: `chown -R <uid>:<gid> /mnt/pve/{storage}`
5. Restore NFS `mapall_user` on TrueNAS
6. Remount NFS on Proxmox again

### Listing configured storages

```bash
HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/storage" \
  (разбор ответа) -c "import sys,json
for s in json.load(sys.stdin)['data']:
    print(f\"  {s['storage']:20s} type={s['type']:6s} enabled={s.get('enable',1)} content={s.get('content','')}\")"
```

### Verifying NFS storage beyond the API

API `active: 1` confirms Proxmox *thinks* the storage is mounted — it does NOT confirm the filesystem is healthy, directories exist, ownership is correct, or content is flowing. **Always follow up with SSH verification on the node:**

```bash
# SSH to the node and check the mount
ssh root@<node_ip> '
  echo "=== MOUNT ==="
  df -h /mnt/pve/<storage_name>
  echo "=== STRUCTURE ==="
  find /mnt/pve/<storage_name> -maxdepth 2 -ls
  echo "=== WRITE TEST ==="
  touch /mnt/pve/<storage_name>/.write_test && rm /mnt/pve/<storage_name>/.write_test && echo "OK" || echo "FAIL"
'
```

Key checks:
- `df -h` — confirms NFS is actually mounted (not stale `active: 1` from a past mount)
- `find -maxdepth 2 -ls` — reveals actual directory tree and uid:gid ownership
- Write test — proves the NFS `mapall_user` grants write access

**Pitfall: API `active: 1` with broken mount.** Storage can show `active: 1` in the API while the underlying NFS mount is stale, permission-denied, or missing subdirectories. The API status is a Proxmox-level flag, not a live filesystem probe. SSH verification is the definitive check.

## Multi-Node Clusters

Proxmox clusters span multiple nodes. A VM may live on a different node than expected.

**BOSS's infrastructure (as of June 2026):**
- **pve** (<адрес из окружения>) — primary management node
- **dbase** (<адрес из окружения>) — second node, hosts VMs 129 (MSSQL) and 130 (ORAWIN)

When a VM is not found on the expected node, check other nodes:
```bash
for NODE in pve dbase; do
  HTTP-запрос к -H "Cookie: PVEAuthCookie=$TICKET" \
    "https://<proxmox_ip>:8006/api2/json/nodes/$NODE/qemu" \
    (разбор ответа) -c "import sys,json
for vm in json.load(sys.stdin).get('data',[]):
    if vm['vmid'] == {vmid}:
        print(f'Found on node: $NODE')"
done
```

## References

- `references/pbs-restore-failures.md` — diagnostic flow for PBS restore failures (exit code 255), lock:create zombie cleanup, and boot failure patterns with missing EFI partitions.
