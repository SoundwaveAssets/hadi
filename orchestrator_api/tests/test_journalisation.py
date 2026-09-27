"""Les migrations ne doivent pas éteindre la journalisation de l'application."""
import logging
from logging.config import fileConfig
from pathlib import Path

API = Path(__file__).resolve().parent.parent
ENV = API / "alembic" / "env.py"
ALEMBIC_INI = API / "alembic.ini"


def test_alembic_ne_desactive_pas_les_loggers_existants():
    """`fileConfig` désactive par défaut tout logger déjà créé."""
    assert "disable_existing_loggers=False" in ENV.read_text(encoding="utf-8")


def test_un_logger_de_l_application_survit_a_la_configuration_alembic():
    logger = logging.getLogger("app.test.journalisation")
    logger.warning("avant")
    fileConfig(str(ALEMBIC_INI), disable_existing_loggers=False)
    assert not logger.disabled
    assert logger.isEnabledFor(logging.WARNING)


def test_la_configuration_par_defaut_eteindrait_ce_logger():
    """Garde-fou : sans le drapeau, le défaut de fileConfig est destructeur."""
    logger = logging.getLogger("app.test.journalisation.temoin")
    logger.warning("avant")
    fileConfig(str(ALEMBIC_INI))
    assert logger.disabled
    fileConfig(str(ALEMBIC_INI), disable_existing_loggers=False)
