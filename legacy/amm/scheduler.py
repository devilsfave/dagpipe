"""AMM Phase 5 — Cross-Platform Scheduler

Abstracts daemon registration behind a portable interface.
Windows (dev): schtasks
Linux (VPS): systemd unit files or cron

Usage:
    from amm.scheduler import get_scheduler
    sched = get_scheduler()
    sched.register_daemon("gemini_bot", "python gemini_bot.py")
    sched.list_daemons()
"""
import platform
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from .config import AMM_WORKSPACE


# ─────────────────────────────────────────────────────────────────────────────
# ABSTRACT INTERFACE
# ─────────────────────────────────────────────────────────────────────────────

class SchedulerBackend(ABC):
    """Abstract interface for OS-level daemon scheduling."""

    @abstractmethod
    def register_daemon(self, name: str, command: str, on_boot: bool = True) -> bool:
        """Register a command as a persistent daemon.

        Args:
            name: Daemon identifier (e.g. "AMM_GeminiBot").
            command: Full command to run (e.g. "python gemini_bot.py").
            on_boot: If True, starts on system boot.

        Returns:
            True if registration succeeded.
        """
        ...

    @abstractmethod
    def unregister_daemon(self, name: str) -> bool:
        """Remove a registered daemon."""
        ...

    @abstractmethod
    def list_daemons(self) -> list[dict]:
        """List registered AMM daemons. Returns [{name, command, status}]."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# WINDOWS BACKEND — schtasks
# ─────────────────────────────────────────────────────────────────────────────

class WindowsSchedulerBackend(SchedulerBackend):
    """Windows Task Scheduler via schtasks."""

    def register_daemon(self, name: str, command: str, on_boot: bool = True) -> bool:
        task_name = f"AMM_{name}"
        schedule = "onstart" if on_boot else "once"
        cmd = [
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", command,
            "/sc", schedule,
            "/ru", "SYSTEM",
            "/f",  # Force overwrite
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print(f"   ✓ Registered Windows Task: {task_name}")
                return True
            print(f"   ⚠️ schtasks failed: {result.stderr.strip()}")
            return False
        except Exception as e:
            print(f"   ⚠️ schtasks error: {e}")
            return False

    def unregister_daemon(self, name: str) -> bool:
        task_name = f"AMM_{name}"
        try:
            result = subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True, text=True, timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False

    def list_daemons(self) -> list[dict]:
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/fo", "CSV", "/nh"],
                capture_output=True, text=True, timeout=30,
            )
            daemons = []
            for line in result.stdout.strip().split("\n"):
                if "AMM_" in line:
                    parts = line.strip('"').split('","')
                    if len(parts) >= 3:
                        daemons.append({
                            "name": parts[0].replace('"', ''),
                            "status": parts[2].replace('"', '') if len(parts) > 2 else "unknown",
                        })
            return daemons
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# LINUX BACKEND — systemd unit files
# ─────────────────────────────────────────────────────────────────────────────

class LinuxSchedulerBackend(SchedulerBackend):
    """Linux systemd user service backend."""

    UNIT_DIR = Path.home() / ".config" / "systemd" / "user"

    def register_daemon(self, name: str, command: str, on_boot: bool = True) -> bool:
        service_name = f"amm-{name}"
        unit_content = f"""[Unit]
Description=AMM {name}
After=network.target

[Service]
Type=simple
ExecStart={command}
WorkingDirectory={AMM_WORKSPACE}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
        try:
            self.UNIT_DIR.mkdir(parents=True, exist_ok=True)
            unit_path = self.UNIT_DIR / f"{service_name}.service"
            unit_path.write_text(unit_content, encoding="utf-8")

            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=30)
            subprocess.run(["systemctl", "--user", "enable", service_name], check=True, timeout=30)
            if on_boot:
                subprocess.run(["systemctl", "--user", "start", service_name], timeout=30)
            print(f"   ✓ Registered systemd service: {service_name}")
            return True
        except Exception as e:
            print(f"   ⚠️ systemd registration failed: {e}")
            return False

    def unregister_daemon(self, name: str) -> bool:
        service_name = f"amm-{name}"
        try:
            subprocess.run(["systemctl", "--user", "stop", service_name], timeout=30)
            subprocess.run(["systemctl", "--user", "disable", service_name], timeout=30)
            unit_path = self.UNIT_DIR / f"{service_name}.service"
            if unit_path.exists():
                unit_path.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=30)
            return True
        except Exception:
            return False

    def list_daemons(self) -> list[dict]:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "list-units", "--type=service",
                 "--no-legend", "--no-pager"],
                capture_output=True, text=True, timeout=30,
            )
            daemons = []
            for line in result.stdout.strip().split("\n"):
                if "amm-" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        daemons.append({
                            "name": parts[0].replace(".service", ""),
                            "status": parts[3] if len(parts) > 3 else "unknown",
                        })
            return daemons
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def get_scheduler() -> SchedulerBackend:
    """Auto-detect OS and return the appropriate scheduler backend."""
    system = platform.system().lower()
    if system == "windows":
        return WindowsSchedulerBackend()
    elif system == "linux":
        return LinuxSchedulerBackend()
    else:
        print(f"[SCHEDULER] Unsupported OS: {system} — using Linux backend as fallback")
        return LinuxSchedulerBackend()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AMM Scheduler")
    sub = parser.add_subparsers(dest="action")

    reg = sub.add_parser("register", help="Register a daemon")
    reg.add_argument("name", help="Daemon name (e.g. gemini_bot)")
    reg.add_argument("command", help="Command to run")

    unreg = sub.add_parser("unregister", help="Remove a daemon")
    unreg.add_argument("name", help="Daemon name")

    sub.add_parser("list", help="List registered AMM daemons")

    args = parser.parse_args()
    sched = get_scheduler()

    if args.action == "register":
        sched.register_daemon(args.name, args.command)
    elif args.action == "unregister":
        sched.unregister_daemon(args.name)
    elif args.action == "list":
        for d in sched.list_daemons():
            print(f"  {d['name']}: {d.get('status', '?')}")
    else:
        parser.print_help()
