# Device backup

Application web Django pour inventorier des équipements réseau et déclencher des sauvegardes de configuration. L’exécution des backups est actuellement **simulée** (voir `equipment/services.py`) en attendant le branchement sur les APIs réelles (F5, Palo Alto, etc.) via les adaptateurs prévus par `EquipmentType.adapter_key`.

## Prérequis

- Python 3.10 ou supérieur
- Un environnement virtuel (recommandé)

## Installation

À la racine du dépôt (dossier contenant `manage.py`) :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
```

Créer un compte administrateur pour l’interface d’administration et la connexion à l’application :

```powershell
python manage.py createsuperuser
```

## Lancer le serveur de développement

```powershell
python manage.py runserver
```

Ouvrir [http://127.0.0.1:8000/](http://127.0.0.1:8000/) : la liste des équipements nécessite une session (connexion). L’admin Django est disponible sur [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

## Variables d’environnement (optionnel)

| Variable | Rôle |
|----------|------|
| `DJANGO_SECRET_KEY` | Clé secrète Django (obligatoire en production) |
| `DJANGO_DEBUG` | `true` / `false` — désactiver en production |
| `DJANGO_ALLOWED_HOSTS` | Liste séparée par des virgules (ex. `example.com,www.example.com`) |

## Structure du dépôt

- `config/` — paramètres Django (`settings`, URLs racine)
- `equipment/` — modèles (`Equipment`, `EquipmentType`, `BackupJob`), vues, services de backup
- `templates/` — pages (accueil, détail équipement, connexion)
- `static/` — fichiers statiques
- `db.sqlite3` — base SQLite locale (générée après migration ; ne pas versionner en production sensible)

## Fonctionnalités principales

- Liste des équipements et fiche détail avec métadonnées JSON optionnelles
- Déclenchement d’un job de sauvegarde depuis la fiche (POST) ; historique des jobs sur la fiche
- Types d’équipement extensibles et champ `adapter_key` pour futurs modules Python

## Tests

```powershell
python manage.py test
```

## Licence

Usage interne / selon la politique de votre organisation.
