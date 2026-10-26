# PBS Restore Failure Diagnostics

This captures the concrete failure modes, error messages, and recovery patterns encountered when restoring QEMU VMs from Proxmox Backup Server.

## Failure Mode 1: pbs-restore exits 255, creates skeleton config

### Symptoms

1. Task shows: `command '/usr/bin/pbs-restore --repository root@pam!pveconn@<адрес из окружения>:main vm/130/2026-06-09T00:00:58Z local:130/vm-130-disk-1.raw ...' failed: exit code 255`
2. VM 130 config after restore has ONLY: `lock: create`, `memory: "128"`, `digest`
3. No `efidisk0`, no `scsi1`, no `name`, no `bios`
4. `lock: create` persists and blocks all further operations

### Root cause

The PBS backup is corrupted or the restore command fails during data transfer. Proxmox creates the VM skeleton before starting the actual data restore. When `pbs-restore` fails, the skeleton config is left behind with a lock.

### Recovery

1. Wait 60-90 seconds for `lock: create` to timeout (poll with `GET /nodes/{node}/qemu/{vmid}/config`)
2. Once lock clears, DELETE the VM: `DELETE /nodes/{node}/qemu/{vmid}`
3. Verify config is gone (HTTP 500 response to `GET /config` = success)
4. Try an older snapshot: `pbs-main:backup/vm/{vmid}/{earlier_date}Z`

### Prevention

- Always check `POST /qemu` response — it returns `None` if restore immediately failed
- Verify restore by checking config has `scsi1` (data disk) key, not just `lock`+`memory`
- If one date's backup fails, try another date before resorting to cloning

## Failure Mode 2: All PBS snapshots for a VM are broken

### Real-world example (June 9, 2026)

VM 130 backups dated 2026-06-07, 2026-06-08, and 2026-06-09 all failed with exit code 255. VM 129 backups from the same dates restored successfully.

### Recovery path

Instead of restoring from backup, **clone a working VM**:

```bash
# 1. Delete broken VM 130 (wait for lock timeout first)
# 2. Clone VM 129 → 130
curl -sk -X POST \
  -H "Cookie: PVEAuthCookie=$TICKET" -H "CSRFPreventionToken: $CSRF" \
  "https://<адрес из окружения>/api2/json/nodes/dbase/qemu/129/clone" \
  -d "newid=130&name=ORAWIN&full=1&storage=local"
```

Note: full clone requires source VM to be stopped. Linked clone fails if source has TPM state, has RAW-format efidisk (`"Linked clone feature is not supported for ..."`), or is running with any of these. On CoW storage (ZFS) full clones complete in seconds — prefer `full=1` when any constraint is in doubt.

## Failure Mode 3: Lock contention cascade

### What it looks like

When multiple operations are submitted while a lock is active, tasks accumulate and all fail:
```
qmdestroy | VM130 | can't lock file ... - got timeout
qmstart   | VM130 | can't lock file ... - got timeout
qmstart   | VM130 | can't lock file ... - got timeout
qmrestore | VM130 | can't lock file ... - got timeout
```

### Recovery

1. **Stop submitting operations.** Do NOT retry immediately — wait for the lock to clear.
2. Check lock status: `GET /config` → look for `lock` key
3. Wait 60-90 seconds, re-check
4. Once lock clears, submit a SINGLE operation
5. Verify it succeeded before proceeding

## Failure Mode 4: Boot failure after "successful" restore

### Symptoms

- VM starts (status: running) but shows no disk in dashboard
- At console: UEFI shell or "no bootable disk" message
- `uptime` stays at 0, `disk: 0`

### Diagnosis

1. Check config for `efidisk0` and `scsi1`:
```bash
curl -sk -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/qemu/{vmid}/config"
```
2. Verify `bios: ovmf` (UEFI) and `boot: order=scsi0;...` (disk first)
3. Check disk images exist:
```bash
curl -sk -H "Cookie: PVEAuthCookie=$TICKET" \
  "https://<proxmox_ip>:8006/api2/json/nodes/{node}/storage/local/content?content=images&vmid={vmid}"
```

### Common failure: Missing EFI System Partition

If `efidisk0` is present but no data disk (`scsi1`), or vice versa, the restore was incomplete. The backup may not have included all partitions. Resolution: re-restore from a different snapshot, or clone from a working VM.

## API Response Patterns

### HTTP 200 with valid config
```json
{"data": {"name": "MSSQL", "memory": "61440", "efidisk0": "local:129/...", "scsi1": "local:129/...", ...}}
```
→ VM exists and has real config. OK.

### HTTP 200 with skeleton config
```json
{"data": {"lock": "create", "memory": "128", "digest": "760bc3a1..."}}
```
→ Restore failed, zombie config remains. Wait for lock timeout, then delete.

### HTTP 500
→ VM config does not exist (deleted). This is success after deletion.
