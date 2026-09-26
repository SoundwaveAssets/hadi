import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.secrets_store import load_or_create_secret

logger = logging.getLogger(__name__)

#: Tout jeton Fernet commence ainsi (version 0x80 en base64url).
_FERNET_PREFIX = "gAAAA"


class SecretBox:
    """
    Chiffrement symétrique (Fernet / AES-128) des secrets stockés en base ou
    sur disque (mot de passe PostgreSQL, tokens Gitea/Jenkins/SonarQube/Argo
    CD/IA) : jamais en clair, ni en base ni sur disque.
    """

    def __init__(self):
        key = load_or_create_secret("ORCHESTRATOR_MASTER_KEY", "master.key", Fernet.generate_key)
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str | None) -> str | None:
        if not plaintext:
            return plaintext
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str | None) -> str | None:
        if not ciphertext:
            return ciphertext
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            if ciphertext.startswith(_FERNET_PREFIX):
                # C'est bien un chiffré, mais pas avec cette clé : la clé maître a
                # changé. Renvoyer le chiffré comme mot de passe donnerait des
                # "identifiants refusés" très loin de la cause.
                logger.error(
                    "Secret indéchiffrable avec la clé maître actuelle (ORCHESTRATOR_MASTER_KEY ou local_data/master.key) : "
                    "la clé a probablement changé. Ressaisissez les secrets concernés."
                )
                return None
            # Valeur saisie avant l'introduction du chiffrement : renvoyée telle quelle.
            return ciphertext


secret_box = SecretBox()
