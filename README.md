# CHUMAN-KINK — Prototype 0.2.2 (stabilisation)

Cette version reprend le prototype 0.1 et corrige les premiers défauts confirmés par l'audit Claude. Elle reste un prototype web monopersonnel : ce n'est pas encore l'architecture hybride complète.

## Changements apportés

- Authentification administrateur obligatoire avant l'accès à l'interface et aux API privées.
- Démarrage verrouillé tant que le mot de passe administrateur et la clé de session ne sont pas configurés.
- Protection CSRF ajoutée au formulaire de connexion.
- Fermeture explicite des connexions après chaque opération (SQLite ou PostgreSQL).
- Pagination corrigée pour détecter correctement la fin de l'historique, y compris lorsque le nombre de messages est un multiple exact de la taille de page.
- Protection CSRF sur les requêtes qui modifient les données.
- `/api/reset` est désormais protégé par authentification et CSRF.
- Validation stricte du JSON et du type du champ `message` : une valeur non textuelle renvoie 400 au lieu de provoquer une erreur serveur.
- Historique paginé par curseur : il n'est plus limité définitivement aux 100 premiers messages.
- Les réponses de démonstration et les erreurs ne sont pas réinjectées dans le contexte IA.
- Limitation de débit en mémoire pour les connexions et les messages.
- Délai maximal et nombre de tentatives limité pour les appels OpenAI.
- En-têtes HTTP de sécurité et migration automatique de la base SQLite 0.1.
- Ajout de Gunicorn pour le lancement en déploiement.

## Configuration Render + Neon

L’application peut fonctionner avec PostgreSQL (Neon) ou conserver SQLite en local.
Pour Render + Neon, définir `CK_DATABASE_URL` dans les variables privées Render avec l’URI PostgreSQL fournie par Neon. Ne jamais enregistrer cette URI dans GitHub.

Render gratuit utilise un disque éphémère : la base de production doit donc être sur Neon, pas dans un fichier SQLite du service.
Le code crée la table `messages` sur PostgreSQL et ajoute la colonne `include_in_context` si elle manque. Cette préparation ne copie pas automatiquement les anciennes conversations SQLite : conserver la base d’origine et réaliser une migration/export séparée avant de considérer l’historique transféré.

Le point de santé `/health` vérifie une requête à la base configurée. Sur PostgreSQL, `/api/backup` télécharge un export JSON ; sur SQLite, le format SQL historique est conservé.

Le dépôt contient `render.yaml` et `Procfile` pour lancer Gunicorn avec un seul worker. Le limiteur de débit étant en mémoire, ne pas augmenter le nombre de workers ou d’instances sans le remplacer par un stockage partagé.

## Configuration Replit (compatibilité)

Dans **Secrets / Environment Variables**, ajouter :

- `CK_ADMIN_PASSWORD` : mot de passe administrateur long et unique.
- `CK_SECRET_KEY` : valeur aléatoire longue utilisée pour signer les sessions.
- `OPENAI_API_KEY` : clé API OpenAI (facultative tant que le moteur IA n'est pas activé).
- `OPENAI_MODEL` : facultatif, modèle autorisé sur ton compte.

Ne place jamais ces valeurs dans les fichiers du projet, le HTML, le JavaScript ou une conversation. Si `CK_ADMIN_PASSWORD` n'est pas défini, l'application reste verrouillée et affiche la configuration nécessaire.

Pour un test local HTTP uniquement, définir `COOKIE_SECURE=false`. En hébergement HTTPS, conserver `COOKIE_SECURE=true` (valeur par défaut).

## Lancement

Développement :

```bash
python app.py
```

Déploiement :

```bash
gunicorn --workers 1 --threads 4 --timeout 45 --bind 0.0.0.0:$PORT app:app
```

Le limiteur de débit actuel est en mémoire et convient uniquement à une instance / un processus. Pour plusieurs instances, il faudra le remplacer par un stockage partagé tel que Redis.

## Version 0.2.1 — correctifs complémentaires

Cette révision corrige la fermeture des connexions SQLite, impose les deux secrets d'administration avant l'accès, protège aussi le formulaire de connexion contre les soumissions CSRF et fiabilise le curseur de pagination.

## Limites restantes à traiter

- La base SQLite n'est pas encore chiffrée au repos : protéger le stockage et les sauvegardes de l'environnement d'hébergement. Le chiffrement applicatif des données nécessite une gestion de clé et une migration dédiées.
- Pas encore de comptes multiples : l'application est conçue pour un seul administrateur.
- Pas encore de mémoire sémantique/épisodique, de personnalité versionnée, de voix, d'orchestrateur GPT/Claude/Gemini ou d'autonomie planifiée.
- Pas encore de plafond de dépense global côté fournisseur ; la limite de sortie et le débit réduisent le risque sans remplacer un budget API.
- La protection CSRF utilise un jeton de session synchronisé avec le navigateur ; toute nouvelle route de mutation doit conserver ce contrôle.
- Avant une exposition publique, ajouter des tests de sécurité, sauvegardes vérifiées, surveillance, gestion des clés et revue complète du déploiement.

## Migration depuis 0.1

Conserve ton ancien dossier et ta base SQLite. La nouvelle version ajoute automatiquement la colonne `include_in_context` à la table `messages`. Elle ne supprime pas l'historique existant.


## Version 0.2.2 — stabilisation complémentaire

- Nettoyage périodique et plafond défensif des clés du limiteur de débit (toujours monoprocès).
- En-têtes CSP et HSTS conditionnel lorsque la requête est HTTPS.
- Contrôle de santé incluant la disponibilité de la base configurée (`/health`).
- Route administrateur `GET /api/backup` : télécharge un export SQL cohérent de la base.
- Validation du curseur de pagination négatif.
- Libellés de l'interface mis à jour en 0.2.2.

### Sauvegarde

Connecte-toi à l'interface puis ouvre `/api/backup` pour télécharger un export de sauvegarde (SQL sur SQLite, JSON sur PostgreSQL). Stocke-le hors de Replit, dans un emplacement privé. Cette sauvegarde n'est pas chiffrée : ne la partage pas et protège-la comme les données de conversation.

### Limites opérationnelles

Le limiteur de débit reste local au processus : un déploiement multi-instance exige un stockage partagé. Le backup est une exportation SQL, pas une sauvegarde automatique planifiée. Tester la restauration sur une copie avant toute migration importante.
