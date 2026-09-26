"""
Exécutables de la CLI produits sur ce serveur : quelle plateforme, quel
fichier, et son empreinte.

Les binaires ne sont pas versionnés dans le dépôt : ils se produisent avec
`make cli-binary` sur chaque plateforme visée (PyInstaller ne croise pas les
compilations). Ce module est le seul à connaître leurs noms.
"""
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: Où chercher les exécutables produits. Par défaut le dossier du dépôt ;
#: dans l'image, seul `orchestrator_api/` est copié, donc ce chemin n'existe
#: pas : HADI_CLI_DIST_DIR permet de monter un volume qui les contient
#: (voir README). Sans binaire, l'API répond 404 en renvoyant vers `pip install`.
_DIST_DIR = Path(os.getenv("HADI_CLI_DIST_DIR") or Path(__file__).resolve().parents[3] / "cli" / "dist")

#: Artefacts reconnus, par plateforme.
ARTIFACTS: dict[str, str] = {
    "windows": "hadi-windows.exe",
    "linux": "hadi-linux",
    "darwin": "hadi-macos",
}

#: Noms antérieurs, acceptés pour ne pas casser une installation où le
#: binaire a déjà été produit.
_LEGACY: dict[str, list[str]] = {
    "windows": ["orchestrator-cli-windows.exe", "orchestrator-cli.exe"],
    "linux": ["orchestrator-cli-linux"],
    "darwin": ["orchestrator-cli-macos"],
}

#: Nom du fichier tel que l'utilisateur le reçoit : la commande s'appelle hadi.
DOWNLOAD_NAME = {"windows": "hadi.exe", "linux": "hadi", "darwin": "hadi"}

#: Commande de vérification à afficher à l'utilisateur, par plateforme.
CHECK_COMMAND = {
    "windows": r"Get-FileHash .\hadi.exe -Algorithm SHA256",
    "linux": "sha256sum hadi",
    "darwin": "shasum -a 256 hadi",
}


@dataclass(frozen=True)
class Artifact:
    target: str
    path: Path
    size: int
    modified: datetime
    sha256: str

    @property
    def download_name(self) -> str:
        return DOWNLOAD_NAME[self.target]


def normalise(value: str) -> str:
    """Ramène un identifiant de plateforme à l'une des clés d'`ARTIFACTS`."""
    value = value.strip().lower()
    if value in {"win", "win32", "win64", "windows"}:
        return "windows"
    if value in {"mac", "macos", "osx", "darwin"}:
        return "darwin"
    if value == "linux":
        return "linux"
    return value


def _locate(target: str) -> Path | None:
    for name in [ARTIFACTS[target], *_LEGACY.get(target, [])] if target in ARTIFACTS else []:
        # Le nom vient d'une table interne, jamais de l'appelant : aucun
        # segment de chemin ne peut être injecté ici.
        candidate = _DIST_DIR / name
        if candidate.is_file():
            return candidate
    return None


#: Empreintes déjà calculées, indexées par (chemin, taille, date de modification) :
#: un binaire reconstruit change de clé, donc d'empreinte, sans invalidation à gérer.
_digests: dict[tuple[str, int, float], str] = {}


def _sha256(path: Path, stat) -> str:
    key = (str(path), stat.st_size, stat.st_mtime)
    if key not in _digests:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        _digests[key] = digest.hexdigest()
    return _digests[key]


def find(target: str) -> Artifact | None:
    """Artefact disponible pour cette plateforme, empreinte comprise, ou None."""
    path = _locate(target)
    if path is None:
        return None
    stat = path.stat()
    return Artifact(
        target=target,
        path=path,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        sha256=_sha256(path, stat),
    )
