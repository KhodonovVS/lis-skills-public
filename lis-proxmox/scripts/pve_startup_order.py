#!/usr/bin/env python3
"""Применяет порядок запуска CT/VM порциями на узле Proxmox (startup order).

Использование: отредактировать PLAN под свой узел и запустить.
Пароль root pve — из ~/.secrets/pve_pass (или переменная PVE_PASS).

Каждая запись: order -> (пауза up в секундах, ["ct105", "vm135", ...]).
Гости с одинаковым order стартуют параллельно, пауза действует между порциями.
"""
import os
import subprocess

PVE = os.environ.get("PVE_HOST", "root@10.0.1.3")
PW_FILE = os.path.expanduser("~/.secrets/pve_pass")

PLAN = {
    10: (40, ["vm135"]),                                    # шлюз
    20: (25, ["vm100", "ct150", "ct122", "ct160"]),        # DNS + маршруты
    30: (25, ["ct144", "ct105", "ct121", "vm112"]),        # VPN, reverse-proxy, панель
    40: (30, ["ct203", "ct204", "ct164", "ct165"]),        # SSO, почта, пароли, git
    50: (20, ["ct152", "ct166", "ct301", "ct302", "ct303"]),  # БД
    60: (45, ["ct109", "ct124", "ct127", "ct232", "ct233"]),  # LLM-слой
    80: (30, ["ct113", "ct174", "ct141", "ct162"]),        # сервисы
    90: (35, ["ct102", "ct110", "ct111", "ct108", "ct216"]),  # медиа
    100: (20, ["ct103", "ct206", "ct161"]),                # MQTT -> zigbee -> детекция
    110: (15, ["ct106", "ct171", "ct200"]),                # прочее
}


def sh(cmd: str) -> str:
    pw = os.environ.get("PVE_PASS") or open(PW_FILE).read().strip()
    p = subprocess.run(
        ["sshpass", "-p", pw, "ssh", "-o", "StrictHostKeyChecking=no", PVE, cmd],
        capture_output=True, text=True, timeout=900,
    )
    return (p.stdout + p.stderr).strip()


def main():
    cmds = []
    for order, (up, ids) in sorted(PLAN.items()):
        for ident in ids:
            tool = "qm" if ident.startswith("vm") else "pct"
            num = int(ident[2:])
            cmds.append(
                f"{tool} set {num} --startup order={order},up={up} >/dev/null 2>&1 "
                f"&& echo ok-{ident} || echo FAIL-{ident}"
            )
    out = sh("; ".join(cmds))
    fails = [l for l in out.splitlines() if l.startswith("FAIL")]
    oks = [l for l in out.splitlines() if l.startswith("ok-")]
    print(f"применено: {len(oks)} | ошибок: {len(fails)}")
    for f in fails:
        print(" ", f)
    print("\nаудит (гости с onboot, но без startup):")
    print(sh(
        "miss=''; for id in $(pct list | awk 'NR>1{print $1}'); do c=$(pct config $id); "
        "echo \"$c\" | grep -q 'onboot: 1' || continue; "
        "echo \"$c\" | grep -q '^startup:' || miss=\"$miss $id\"; done; "
        "echo \"CT:${miss:- нет}\""
    ))


if __name__ == "__main__":
    main()
