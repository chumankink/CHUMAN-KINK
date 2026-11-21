# Plan de test — CHUMAN-KINK 0.2.2

À exécuter dans Replit après avoir défini `CK_ADMIN_PASSWORD` et `CK_SECRET_KEY`.

1. Démarrer l'application. `/health` doit renvoyer 200 avec `database: ok`.
2. Sans session, `/` redirige vers `/login` et `/api/history` renvoie 401.
3. Le formulaire de connexion contient un jeton CSRF. Une soumission sans jeton doit être refusée (400).
4. Une connexion avec le bon mot de passe ouvre l'interface.
5. Les requêtes POST sans jeton CSRF vers `/api/chat`, `/api/reset` et `/logout` sont refusées (403).
6. Envoyer un message de test : une réponse doit être affichée et persistée.
7. `/api/history?limit=1` doit paginer correctement ; tester aussi `before=-1` (400).
8. `/api/backup` doit télécharger un fichier SQL non vide.
9. `/api/reset` doit effacer l'historique après confirmation.
10. Après déconnexion, l'accès aux routes privées doit de nouveau être refusé.
11. Sans `OPENAI_API_KEY`, l'application doit rester utilisable en mode démo sans planter.
12. Avec une clé fournisseur valide, tester une réponse réelle et consulter les journaux en cas d'échec.

Ne teste pas la restauration sur la base de production. Fais-le sur une copie.
