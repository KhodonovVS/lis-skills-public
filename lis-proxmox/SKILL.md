---
name: lis-proxmox
description: "Manage Proxmox VE: LXC containers and QEMU VMs via REST API — auth, lifecycle, networking, backup/restore, clone, and diagnosis."
version: 1.0.0
author: Hermes Agent (consolidated)
license: MIT
tags: [proxmox, lxc, qemu, vm, container, api, network, backup, restore]
---

# Proxmox Management — Consolidated

Unified skill for Proxmox VE operations: LXC containers and QEMU virtual machines via the REST API. Both share the same authentication pattern (ticket + CSRF token).

## Authentication (shared)

```bash
RESPONSE=$(curl -sk -X POST "https://<proxmox_ip>:8006/api2/json/access/ticket" \
  -d "username=root@pam&password=<password>")

TICKET=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['ticket'])")
CSRF=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['CSRFPreventionToken'])")
```

All subsequent API calls need:
```
Cookie: PVEAuthCookie=$TICKET
CSRFPreventionToken: $CSRF
```

Use `-k` (insecure TLS) — Proxmox uses self-signed certificates. Tickets expire after ~2 hours.

## Quick-Reference

| Task | Section |
|------|---------|
| LXC containers: create, start/stop, network config, pct exec/push, SSH passthrough, docker restart inside | See `references/lxc-management.md` |
| QEMU VMs: create, start/stop, backup/restore from PBS, clone, lock handling, boot diagnosis | See `references/qemu-management.md` |
| Multi-node clusters: find VMs across nodes, storage management, NFS setup | Covered in both references |

## Checking LXC Network Interfaces After Reboot

When an LXC container uses DHCP (`ip=dhcp` in net0 config), its IP address may change after reboot. To discover the new IP:

```python
import json, urllib.request, urllib.parse, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Authenticate
auth = urllib.parse.urlencode({"username": "root@pam", "password": "<pass>"}).encode()
req = urllib.request.Request("https://<proxmox>:8006/api2/json/access/ticket", data=auth, method="POST")
with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
    result = json.loads(r.read().decode())

headers = {"Cookie": f"PVEAuthCookie={result['data']['ticket']}"}

# Get interfaces
req2 = urllib.request.Request(
    f"https://<proxmox>:8006/api2/json/nodes/<node>/lxc/<ctid>/interfaces",
    headers=headers
)
with urllib.request.urlopen(req2, context=ctx, timeout=10) as r:
    interfaces = json.loads(r.read().decode()).get("data", [])

for iface in interfaces:
    for addr in iface.get("ip-addresses", []):
        print(f"{iface['name']}: {addr['ip-address-type']}:{addr['ip-address']}")
```

Look for the `eth0` interface with `inet` type — that's the container's IPv4. If only `lo` (<адрес из окружения>) and `eth0` with only `inet6:fe80::` (link-local) are present, the DHCP lease failed — the container needs manual network fix on the Proxmox host.

**Pitfall**: DHCP-assigned LXC containers can get a different IP after every reboot. Proxmox's `pve-firewall` or router lease table may vary. Always verify the actual IP via the interfaces endpoint after restarting a DHCP-configured container.

## Running Commands Inside LXC Containers

The Proxmox REST API does NOT support the `/nodes/{node}/lxc/{vmid}/exec` endpoint (returns HTTP 501). The only way to run arbitrary commands inside a running LXC is:

### Via SSH to Proxmox host + `lxc-attach`

```bash
# SSH to Proxmox host first
sshpass -f /tmp/ct_pw.txt ssh root@<proxmox_ip> "lxc-attach <vmid> -- <command>"

# Examples:
# Restart a Docker container inside CT 127
lxc-attach 127 -- docker restart hermes-llm

# Check Docker containers inside CT
lxc-attach 127 -- docker ps -a

# Check if a specific port is listening inside CT
lxc-attach 127 -- ss -tlnp
```

**Prerequisites:**
- SSH access to Proxmox host must work (password or key)
- The CT must be running
- Use `sshpass` (install: `apt-get install sshpass`) or SSH keys
- Proxmox root password is stored in Qdrant (search "Proxmox pve credentials")

**Why not `pct enter` or API?**
- The Proxmox API `exec` endpoint is not implemented for LXC
- `pct enter` is interactive only (no non-interactive mode)
- `vncproxy`/`termproxy` returns a VNC WebSocket, not a command pipe
- SSH + `lxc-attach` is the only non-interactive way to run commands inside LXC

## `pct mount` и mount points: данные чистить ТОЛЬКО по raw-путям

У остановленного CT `pct mount <id>` подмонтирует и mp-точки (bind) ПОВЕРХ rootfs. Поэтому:

- `rm -rf .../rootfs/<путь mp>/*` при этом чистит содержимое **датасета**, а не «старую копию в rootfs» — проверено: так снесло свежую копию данных qdrant; спасла вторая копия в raw-subvol.
- Для операций с данными сервиса использовать RAW-пути датасетов (`/pool/subvol-<id>-disk-0/...`), а не `pct mount`, когда у CT есть mp в тот же каталог.
- Перед любым `rm` в таких местах — `findmnt <путь>`: убедиться, что удаляется именно то, что думаешь.
- Безопасный порядок переноса данных сервиса на отдельный датасет: CT stopped → копия rsync по raw-путям → сверка (bytes/files/`rsync -ani`=0) → прописать mp → старт → проверка API/сервиса → и только потом удаление старой копии (raw-путь, после проверки).

## Миграции дисков VM/CT — проверенные рецепты (30.09.2026)

**Live-move VM-диска (без остановки гостя, PVE зеркалит фоном):**
`qm disk move <vmid> <disk> <target-storage> --delete 1` — гость работает; в конце пауза 1–2 с (для сетевых VM/шлюзов — предупредить). Скорость на локальных SSD: 30–36 ГиБ ≈ 50 с.
**`--delete 0` = источник остаётся (безопасный дефолт); `--delete 1` удаляет источник ТОЛЬКО после успешного копирования.**

**Перенос rootfs КОНТЕЙНЕРА на другой storage:** `pct move-volume <ctid> rootfs <storage> --delete 1` — но, в отличие от VM-диска, rootfs CT переносится только на остановленном контейнере: `pct stop <ctid> --skiplock` → `pct move-volume …` → `pct start <ctid>`. Скорость на локальных SSD/NVMe ~130 МБ/с (22 ГБ ≈ 3 мин). После старта сервис с большим индексом/базой поднимается 60–90 с (читает данные с диска) и всё это время порт не слушается — готовность брать по строке в журнале сервиса, а не по первому curl (иначе легко принять норму за поломку).

**Грабли нумерации дисков:** `qm list` колонка BOOTDISK показывает первый диск по boot-order (может быть CD-ROM/ISO!) — реальные диски смотреть `qm config <id> | grep -E '^(ide|scsi|virtio|sata|efidisk|tpmstate)[0-9]+:'`; регекс БЕЗ `[0-9]+` не поймает `ide1:` (grep `^(...|ide|...):` = ложная пустота).
**`unusedN:`** в конфиге = отвязанный диск с недоступного стораджа — не мешает, разобрать отдельно.

**Переименование стораджей PVE БЕЗ простоя гостей** (LXCCONT→CTPOOL и т.п.): править `/etc/pve/storage.cfg` — ТОЛЬКО строку-заголовок `zfspool: <id>` (строку `pool <zfs-pool>` не трогать), сэдом переписать ссылки `<id>:` → `<new-id>:` во ВСЕХ `/etc/pve/lxc/*.conf` и `/etc/pve/qemu-server/*.conf`. Окно несоответствия ~секунды: НЕ запускать во время qm/pct-операций. Работающие гости конфиг не перечитывают; после — проверить стартом одного stopped CT и stopped VM. Бэкап: `cp -a /etc/pve/lxc /etc/pve/qemu-server /etc/pve/storage.cfg /root/pve-conf-bak-<TS>/`. **ZFS-имена пулов так не меняются:** `zpool export/import <old> <new>` требует остановки ВСЕХ гостей пула (если на пуле хост самого оператора — остановишь себя) — только отдельным окном с консоли.

## ⚠️ ZFS zvol-резервации: `zpool free` ≠ реально доступно (avail)

Перед любым планированием места на ZFS-пулах смотри `zfs list -o name,used,avail` и `zfs get refreservation -r <pool>`, а НЕ `zpool list` / «свободно» из `pvesm status`:
- «Толстые» zvol (refreservation = volsize; дефолт PVE для VM-дисков при `sparse 0`) **резервируют полный объём** из пула: `zpool free` показывает его свободным, а `zfs avail` — уже нет. PVE распределяет место по avail.
- Реальный кейс (30.09.2026): пул LXCCONT показывал «185G свободно», фактически avail = **15.5G** (резервации vm-100 102G + vm-112 163G) — 58 CT упёрлись в потолок; APPSTORE «597G» против avail 276G (vm-159 559G).
- Лечение (мгновенно, обратимо, данные не двигаются): `zfs set refreservation=none <pool>/<zvol>` — вернуло +170G и +290G. Перед снятием зафиксировать: `zfs get refreservation <zvol> | tee /root/refreservation.before.txt`.
- Всегда сверять оба числа, прежде чем утверждать «места хватает» — иначе план/миграция строится на ложной цифре.

## Порядок запуска CT/VM при старте узла (порциями)

Штатный механизм: `startup: [[order=]N][,up=S][,down=S]` в конфиге гостя (`man pct.conf`). `order` — неотрицательное число, задаёт очередь; **гости с одинаковым `order` стартуют параллельно**, а `up` — пауза после порций перед следующей; выключение идёт в обратном порядке.

```bash
pct set <ctid> --startup order=60,up=45      # контейнер
qm  set <vmid> --startup order=10,up=40      # виртуалка
```

Изменение применяется к конфигу сразу, перезапускать гостя не нужно. Действует только при `onboot: 1`.

**Аудит перед назначением — кто вообще не встанет:**

```bash
for id in $(pct list | awk 'NR>1{print $1}'); do c=$(pct config $id);
  echo "$c" | grep -q 'onboot: 1' || continue
  echo "$c" | grep -q '^startup:' || echo "CT$id без startup"
done
```

Свежесозданный CT легко остаётся без `onboot`/`startup` и после ребута просто не поднимается — проверять оба флага.

**Порядок строить по фактическим зависимостям, а не по номерам ID.** Рабочая раскладка для домашней инфраструктуры (проверена на 95 объектах):

| order | что | пауза |
|---|---|---|
| 10 | шлюз/фаервол (VM с OPNsense) | 40 с — должен поднять маршруты |
| 20 | DNS (PDC, DoH-прокси) + маршрутные агенты (BIRD) | 25 с — без DNS гости висят в таймаутах |
| 30 | VPN-выход, reverse-proxy (NPM), панель управления | 25 с |
| 40 | SSO, почта, хранилище паролей, git | 30 с |
| 50 | БД и стенды (clickhouse, postgres-кластеры) | 20 с |
| 60 | LLM-слой: vLLM, llama-swap, gateway, router, embeddings | 45 с — модели грузятся долго |
| 70 | агентские контейнеры | 20 с |
| 80 | прикладные сервисы (web-UI, трекеры задач, автоматизации) | 30 с |
| 90 | медиа и загрузки — пик I/O по дискам | 35 с |
| 100 | MQTT → zigbee → видеодетекция (строго цепочкой) | 20 с |
| 110 | второстепенное (CI, песочницы, OCR, фото) | 15 с |
| 120 | прочие VM | 0 |

Правила, из которых сложилась схема:
- **Приложения зависят от LLM-слоя, а не наоборот:** web-UI и агенты при старте дёргают gateway — если он позже, они уходят в ретраи на минуты.
- **Медиа отдельно от БД:** Plex/*arr/торренты дают пик I/O; ставить их в одну порцию с базами — гарантированные таймауты.
- **Цепочки внутри порции запрещены:** если сервис A нужен сервису B (брокер → zigbee → детектор), это разные `order`, иначе B стартует раньше A в случайном порядке.
- Порции по 5–30 штук: мельче — старт растягивается, крупнее — пик по CPU/диску.

Готовый применятор схемы — `scripts/pve_startup_order.py` (таблица `order → (пауза, [id])`, применяет через `pct set`/`qm set` и печатает разбивку).

## BOSS Infrastructure (as of June 2026)

- **pve** (<адрес из окружения>) — primary management node
- **dbase** (<адрес из окружения>) — second node, hosts VMs 129 (MSSQL) and 130 (ORAWIN)
- Storage: `local` (node-local), `LXCCONT` (ZFS pool for LXC), `pbs-main` (Proxmox Backup Server)

## Reference Files

- `references/lxc-management.md` — LXC container lifecycle, creation from templates, network config (DHCP/static), pct operations, post-creation SSH setup
- `references/qemu-management.md` — QEMU VM lifecycle, PBS backup/restore, cloning, lock contention resolution, disk inspection, boot failure diagnosis
- `references/lxc-creation-example.md` — Real-world example: creating CT 138 (Sonarr dev)
- `references/pbs-restore-failures.md` — PBS restore failure diagnosis and zombie config cleanup
- `references/docker-lxc-install.md` — Installing Docker-based applications inside LXC (bypassing TTY-dependent community scripts, storage selection, pct create + Docker run pattern)
- `references/llm-container-management.md` — Managing the Gemma 4 31B LLM server container inside CT 127 (restart, monitor, failure modes)
