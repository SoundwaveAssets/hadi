"""
Vocabulaire des statuts d'un pipeline, en un seul endroit.

L'interface et la CLI redéclarent ces valeurs ; tests/test_status_vocabulary.py
compare les trois listes à chaque exécution.
"""
from enum import Enum


class PipelineStatus(str, Enum):
    #: Reçu, en attente d'être pris par la file.
    PENDING = "PENDING"
    #: Analyse terminée, en attente d'une décision humaine.
    WAITING_HUMAN = "WAITING_HUMAN"
    #: Première validation obtenue, la seconde manque (règle des quatre yeux).
    DEROGATION_PENDING = "DEROGATION_PENDING"
    #: Refusé par le moteur de décision.
    BLOCKED = "BLOCKED"
    #: Le workflow d'analyse lui-même n'a pas abouti (outil durablement injoignable).
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    #: Autorisé, déploiement en cours.
    DEPLOYING = "DEPLOYING"
    #: Image observée sur le cluster.
    DEPLOYED = "DEPLOYED"
    #: Déploiement interrompu : manifeste, synchronisation ou image non observée.
    DEPLOY_FAILED = "DEPLOY_FAILED"


#: Plus rien ne les fera évoluer : ni sondage, ni chien de garde.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        PipelineStatus.DEPLOYED.value,
        PipelineStatus.DEPLOY_FAILED.value,
        PipelineStatus.BLOCKED.value,
        PipelineStatus.ANALYSIS_FAILED.value,
    }
)

#: En attente d'un humain : rien ne bouge tant que personne n'a tranché,
#: et surtout, aucun délai ne doit les faire basculer en échec.
AWAITING_HUMAN_STATUSES: frozenset[str] = frozenset(
    {PipelineStatus.WAITING_HUMAN.value, PipelineStatus.DEROGATION_PENDING.value}
)

#: Un travail est en cours quelque part : c'est ce que le chien de garde
#: surveille (voir orchestration/watchdog.py) et ce que l'interface sonde
#: de près.
IN_PROGRESS_STATUSES: frozenset[str] = frozenset(
    {PipelineStatus.PENDING.value, PipelineStatus.DEPLOYING.value}
)
