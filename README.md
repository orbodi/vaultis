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
| `NITROKEY_NETHSM_USER` / `NITROKEY_NETHSM_PASSWORD` | Compte NetHSM avec le rôle **Backup** (mode `integration=nethsm`) |
| `NITROKEY_NETHSM_VERIFY_TLS` | `true` / `false` — vérification TLS vers le NetHSM (défaut `true`) |
| `NITROKEY_INTEGRATION` | `nethsm` pour forcer l’API NetHSM sur tout le parc Nitrokey (sinon `demo`) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origines CSRF (prod), séparées par des virgules |
| `DJANGO_USE_HTTPS` | `true` si l’app est servie en HTTPS (cookies sécurisés) |
| `NITROKEY_BACKUP_ROOT` | Répertoire d’enregistrement des fichiers `.bkp` |

## Test réel en mode production

### 1. Fichier d’environnement

```powershell
copy .env.example .env
# Éditer .env : DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, NITROKEY_INTEGRATION=nethsm
```

Générer une clé secrète :

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 2. Préparer Nitrokey dans l’admin

Sur l’équipement **Nitrokey** :

1. **Hosts** : adresse du NetHSM (ex. `nethsm01.example.com:8443` ou URL complète).
2. **extra** (JSON) :

```json
{"integration": "nethsm"}
```

(ou laisser `NITROKEY_INTEGRATION=nethsm` dans `.env` pour tout le parc Nitrokey.)

3. Compte API avec le rôle **Backup** : saisi dans le formulaire à chaque sauvegarde, ou via `NITROKEY_NETHSM_USER` / `NITROKEY_NETHSM_PASSWORD` dans `.env`.

### 3. Lancer en prod

```powershell
.\scripts\run-prod.ps1
```

Équivalent manuel :

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings_prod"
$env:DJANGO_DEBUG = "false"
$env:DJANGO_SECRET_KEY = "votre-cle"
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost"
$env:NITROKEY_INTEGRATION = "nethsm"
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver 127.0.0.1:8000
```

### 4. Vérifications

- Connexion sur `/`, fiche Nitrokey → host + identifiants → sauvegarde.
- Message attendu en cas de succès : `Backup enregistré — …bkp (… Ko).`
- Fichier sous `backups/nitrokey/` (ou `NITROKEY_BACKUP_ROOT`).
- Certificat interne : `NITROKEY_NETHSM_VERIFY_TLS=false` uniquement en labo.

Pour un déploiement serveur (IIS, Linux + reverse proxy), utiliser `settings_prod`, HTTPS (`DJANGO_USE_HTTPS=true`) et un serveur WSGI (gunicorn, waitress, etc.) au lieu de `runserver`.

## Docker

Prérequis : [Docker](https://docs.docker.com/get-docker/) et Docker Compose.

```powershell
copy .env.example .env
# Éditer .env (DJANGO_SECRET_KEY, NITROKEY_*, etc.)

# Production (gunicorn, DEBUG=false)
docker compose up --build

# Développement (runserver, DEBUG=true, message « simulée »)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Application : [http://localhost:8000/](http://localhost:8000/)

Créer un compte admin dans le conteneur :

```powershell
docker compose exec web python manage.py createsuperuser
```

Données persistantes :

- PostgreSQL : volume `postgres_data`
- Backups NetHSM (fichiers `.bkp`) : volume `vaultis_data` (`/app/data/backups/nitrokey`)

Hors Docker, l’application utilise SQLite par défaut (sans `DATABASE_URL` ni `POSTGRES_HOST`).

## Structure du dépôt

- `config/` — paramètres Django (`settings`, URLs racine)
- `equipment/` — modèles (`Equipment`, `EquipmentType`, `BackupJob`), vues, services de backup
- `templates/` — pages (accueil, détail équipement, connexion)
- `static/` — fichiers statiques
- `docker/` — scripts conteneur (`entrypoint.sh`)
- `Dockerfile`, `docker-compose.yml` — exécution conteneurisée
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
