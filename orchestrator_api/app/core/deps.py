from datetime import datetime, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import API_TOKEN_PREFIX, decode_access_token, hash_api_token, verify_password
from app.models.user import User, UserRole

# tokenUrl sert uniquement à la doc OpenAPI (bouton "Authorize") ; le vrai
# endpoint de login est /api/auth/login.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

#: Préfixe du nom d'utilisateur synthétique porté par un jeton API (voir
#: _authenticate_api_token) : ce qui permet aux routes de gouvernance de les
#: reconnaître et de les refuser.
API_TOKEN_PREFIX_IDENTITY = "jeton:"


def get_authenticated_identity(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_session),
) -> User:
    """
    Résout l'identité derrière un jeton, SANS appliquer la contrainte de
    changement de mot de passe.

    Réservé aux deux routes qui doivent rester joignables pendant cette
    contrainte (`GET /auth/me` et `POST /auth/change-password`) : tout le reste
    de l'API passe par `get_current_user`, qui l'applique. Le défaut est donc
    sûr, et l'exception est explicite, l'inverse d'une vérification qu'on
    oublie d'ajouter sur une nouvelle route.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides ou session expirée.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    # Module Jetons API (désactivé par défaut) : un jeton de compte de
    # service se reconnaît à son préfixe fixe, jamais présent dans un JWT
    # de session (structure base64.base64.base64), pas d'ambiguïté possible
    # entre les deux formats.
    if token.startswith(API_TOKEN_PREFIX):
        return _authenticate_api_token(token, db, credentials_error)

    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as e:
        raise credentials_error from e

    username = payload.get("sub")
    user = db.exec(select(User).where(User.username == username)).first()
    if not user or not user.is_active:
        raise credentials_error
    return user


def get_current_user(user: User = Depends(get_authenticated_identity)) -> User:
    """
    Identité + contrainte de changement de mot de passe. C'est la dépendance
    par défaut de toute route authentifiée.

    Vérifié côté serveur, pas seulement dans l'interface : sinon curl, la CLI
    ou un script se connecterait avec admin/admin et disposerait de toutes les
    routes d'administration.
    """
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mot de passe par défaut encore actif : changez-le via POST /api/auth/change-password "
            "avant d'utiliser le reste de l'API.",
        )
    return user


#: Code renvoyé quand une action exige une confirmation par mot de passe.
#: L'interface le reconnaît et demande le mot de passe, plutôt que d'afficher
#: une erreur d'autorisation incompréhensible.
PASSWORD_CONFIRMATION_REQUIRED = "password_confirmation_required"


def require_password_confirmation(
    user: User = Depends(get_current_user),
    confirmation: str | None = Header(default=None, alias="X-Confirm-Password"),
) -> User:
    """
    Exige le mot de passe du compte, en plus de la session, pour les actions
    les plus privilégiées.

    Une session d'administrateur laissée ouverte suffisait à créer un compte
    de service `admin`, à changer un jeton d'outil ou à réinitialiser le mot
    de passe d'un tiers : le tout journalisé au nom du titulaire légitime.
    Le mot de passe voyage dans un en-tête dédié, jamais dans l'URL ni dans
    le corps : il ne finit ni dans les journaux d'accès ni dans un historique.

    Un compte de service (jeton API) n'a pas de mot de passe à confirmer :
    ces actions lui sont refusées, comme les routes de gouvernance.
    """
    if user.username.startswith(API_TOKEN_PREFIX_IDENTITY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cette action demande une confirmation par mot de passe : elle n'est pas accessible à un jeton API.",
        )
    if not confirmation or not verify_password(confirmation, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": PASSWORD_CONFIRMATION_REQUIRED, "message": "Confirmez votre mot de passe pour cette action."},
        )
    return user


def _authenticate_api_token(token: str, db: Session, credentials_error: HTTPException) -> User:
    from app.models.api_token import ApiToken
    from app.models.module_state import ModuleState

    # Un jeton déjà émis cesse de fonctionner si le module est désactivé -
    # cohérent avec le principe "un module éteint, c'est vraiment éteint",
    # pas seulement retiré de la navigation.
    module_state = db.get(ModuleState, "api_tokens")
    if module_state is not None and not module_state.is_active:
        raise credentials_error

    record = db.exec(select(ApiToken).where(ApiToken.token_hash == hash_api_token(token))).first()
    if not record or record.is_revoked:
        raise credentials_error

    # Vérification de l'expiration : un jeton expiré est refusé même s'il
    # n'a pas été révoqué manuellement. Comparaison timezone-aware.
    if record.expires_at is not None:
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise credentials_error

    record.last_used_at = datetime.now(timezone.utc)
    db.add(record)
    db.commit()

    # Identité synthétique, jamais persistée : un jeton d'accès programmatique
    # n'est pas un compte utilisateur (pas de mot de passe, pas de connexion
    # interactive), juste un rôle emprunté pour les vérifications d'accès
    # existantes (require_roles, filtres par développeur, etc.).
    return User(
        username=f"{API_TOKEN_PREFIX_IDENTITY}{record.name}",
        hashed_password="",
        role=record.role,
        is_active=True,
        must_change_password=False,
    )


def require_roles(*roles: UserRole):
    """Dépendance FastAPI : n'autorise l'accès qu'aux rôles listés."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Votre rôle ne permet pas d'accéder à cette ressource.",
            )
        return user

    return _dependency


def require_module(module_key: str):
    """
    Dépendance FastAPI : n'autorise l'accès qu'aux routes propres à un module
    encore activé (voir app/modules/registry.py, page /dashboard/modules).
    Un administrateur qui désactive un module coupe ainsi son accès API en
    plus de le retirer de la navigation, pas qu'un habillage visuel côté
    frontend.
    """

    def _dependency(db: Session = Depends(get_session)) -> None:
        from app.models.module_state import ModuleState

        state = db.get(ModuleState, module_key)
        if state is not None and not state.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Le module '{module_key}' est désactivé. Un administrateur peut le réactiver depuis Modules.",
            )

    return _dependency
