"""
Sérialisation des écritures dans une chaîne d'intégrité.

Deux requêtes qui ajoutent en même temps une entrée à la même chaîne liraient
la même « dernière entrée » et produiraient deux successeurs légitimes du
même condensat : une fourche, que la vérification signale ensuite comme une
rupture. Un verrou consultatif PostgreSQL, tenu jusqu'à la fin de la
transaction, fait passer ces écritures l'une après l'autre. SQLite n'a qu'un
écrivain à la fois : rien à faire.
"""
from sqlalchemy import text
from sqlmodel import Session


def serialize_chain_writes(session: Session, chain: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:chain))"), {"chain": chain})
