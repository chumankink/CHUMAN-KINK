# Notes de déploiement — 0.2.2

- Garder une seule instance / un seul worker tant que le limiteur est en mémoire.
- Définir `CK_ADMIN_PASSWORD` et `CK_SECRET_KEY` dans les Secrets Replit, jamais dans le dépôt.
- Conserver `COOKIE_SECURE=true` sur HTTPS. Pour un test local HTTP uniquement, utiliser `false`.
- Définir `OPENAI_API_KEY` uniquement si le moteur OpenAI doit être activé.
- Vérifier `/health` après chaque redémarrage.
- Télécharger périodiquement `/api/backup` et conserver les exports hors du projet.
- La sauvegarde SQL n'est pas chiffrée. Protéger l'accès et le stockage.
- Ne pas activer de workers multiples sans remplacer le limiteur par un stockage partagé.


## Déploiement Render + Neon

- Définir `CK_DATABASE_URL` dans les variables privées Render avec l’URI PostgreSQL Neon. Ne jamais la placer dans Git.
- Si `CK_DATABASE_URL` est vide, l’application conserve le backend SQLite local (`CK_DATABASE_PATH`).
- Le backend PostgreSQL crée la table `messages` et ajoute de façon non destructive la colonne `include_in_context` si nécessaire.
- Sur PostgreSQL, `/api/backup` fournit un export JSON des messages ; sur SQLite, il fournit le dump SQL existant. Conserver les exports hors du serveur.
- Déployer une seule instance et un seul worker : le limiteur de débit est en mémoire.
- Render gratuit utilise un système de fichiers éphémère ; ne pas y stocker la base de production. Utiliser Neon via `CK_DATABASE_URL`.
