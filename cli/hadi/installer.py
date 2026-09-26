"""
L'exécutable téléchargé depuis le tableau de bord est aussi l'installateur :
lancé sans argument (double-clic), il se copie dans un dossier stable,
s'ajoute au PATH de l'utilisateur, et signale s'il est déjà installé.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from hadi import __version__, session
from hadi.output import console
from hadi.settings import CONFIG_FILE

IS_WINDOWS = platform.system() == "Windows"
IS_FROZEN = bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / "hadi"
    return Path.home() / ".local" / "bin"


def installed_binary() -> Path:
    return install_dir() / ("hadi.exe" if IS_WINDOWS else "hadi")


def _installed_version(binary: Path) -> str | None:
    try:
        out = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=15).stdout
        return out.strip().split()[-1] if out.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def _user_path_contains(directory: Path) -> bool:
    """Dans le PATH courant, ou déjà enregistré pour les prochains terminaux (registre Windows)."""
    wanted = str(directory).lower()
    if wanted in [p.strip().lower() for p in os.environ.get("PATH", "").split(os.pathsep)]:
        return True
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                current, _ = winreg.QueryValueEx(key, "Path")
            return wanted in [p.strip().lower() for p in current.split(";")]
        except OSError:
            return False
    return False


def _add_to_user_path(directory: Path) -> bool:
    """Ajoute le dossier au PATH de l'utilisateur (registre sous Windows). True si modifié."""
    if not IS_WINDOWS:
        return False  # ~/.local/bin est déjà dans le PATH de la plupart des shells
    import ctypes
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            current, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, kind = "", winreg.REG_EXPAND_SZ
        parts = [p for p in current.split(";") if p]
        if str(directory).lower() in [p.lower() for p in parts]:
            return False
        winreg.SetValueEx(key, "Path", 0, kind, ";".join(parts + [str(directory)]))
    # Prévient l'Explorateur : les prochains terminaux voient le nouveau PATH.
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x0002, 5000, None)
    return True


def install(force: bool = False) -> None:
    if not IS_FROZEN:
        console.print("[yellow]Depuis les sources, installez avec : pip install ./cli[/yellow]")
        raise typer.Exit(code=1)
    source = Path(sys.executable).resolve()
    target = installed_binary()
    other = shutil.which("hadi")

    if target.exists():
        current = _installed_version(target)
        if source == target or (current == __version__ and not force):
            console.print(f"[bold green]hadi est déjà installé[/bold green] (version {current or '?'}) : {target}")
            if _user_path_contains(target.parent) or _add_to_user_path(target.parent):
                console.print("[dim]Si la commande hadi est introuvable, ouvrez un nouveau terminal.[/dim]")
            else:
                console.print(f"[yellow]Ajoutez {target.parent} à votre PATH.[/yellow]")
            return
        console.print(f"Version installée : {current or '?'}. Mise à jour vers {__version__}.")
    elif other:
        console.print(f"[yellow]Un autre hadi est déjà présent dans le PATH : {other}[/yellow]")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if not IS_WINDOWS:
        target.chmod(0o755)
    console.print(f"[bold green]Installé :[/bold green] {target}")
    if _add_to_user_path(target.parent):
        console.print("PATH mis à jour : ouvrez un nouveau terminal.")
    elif not _user_path_contains(target.parent):
        console.print(f"[yellow]Ajoutez {target.parent} à votre PATH pour lancer hadi depuis n'importe où.[/yellow]")
    console.print("Ensuite : [cyan]hadi config --api-url http://<hadi>/api[/cyan], puis [cyan]hadi login[/cyan].")


def uninstall() -> None:
    target = installed_binary()
    if not target.exists():
        console.print("[yellow]hadi n'est pas installé.[/yellow]")
        raise typer.Exit(code=1)
    if IS_WINDOWS and Path(sys.executable).resolve() == target:
        console.print("[yellow]Lancez la désinstallation depuis un autre emplacement : le fichier en cours d'exécution ne peut pas se supprimer lui-même.[/yellow]")
        raise typer.Exit(code=1)
    target.unlink()
    session.clear()
    CONFIG_FILE.unlink(missing_ok=True)
    console.print(f"[green]Désinstallé : {target}[/green]")


def launched_by_double_click() -> bool:
    """Windows : la console vient d'être créée pour ce seul process (double-clic), pas héritée d'un terminal."""
    if not IS_WINDOWS or not IS_FROZEN:
        return False
    try:
        import ctypes

        buffer = (ctypes.c_uint * 8)()
        count = ctypes.windll.kernel32.GetConsoleProcessList(buffer, 8)
        return count <= 2  # le bootloader PyInstaller et ce process
    except Exception:
        return False
