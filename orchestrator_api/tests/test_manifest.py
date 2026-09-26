import pytest

from app.domain.manifest import ManifestError, pin_image

MANIFEST = """\
spec:
  containers:
    - name: demo
      # À ADAPTER : préfixez par votre registre
      image: registry.exemple.org/org/demo:RELEASE_TAG
      imagePullPolicy: IfNotPresent
    - name: sidecar
      image: 'nginx:1.27'
"""


def test_remplace_le_tag_de_la_bonne_image_seulement():
    out = pin_image(MANIFEST, "demo", "abc123")
    assert "image: registry.exemple.org/org/demo:abc123" in out
    assert "image: 'nginx:1.27'" in out


def test_accepte_un_nom_avec_proprietaire():
    out = pin_image(MANIFEST, "org/demo", "abc123")
    assert "org/demo:abc123" in out


def test_remplace_un_sha_deja_epingle():
    once = pin_image(MANIFEST, "demo", "aaa")
    twice = pin_image(once, "demo", "bbb")
    assert "demo:bbb" in twice and "demo:aaa" not in twice


def test_idempotent():
    once = pin_image(MANIFEST, "demo", "abc")
    assert pin_image(once, "demo", "abc") == once


def test_garde_commentaires_et_indentation():
    out = pin_image(MANIFEST, "demo", "abc")
    assert "# À ADAPTER : préfixez par votre registre" in out
    assert out.count("\n") == MANIFEST.count("\n")


def test_registre_avec_port():
    m = "image: localhost:3000/didier/demo:RELEASE_TAG\n"
    assert pin_image(m, "demo", "x") == "image: localhost:3000/didier/demo:x\n"


def test_digest_remplace_par_le_tag():
    m = "image: org/demo@sha256:deadbeef\n"
    assert pin_image(m, "demo", "x") == "image: org/demo:x\n"


def test_ne_confond_pas_un_suffixe():
    m = "image: org/notdemo:RELEASE_TAG\n"
    with pytest.raises(ManifestError):
        pin_image(m, "demo", "x")


def test_echoue_sans_ligne_image():
    with pytest.raises(ManifestError):
        pin_image("kind: Service\n", "demo", "x")
