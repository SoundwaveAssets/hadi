"""
Cœur métier, sans aucune dépendance d'infrastructure.

Règle d'or de ce paquet : aucun import de `fastapi`, `sqlmodel`, `httpx`,
`procrastinate`, ni du système de fichiers, du réseau ou de l'horloge système. Tout
ce dont une règle a besoin entre par ses paramètres.

C'est ce qui rend ces règles testables en millisecondes, sans PostgreSQL ni
Jenkins.
"""
