import json
import logging
from pathlib import Path

from sqlmodel import Session, create_engine, select

from app.config import get_settings
from app.core.secrets_store import LOCAL_DATA_DIR

logger = logging.getLogger(__name__)

BOOTSTRAP_FILE = LOCAL_DATA_DIR / "db_bootstrap.json"


class DatabaseManager:
    def __init__(self):
        self.engine = None
        # Paramètres non-secrets de la connexion active, pour affichage
        # (GET /api/config/database), jamais le mot de passe en mémoire
        # au-delà de ce qu'il faut pour ouvrir la connexion.
        self.current_params: dict | None = None
        self.current_url: str | None = None

    def connect_and_init(self, host, port, user, password, dbname, persist: bool = True) -> None:
        """
        Se connecte à PostgreSQL, applique les migrations, et (si `persist`)
        sauvegarde la configuration localement de façon chiffrée pour les
        redémarrages ultérieurs de cette instance.
        """
        from app.core.crypto import secret_box  # import tardif : évite un cycle au chargement du module

        database_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        new_engine = create_engine(database_url, pool_pre_ping=True)

        with new_engine.connect():
            pass  # test de connexion : lève une exception si les identifiants/host sont invalides

        self.engine = new_engine
        self.current_params = {"host": host, "port": port, "user": user, "dbname": dbname}
        self.current_url = database_url

        self._migrate(database_url)
        self._ensure_system_settings_row()
        self._ensure_default_admin()
        self._ensure_module_states()

        if persist:
            LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
            config_data = {
                "host": host,
                "port": port,
                "user": user,
                "password": secret_box.encrypt(password),
                "dbname": dbname,
            }
            with open(BOOTSTRAP_FILE, "w") as f:
                json.dump(config_data, f)

    def _migrate(self, database_url: str) -> None:
        """
        Schéma tenu par Alembic (alembic/versions), seul mécanisme. Une base
        vide reçoit les migrations ; une base peuplée mais jamais marquée
        (créée par `create_all`, au schéma courant) est simplement marquée à
        jour sans rien recréer.
        """
        from sqlalchemy import inspect

        from alembic import command
        from alembic.config import Config

        root = Path(__file__).resolve().parents[2]
        cfg = Config(str(root / "alembic.ini"))
        cfg.set_main_option("script_location", str(root / "alembic"))
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

        tables = set(inspect(self.engine).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            command.stamp(cfg, "head")
            return
        command.upgrade(cfg, "head")

    def _ensure_system_settings_row(self) -> None:
        from app.models.system import SystemSettings

        with Session(self.engine) as session:
            existing = session.exec(select(SystemSettings)).first()
            if not existing:
                # Plus d'étape "admin" séparée dans le wizard : le compte est
                # semé automatiquement par _ensure_default_admin() juste après.
                session.add(SystemSettings(setup_step="integrations", setup_locked=False))
                session.commit()

    def _ensure_default_admin(self) -> None:
        """
        Sème un compte admin/admin par défaut si aucun admin n'existe encore
        (façon SonarQube), plus simple qu'une étape de wizard dédiée à
        choisir des identifiants. `must_change_password` force le changement
        au premier login, avant tout accès au Dashboard.
        """
        from app.core.security import hash_password
        from app.models.user import User, UserRole

        with Session(self.engine) as session:
            existing_admin = session.exec(select(User).where(User.role == UserRole.ADMIN)).first()
            if not existing_admin:
                session.add(
                    User(
                        username="admin",
                        hashed_password=hash_password("admin"),
                        role=UserRole.ADMIN,
                        must_change_password=True,
                    )
                )
                session.commit()

    def _ensure_module_states(self) -> None:
        """
        Sème une ligne ModuleState pour chaque module du registre qui n'en a
        pas encore (nouvelle installation, ou nouveau module ajouté depuis
        une mise à jour du code), avec son état par défaut. N'écrase jamais
        l'état d'un module déjà connu : le choix de l'administrateur (activé/
        désactivé) survit aux redémarrages et aux mises à jour.
        """
        from app.models.module_state import ModuleState
        from app.modules.registry import MODULES

        with Session(self.engine) as session:
            existing_keys = set(session.exec(select(ModuleState.module_key)))
            for module in MODULES:
                if module.key not in existing_keys:
                    session.add(ModuleState(module_key=module.key, is_active=module.default_active))
            session.commit()

    def load_existing_config(self) -> bool:
        """
        Reconnecte la base au démarrage de l'instance. Priorité :
        1. Variables d'environnement DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
          , recommandé en production / multi-instances (même secret injecté
           à toutes les instances via l'orchestrateur de conteneurs).
        2. Fichier de bootstrap local chiffré généré par le wizard, mode
           "installation simple", une seule instance.
        Renvoie True si une connexion active existe à l'issue de l'appel.
        """
        if self.engine is not None:
            return True

        settings = get_settings()
        if settings.db_host:
            try:
                self.connect_and_init(
                    host=settings.db_host,
                    port=settings.db_port,
                    user=settings.db_user,
                    password=settings.db_password,
                    dbname=settings.db_name,
                    persist=False,
                )
                return True
            except Exception as e:
                logger.warning(f"Échec de connexion via variables d'environnement DB_*: {e}")
                return False

        if BOOTSTRAP_FILE.exists():
            from app.core.crypto import secret_box

            try:
                with open(BOOTSTRAP_FILE) as f:
                    data = json.load(f)
                self.connect_and_init(
                    data["host"],
                    data["port"],
                    data["user"],
                    secret_box.decrypt(data["password"]),
                    data["dbname"],
                    persist=False,
                )
                return True
            except Exception as e:
                logger.warning(f"Erreur de reconnexion auto depuis le bootstrap local: {e}")
                return False

        return False


def resolve_database_url() -> str | None:
    """URL PostgreSQL telle que load_existing_config la construirait, sans ouvrir de connexion (usage : alembic/env.py)."""
    settings = get_settings()
    if settings.database_url_from_env:
        return settings.database_url_from_env
    if BOOTSTRAP_FILE.exists():
        from app.core.crypto import secret_box

        data = json.loads(BOOTSTRAP_FILE.read_text(encoding="utf-8"))
        return f"postgresql://{data['user']}:{secret_box.decrypt(data['password'])}@{data['host']}:{data['port']}/{data['dbname']}"
    return None


# Instance globale
db_manager = DatabaseManager()


def get_session():
    """Dépendance FastAPI pour injecter la session de base de données dans les routes."""
    if db_manager.engine is None:
        raise Exception("Base de données non initialisée.")

    with Session(db_manager.engine) as session:
        yield session
