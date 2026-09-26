from sqlmodel import Session, select

from app.core.database import db_manager


class AppState:
    def __init__(self):
        self.db_connected = False
        self.setup_step = "database"
        self.setup_locked = False

    @property
    def is_setup_complete(self) -> bool:
        return self.db_connected and self.setup_locked


class AppStateManager:
    """
    État de l'installation, relu à la demande.

    Volontairement PASSIF à la construction : importer `app.main` ne doit rien
    ouvrir. Sinon un simple `python -c "import app.main"` (contrôle d'import,
    génération d'OpenAPI, collecte de tests) se connectait à la base de
    l'environnement courant et y jouait les migrations. C'est le cycle de vie
    de l'application qui appelle `refresh()`, une fois, au démarrage.
    """

    def __init__(self):
        self.state = AppState()

    def refresh(self) -> None:
        """
        Reflète l'état réel du système : tente la connexion DB (variables
        d'environnement ou bootstrap local), puis lit l'avancement du wizard
        depuis `SystemSettings` en base, la seule source de vérité fiable
        quand plusieurs instances tournent en parallèle.
        """
        self.state.db_connected = db_manager.load_existing_config()
        if not self.state.db_connected:
            self.state.setup_step = "database"
            self.state.setup_locked = False
            return

        from app.models.system import SystemSettings

        with Session(db_manager.engine) as session:
            settings = session.exec(select(SystemSettings)).first()
            if settings:
                self.state.setup_step = settings.setup_step
                self.state.setup_locked = settings.setup_locked


app_state_manager = AppStateManager()
