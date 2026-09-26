"""
Téléchargement de l'exécutable hadi pour la plateforme de l'appelant, et son
empreinte SHA-256 pour la vérifier avant de l'exécuter. La voie universelle
reste `pip install ./cli`.
"""
import platform
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.deps import get_current_user
from app.models.user import User
from app.services.cli_artifacts import ARTIFACTS, CHECK_COMMAND, Artifact, find, normalise

router = APIRouter()

_MISSING_BINARY = (
    "Aucun exécutable {target} n'a été produit sur ce serveur. "
    "Installez la CLI avec `pip install ./cli` (fonctionne sur toutes les "
    "plateformes), ou lancez `make cli-binary` pour générer le binaire."
)


def _requested(os_name: str | None) -> Artifact:
    if os_name is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", os_name):
        raise HTTPException(status_code=400, detail="Plateforme invalide.")

    target = normalise(os_name) if os_name else normalise(platform.system())
    if target not in ARTIFACTS:
        raise HTTPException(status_code=400, detail=f"Plateforme inconnue : {os_name!r}. Attendu : windows, linux ou macos.")

    artifact = find(target)
    if artifact is None:
        raise HTTPException(status_code=404, detail=_MISSING_BINARY.format(target=target))
    return artifact


_OS_QUERY = Query(default=None, alias="os", description="windows | linux | macos. Par défaut, la plateforme du serveur.")


@router.get("/download")
def download_cli(os_name: str | None = _OS_QUERY, _: User = Depends(get_current_user)):
    """
    Sert l'exécutable autonome correspondant à la plateforme demandée.

    L'empreinte accompagne le fichier (`X-Checksum-Sha256`) : le même
    condensat que /checksum, sur l'octet près de ce qui est servi.
    """
    artifact = _requested(os_name)
    # Sans directive, le navigateur applique une fraîcheur heuristique et
    # ressert l'exécutable précédent après une reconstruction.
    return FileResponse(
        artifact.path,
        media_type="application/octet-stream",
        filename=artifact.download_name,
        headers={"Cache-Control": "no-store", "X-Checksum-Sha256": artifact.sha256},
    )


@router.get("/checksum")
def cli_checksum(os_name: str | None = _OS_QUERY, _: User = Depends(get_current_user)):
    """
    Empreinte de l'exécutable servi, à comparer après téléchargement : c'est
    ce qui distingue le binaire produit par cette instance d'un fichier
    substitué en chemin. La commande à taper est donnée avec.
    """
    artifact = _requested(os_name)
    return {
        "os": artifact.target,
        "filename": artifact.download_name,
        "sha256": artifact.sha256,
        "size": artifact.size,
        "modified": artifact.modified,
        "command": CHECK_COMMAND[artifact.target],
    }
