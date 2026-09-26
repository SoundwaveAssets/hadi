"""
Épinglage du tag d'image dans un manifeste Kubernetes.

C'est l'écriture GitOps du déploiement : après une décision favorable,
l'Orchestrateur remplace le tag de l'image (RELEASE_TAG à la première fois,
le SHA précédent ensuite) par le SHA du commit approuvé, puis commite le
manifeste. Argo CD voit un vrai diff et déploie cette image précise, pas un
tag mobile.

Pure fonction sur du texte : on ne parse pas le YAML pour ne pas réécrire
les commentaires et l'indentation du fichier de l'équipe. Seules les lignes
`image:` dont la référence désigne cette image sont touchées.
"""
from __future__ import annotations

import re

_IMAGE_LINE = re.compile(r"^(?P<indent>\s*-?\s*image:\s*)(?P<ref>[^\s#]+)(?P<rest>.*)$")


class ManifestError(ValueError):
    """Le manifeste ne contient aucune ligne `image:` pour cette image."""


def _same_image(ref: str, image: str) -> bool:
    # ref = [registre/][propriétaire/]nom[:tag][@digest]
    name = ref.split("@", 1)[0]
    last_slash = name.rfind("/")
    if ":" in name[last_slash + 1 :]:
        name = name[: name.rfind(":")]
    return name == image or name.endswith("/" + image)


def pin_image(manifest: str, image: str, tag: str) -> str:
    """
    Renvoie le manifeste avec `image` épinglée sur `tag`. Lève ManifestError
    si aucune ligne ne référence cette image : déployer sans avoir rien
    changé serait exactement le faux DEPLOYED que ce module existe pour
    empêcher.
    """
    if not image or not tag:
        raise ValueError("image et tag sont requis")
    lines = manifest.split("\n")
    touched = 0
    for i, line in enumerate(lines):
        m = _IMAGE_LINE.match(line)
        if not m:
            continue
        ref = m.group("ref").strip("\"'")
        if not _same_image(ref, image):
            continue
        base = ref.split("@", 1)[0]
        last_slash = base.rfind("/")
        if ":" in base[last_slash + 1 :]:
            base = base[: base.rfind(":")]
        lines[i] = f"{m.group('indent')}{base}:{tag}{m.group('rest')}"
        touched += 1
    if touched == 0:
        raise ManifestError(f"aucune ligne image: pour '{image}' dans le manifeste")
    return "\n".join(lines)
