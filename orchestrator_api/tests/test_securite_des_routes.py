"""Toute route non explicitement publique exige une identité."""
import inspect

#: Routes publiques par nécessité : amorçage, connexion, sondes, webhooks
#: (authentifiés par signature HMAC, pas par session).
PUBLIQUES = {
    "/api/health",
    "/api/health/live",
    "/api/auth/login",
    "/api/auth/session-policy",
    "/api/setup/status",
    "/api/setup/database",
    "/api/setup/integrations",
    "/api/setup/integrations/test/{tool}",
    "/api/setup/complete",
    "/api/webhooks/{provider}",
}

GARDES = ("get_current_user", "require_roles", "get_authenticated_identity", "require_password_confirmation")


def _protegee(route) -> bool:
    try:
        signature = str(inspect.signature(route.endpoint))
    except (TypeError, ValueError):
        signature = ""
    if any(garde in signature for garde in GARDES):
        return True
    dependances = getattr(getattr(route, "dependant", None), "dependencies", []) or []
    return any(garde in str(d.call) for d in dependances for garde in GARDES)


def test_aucune_route_n_est_ouverte_par_inadvertance():
    from app.main import app

    ouvertes = [
        f"{sorted(route.methods or [])} {chemin}"
        for route in app.routes
        if (chemin := getattr(route, "path", "")).startswith("/api")
        and chemin not in PUBLIQUES
        and not _protegee(route)
    ]
    assert not ouvertes, f"routes sans authentification : {ouvertes}"


def test_les_routes_d_installation_exigent_le_jeton():
    from app.main import app

    sans_jeton = []
    for route in app.routes:
        chemin = getattr(route, "path", "")
        if not chemin.startswith("/api/setup/") or chemin == "/api/setup/status":
            continue
        dependances = getattr(getattr(route, "dependant", None), "dependencies", []) or []
        if not any("require_setup_token" in str(d.call) for d in dependances):
            sans_jeton.append(chemin)
    assert not sans_jeton, f"routes d'installation sans jeton : {sans_jeton}"
