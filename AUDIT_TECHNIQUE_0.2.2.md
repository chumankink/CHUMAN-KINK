# Audit technique — CHUMAN-KINK Prototype 0.2.2

## Périmètre

Audit statique de l'archive `CHUMAN-KINK-Prototype-0.2.2.zip` fournie dans la conversation et corrections locales de la route de sauvegarde. Cet audit ne constitue pas une validation du projet actuellement hébergé dans Replit : l'arborescence de cette archive ne correspond pas exactement à celle décrite dans le rapport Replit communiqué séparément.

Aucune connexion au workspace Replit n'a été effectuée. Aucun Secret, aucune base de données externe et aucun fichier de l'espace Replit n'a été modifié.

## Corrections présentes dans cette copie de travail

- Import de `io` ajouté pour construire le flux de sauvegarde.
- Import de `send_file` ajouté pour envoyer le fichier SQL.
- Export SQLite corrigé pour écrire de vrais retours à la ligne (`\n`) dans le dump SQL.
- Test ajouté pour restaurer le dump dans une base temporaire distincte, vérifier `PRAGMA integrity_check` et lire le fichier SQLite depuis un processus Python séparé.

## Constats importants

1. **Configuration de lancement incohérente dans l'archive** : `.replit` lance `python app.py`, tandis que `README.md` documente Gunicorn. Le rapport Replit communiqué précédemment indique une configuration Gunicorn. Il faut comparer avec les fichiers réellement présents dans Replit avant toute modification du déploiement.
2. **Persistance non garantie** : le chemin SQLite est local par défaut (`chuman_kink.db`). Cette archive ne prouve pas que ce chemin pointe vers un volume durable en production. Un test qui relit le même fichier depuis un autre processus ne prouve pas la persistance après redémarrage, republication ou remplacement de machine.
3. **Sauvegarde non chiffrée** : `/api/backup` fournit un export SQL lisible. Il doit rester privé et être conservé dans un emplacement protégé.
4. **Restauration non intégrée** : l'application expose un export, mais pas de route de restauration. La restauration doit être faite hors application sur une copie vérifiée, jamais directement sur la base de production sans procédure approuvée.
5. **Limiteur local au processus** : il reste adapté à une seule instance/processus. Plusieurs workers ou instances demanderaient un mécanisme partagé.
6. **État du fournisseur IA** : `/api/status` indique que le fournisseur est configuré lorsque la clé et la bibliothèque sont présentes ; cela ne prouve pas que l'API distante répond réellement.
7. **Tests non exécutés ici** : `pytest` est présent, mais Flask n'est pas installé dans l'environnement d'audit et l'accès réseau nécessaire à son installation est indisponible. Les compilations Python et le contrôle syntaxique JavaScript ont réussi précédemment ; cela ne remplace pas l'exécution des tests Flask.

## Vérifications statiques

- Compilation syntaxique Python de `app.py` et `test_app.py` : réussie.
- `node --check static/app.js` : réussi.
- Vérification de sécurité front-end : les messages sont insérés avec `textContent`, pas avec du HTML interpolé ; les opérations de mutation utilisent le jeton CSRF.
- Aucun fichier de base SQLite n'est inclus dans cette archive.

## Conditions avant déploiement

- Récupérer l'archive exacte du projet actuellement présent dans Replit et comparer les fichiers.
- Confirmer le chemin SQLite réellement utilisé et la nature durable du volume de stockage.
- Vérifier la commande de démarrage réellement configurée dans Replit, sans la remplacer à l'aveugle.
- Définir les Secrets nécessaires directement dans Replit ; ne jamais les copier dans ce dépôt ou dans une conversation.
- Exécuter les tests dans l'environnement Replit avec les dépendances installées.
- Faire une sauvegarde hors production, tester sa restauration sur une copie et vérifier son intégrité.
- Ne publier qu'après validation explicite.
