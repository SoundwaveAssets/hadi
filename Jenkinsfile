// Jenkinsfile pour le pipeline 'orchestrator'.
//
// À faire dans Jenkins avant utilisation :
//   1. Créer un job de type "Pipeline" (pas "Freestyle").
//   2. "Pipeline script from SCM" : pointer sur ce dépôt, ce fichier.
//   3. Adapter la commande de build & test ci-dessous selon le projet.
//   4. Adapter REGISTRY_URL et GITEA_OWNER dans le bloc "environment", le
//      Dockerfile lui-même vit dans ce dépôt.
//   5. Créer un Credential Jenkins pour le registre (Manage Jenkins >
//      Credentials) et adapter REGISTRY_CREDS_ID s'il porte un autre nom.
//   6. S'assurer que "sonar-scanner" est disponible sur l'agent Jenkins.
//   7. Créer, dans SonarQube, un jeton d'analyse, et l'ajouter dans Jenkins
//      sous l'identifiant "SONARQUBE_ANALYSIS_CREDS_ID".
//   8. Créer un jeton API dans l'Orchestrateur (Dashboard > Jetons API -
//      activer le module si besoin) et l'ajouter dans Jenkins comme
//      Credential "Secret text" sous l'identifiant "ORCHESTRATOR_API_TOKEN".
//      Sans lui, l'étape "Vérification de sécurité" ci-dessous échoue avant
//      même de construire l'image, c'est le comportement voulu par défaut
//      (fail-closed), pas une erreur de configuration à ignorer.

pipeline {
    agent any

    environment {
        REGISTRY_URL = 'host.docker.internal:3000'
        // Organisation/compte Gitea propriétaire du dépôt registre, valeur
        // réelle pour cette instance (compte de service/organisation Gitea
        // utilisé pour héberger le registre, pas une personne). À adapter à
        // votre propre instance si vous réutilisez ce Jenkinsfile ailleurs.
        GITEA_OWNER = 'didier'
        DOCKER_IMAGE = "${REGISTRY_URL}/${GITEA_OWNER}/orchestrator"
        REGISTRY_CREDS_ID = 'gitea_credential'
        // URL vue depuis l'agent Jenkins (conteneur Docker) : host.docker.internal
        // pour joindre l'Orchestrateur, qui tourne directement sur l'hôte.
        ORCHESTRATOR_URL = 'http://host.docker.internal:8000'
    }

    parameters {
        string(name: 'COMMIT_HASH', defaultValue: '', description: 'Commit déclencheur')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                // checkout scm prend la tête de la branche : deux pushs
                // rapprochés, et le build de A compilerait B. On se cale sur
                // le commit reçu, et un job lancé sans COMMIT_HASH s'arrête.
                sh '''
                    [ -n "$COMMIT_HASH" ] || { echo "COMMIT_HASH manquant : ce job ne se lance que depuis l'Orchestrateur."; exit 1; }
                    git checkout --quiet --detach "$COMMIT_HASH"
                '''
            }
        }

        stage('Build & Test') {
            steps {
                sh '''
                    set -e

                    # Environnement virtuel conservé dans l'espace de travail :
                    # l'agent porte d'autres dépendances (un vieux Prefect, entre
                    # autres) dont les contraintes entraient en conflit à chaque
                    # build, et --ignore-installed retéléchargeait tout, dix
                    # minutes durant. Ici, seules les nouveautés sont installées.
                    #
                    # Tous les agents n'ont pas python3-venv : quand il manque,
                    # on retombe sur l'installation globale plutôt que d'échouer.
                    PIP="pip install --quiet --disable-pip-version-check"
                    if python3 -m venv "$WORKSPACE/.venv" >/dev/null 2>&1 && [ -f "$WORKSPACE/.venv/bin/activate" ]; then
                        . "$WORKSPACE/.venv/bin/activate"
                    else
                        echo "python3-venv absent de cet agent : installation dans l'environnement global."
                        PIP="$PIP --break-system-packages"
                    fi

                    cd orchestrator_api
                    $PIP -r requirements.txt
                    python3 -m py_compile app/main.py

                    cd ../cli
                    $PIP -r requirements.txt
                    python3 -m py_compile main.py

                    cd ../frontend
                    # Cache npm dans l'espace de travail et réessais explicites :
                    # un registre lent faisait échouer le build entier sur un
                    # ERR_SOCKET_TIMEOUT, alors que le code était sain.
                    export npm_config_cache="$WORKSPACE/.npm-cache"
                    export npm_config_fetch_retries=5
                    export npm_config_fetch_retry_maxtimeout=180000
                    export npm_config_fund=false
                    export npm_config_audit=false
                    npm ci --prefer-offline --no-progress || npm install --prefer-offline --no-progress
                    npm run build
                '''
            }
        }

        stage('Analyse SonarQube') {
            steps {
                withCredentials([string(credentialsId: 'SONARQUBE_ANALYSIS_CREDS_ID', variable: 'SONAR_TOKEN')]) {
                    sh '''
                        sonar-scanner \\
                          -Dsonar.projectKey=orchestrator \\
                          -Dsonar.sources=. \\
                          -Dsonar.host.url=http://host.docker.internal:9000 \\
                          -Dsonar.scm.revision=$COMMIT_HASH \\
                          -Dsonar.login=$SONAR_TOKEN
                    '''
                }
            }
        }

        stage('Vérification de sécurité') {
            // Interroge le Moteur de décision de l'Orchestrateur AVANT de
            // construire l'image : un commit qui va être bloqué ou mis en
            // attente n'a pas besoin d'une image Docker construite pour
            // rien, ça évite de saturer l'agent Jenkins en mémoire/disque
            // pour un build qui ne sera de toute façon jamais déployé.
            // N'attend PAS le job Jenkins entier côté Moteur de décision
            // (voir JenkinsClient.trigger_build_and_wait, wait_for_stage) :
            // seul "Build & Test" ci-dessus compte pour décider, donc pas de
            // verrou mortel entre cette étape et la décision qu'elle attend.
            steps {
                withCredentials([string(credentialsId: 'ORCHESTRATOR_API_TOKEN', variable: 'ORCH_TOKEN')]) {
                    sh '''
                        HTTP_CODE=$(curl -s -o /tmp/gate_response.json -w "%{http_code}" \\
                          -H "Authorization: Bearer $ORCH_TOKEN" \\
                          "$ORCHESTRATOR_URL/api/decisions/gate/orchestrator/$COMMIT_HASH?wait=300")
                        cat /tmp/gate_response.json
                        echo
                        if [ "$HTTP_CODE" != "200" ]; then
                            echo "Décision de sécurité : construction refusée ou indisponible (HTTP $HTTP_CODE)."
                            exit 1
                        fi
                        echo "Décision de sécurité : autorisé, poursuite de la construction."
                    '''
                }
            }
        }

        stage('Build image Docker') {
            steps {
                script {
                    customImage = docker.build("${DOCKER_IMAGE}:${params.COMMIT_HASH}", "--target api .")
                }
            }
        }

        stage('Push registre') {
            steps {
                script {
                    // Seul le tag du commit est poussé ici, jamais 'latest' :
                    // c'est ce que déploie Argo CD (voir application.yaml), donc
                    // pousser 'latest' inconditionnellement déploierait n'importe
                    // quel commit, y compris un commit bloqué par le Moteur de
                    // décision. C'est l'Orchestrateur qui promeut un commit en
                    // 'latest', uniquement après une décision favorable.
                    docker.withRegistry("http://${REGISTRY_URL}", REGISTRY_CREDS_ID) {
                        customImage.push("${params.COMMIT_HASH}")
                    }
                }
            }
        }
    }

    post {
        always {
            sh "docker rmi ${DOCKER_IMAGE}:${params.COMMIT_HASH} || true"
        }
        failure {
            echo "Build en échec, consultez la console Jenkins."
        }
    }
}