# LXC Creation Example — CT 138 sonar-dev

Full real-world example from session: creating a development container for Sonarr.

## Environment

- Proxmox: <адрес из окружения>
- Node: pve
- Template storage: TEMPLATES (dir type)
- RootFS storage: LXCCONT (zfspool)
- Network bridge: vmbr0 (DHCP, <адрес из окружения>/20)

## Template Selection

```bash
# Available templates
sshpass -p '4977860VXss' ssh root@<адрес из окружения> "pveam available --section system | grep ubuntu"
# Output: ubuntu-22.04, ubuntu-24.04, ubuntu-25.04, ubuntu-26.04

# Download template if not cached
sshpass -p '4977860VXss' ssh root@<адрес из окружения> "pveam download TEMPLATES ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
```

## Creation Payload

```json
{
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
}
```

## Result

| Field | Value |
|-------|-------|
| CT ID | 138 |
| Hostname | sonar-dev |
| IP | <адрес из окружения> (DHCP) |
| OS | Ubuntu 24.04 LTS |
| Password | sonar2024 |

## Post-Creation: SSH Fix

```bash
# PermitRootLogin was prohibit-password → had to enable yes
sshpass -p '4977860VXss' ssh root@<адрес из окружения> "pct exec 138 -- bash -c '
  sed -i \"s/#PermitRootLogin prohibit-password/PermitRootLogin yes/\" /etc/ssh/sshd_config
  systemctl restart sshd
'"
```

## Software Stack Installed

```bash
# .NET SDK 8.0 (for Sonarr backend)
wget -q https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb
dpkg -i packages-microsoft-prod.deb
apt-get update && apt-get install -y dotnet-sdk-8.0

# Node.js 20 (for Sonarr frontend)
HTTP-запрос к -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Git
apt-get install -y git
```
