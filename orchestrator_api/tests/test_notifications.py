"""
Notifications : ce qui est préparé en base (qui prévenir, et faut-il
prévenir), et ce qui part dans la file (l'envoi, réessayable). Aucun SMTP
n'est ouvert ici.
"""
import pytest
from sqlmodel import Session, select

from app.models.module_state import ModuleState
from app.models.notification_config import NotificationConfig
from app.models.user import User
from app.services import notifier


@pytest.fixture
def session(db):
    with Session(db) as s:
        for username, email in (("admin", "admin@exemple.org"), ("rssi", "rssi@exemple.org"), ("dev", "dev@exemple.org")):
            user = s.exec(select(User).where(User.username == username)).one()
            user.email = email
            s.add(user)
        s.add(NotificationConfig(id=1, smtp_host="smtp.exemple.org", from_address="hadi@exemple.org"))
        s.commit()
        yield s


def deactivate(session: Session, module: str = "notifications") -> None:
    state = session.get(ModuleState, module)
    state.is_active = False
    session.add(state)
    session.commit()


BLOCKED = dict(repository="demo", commit_hash="a" * 40, decision="BLOCKED", justification="2 vulnérabilités critiques")
DEROGATION = dict(repository="demo", commit_hash="a" * 40, developer_username="dev", approved_by="admin", four_eyes_approved_by="rssi")


# --- ce qui déclenche, ou non, une notification -------------------------------------

def test_un_blocage_previent_administrateurs_et_responsables_securite(session):
    message = notifier.prepare_waiting_or_blocked(session, **BLOCKED)
    assert message.recipients == ["admin@exemple.org", "rssi@exemple.org"]
    assert "demo" in message.subject and "bloqué" in message.subject
    assert "2 vulnérabilités critiques" in message.body


def test_module_desactive_rien_a_envoyer(session):
    deactivate(session)
    assert notifier.prepare_waiting_or_blocked(session, **BLOCKED) is None
    assert notifier.prepare_derogation_granted(session, **DEROGATION) is None


def test_sans_smtp_configure_rien_a_envoyer(db):
    with Session(db) as s:  # aucune NotificationConfig
        assert notifier.prepare_waiting_or_blocked(s, **BLOCKED) is None


def test_une_case_decochee_fait_taire_ce_cas_la(session):
    config = session.get(NotificationConfig, 1)
    config.notify_on_blocked = False
    session.add(config)
    session.commit()
    assert notifier.prepare_waiting_or_blocked(session, **BLOCKED) is None
    assert notifier.prepare_waiting_or_blocked(session, **{**BLOCKED, "decision": "WAITING_HUMAN"}) is not None


def test_une_derogation_previent_aussi_le_developpeur_sans_doublon(session):
    admin = session.exec(select(User).where(User.username == "admin")).one()
    admin.email = "dev@exemple.org"  # même adresse que le développeur concerné
    session.add(admin)
    session.commit()
    message = notifier.prepare_derogation_granted(session, **DEROGATION)
    assert message.recipients == ["dev@exemple.org", "rssi@exemple.org"]
    assert "admin" in message.body and "rssi" in message.body


def test_personne_a_prevenir_pas_de_message(session):
    for user in session.exec(select(User)):
        user.email = None
        session.add(user)
    session.commit()
    assert notifier.prepare_waiting_or_blocked(session, **BLOCKED) is None


# --- mise en file et envoi ------------------------------------------------------------

@pytest.mark.anyio
async def test_la_notification_part_dans_la_file(session, monkeypatch):
    mis_en_file = []

    async def depot(message):
        mis_en_file.append(message)

    monkeypatch.setattr("app.orchestration.jobs.enqueue_notification", depot)
    monkeypatch.setattr(notifier, "send_email", lambda *a, **k: pytest.fail("aucun SMTP ne doit être ouvert dans le fil de la décision"))

    await notifier.notify_waiting_or_blocked(session, **BLOCKED)
    assert len(mis_en_file) == 1 and mis_en_file[0].recipients == ["admin@exemple.org", "rssi@exemple.org"]


@pytest.mark.anyio
async def test_une_notification_mise_en_file_n_est_pas_aussi_envoyee_sur_place(session, monkeypatch):
    """
    Le dépôt s'attend sur la boucle de la file, il ne s'y confie pas : le
    faire par `submit()` depuis un job bloquait cette même boucle jusqu'au
    délai, la décision repartait par l'envoi direct, puis le job finissait
    par partir lui aussi. Le destinataire recevait deux fois la même alerte.
    """
    monkeypatch.setattr("app.orchestration.jobs.enqueue_notification", _depot_qui_reussit)
    monkeypatch.setattr(notifier, "send_email", lambda *a, **k: pytest.fail("déjà en file : aucun envoi direct"))

    await notifier.notify_waiting_or_blocked(session, **BLOCKED)


async def _depot_qui_reussit(message):
    return 1


def test_sans_file_de_travail_l_envoi_se_fait_sur_place(session, monkeypatch):
    def pas_de_file(message):
        raise RuntimeError("File de travail indisponible")

    envoyes = []
    monkeypatch.setattr("app.orchestration.jobs.defer_notification", pas_de_file)
    monkeypatch.setattr(notifier, "send_email", lambda config, to, subject, body: envoyes.append((to, subject)))

    notifier.notify_derogation_granted(session, **DEROGATION)
    assert len(envoyes) == 1 and "Dérogation accordée" in envoyes[0][1]


@pytest.mark.anyio
async def test_un_echec_d_envoi_ne_remonte_jamais_dans_la_decision(session, monkeypatch):
    async def file_absente(message):
        raise RuntimeError("file absente")

    monkeypatch.setattr("app.orchestration.jobs.enqueue_notification", file_absente)
    monkeypatch.setattr(notifier, "send_email", lambda *a, **k: (_ for _ in ()).throw(OSError("SMTP injoignable")))
    await notifier.notify_waiting_or_blocked(session, **BLOCKED)  # ne lève pas


@pytest.mark.anyio
async def test_sans_file_la_notification_part_quand_meme(session, monkeypatch):
    """La file indisponible ne doit pas faire disparaître l'alerte."""
    async def file_absente(message):
        raise RuntimeError("file absente")

    envoyes = []
    monkeypatch.setattr("app.orchestration.jobs.enqueue_notification", file_absente)
    monkeypatch.setattr(notifier, "send_email", lambda config, to, subject, body: envoyes.append(subject))
    await notifier.notify_waiting_or_blocked(session, **BLOCKED)
    assert envoyes == ["[Hadi] Pipeline bloqué : demo"]


def test_l_envoi_relit_la_configuration_au_dernier_moment(session, monkeypatch):
    envoyes = []
    monkeypatch.setattr(notifier, "send_email", lambda config, to, subject, body: envoyes.append(config.smtp_host))
    message = notifier.prepare_waiting_or_blocked(session, **BLOCKED)

    config = session.get(NotificationConfig, 1)
    config.smtp_host = "nouveau.exemple.org"
    session.add(config)
    session.commit()
    notifier.deliver(session, message)
    assert envoyes == ["nouveau.exemple.org"]

    # Module coupé entre la mise en file et l'envoi : le job s'arrête là.
    deactivate(session)
    notifier.deliver(session, message)
    assert envoyes == ["nouveau.exemple.org"]


def test_l_erreur_smtp_remonte_depuis_le_job_pour_declencher_le_reessai(session, monkeypatch):
    monkeypatch.setattr(notifier, "send_email", lambda *a, **k: (_ for _ in ()).throw(OSError("SMTP injoignable")))
    message = notifier.prepare_waiting_or_blocked(session, **BLOCKED)
    with pytest.raises(OSError):
        notifier.deliver(session, message)
