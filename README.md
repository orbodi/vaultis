# Device backup (Vaultis)

Application web Django pour inventorier des équipements réseau et lancer des sauvegardes de configuration via des **adaptateurs** Python (`equipment.adapters.*`).

| Type | État |
|------|------|
| **Nitrokey / NetHSM** | API réelle (`POST /api/v1/system/backup`) |
| F5, Palo Alto, DDoS, etc. | Simulé (adaptateur stub) |

## Prérequis

- Python 3.10+
- Environnement virtuel (recommandé)
- [Docker](https://docs.docker.com/get-docker/) + Docker Compose (recommandé pour les tests avec PostgreSQL)

## Démarrage rapide (Docker)

```powershell
copy .env.example .env
# Éditer .env : DJANGO_SECRET_KEY, POSTGRES_PASSWORD, NITROKEY_NETHSM_VERIFY_TLS, etc.

docker compose up --build
```

- Application : [http://localhost:8000/](http://localhost:8000/)
- Admin : [http://localhost:8000/admin/](http://localhost:8000/admin/)

```powershell
docker compose exec web python manage.py createsuperuser
```

**Mode développement** (runserver, messages avec « simulée » pour les backups locaux) :

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Volumes persistants :

- `postgres_data` — base PostgreSQL
- `vaultis_data` — fichiers `.bkp` NetHSM (`/app/data/backups/nitrokey`)

## Installation locale (sans Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Sans `DATABASE_URL` ni `POSTGRES_HOST`, la base utilisée est **SQLite** (`db.sqlite3`).

## Nitrokey / NetHSM

### Appel API

Équivalent de :

```bash
curl -k -X POST 'https://{host}/api/v1/system/backup' \
  -u '{user}:{password}' \
  -H 'Accept: application/octet-stream' \
  --output backup.bkp
```

- `{host}` : adresse du host cible dans l’admin (ex. `172.16.42.112`, sans `/api/v1`)
- `-k` : `NITROKEY_NETHSM_VERIFY_TLS=false` dans `.env` (certificat interne)

### Configuration admin

1. Équipement type **Nitrokey**, host = IP ou URL du NetHSM.
2. Sur la fiche : sélection du host, **identifiant** et **mot de passe** (rôle Backup NetHSM).
3. Optionnel dans **extra** : `{"integration": "nethsm"}` ou variable `NITROKEY_INTEGRATION=nethsm`.

Dès que identifiant et mot de passe sont fournis dans le formulaire, l’appel API réel est utilisé.

### Fichiers de backup

Enregistrés sous `NITROKEY_BACKUP_ROOT` (défaut `backups/nitrokey/`), nom horodaté :

```text
2026-01-06_14-30-00_nethsm_172_16_42_112.bkp
```

Fuseau : `Europe/Paris` (paramètre Django `TIME_ZONE`).

### Messages

| Mode | `DJANGO_DEBUG` | Exemple de message |
|------|----------------|-------------------|
| Dev | `true` | `Sauvegarde simulée — …` (si mode démo) |
| Prod | `false` | `Backup enregistré — ….bkp (… Ko).` |

## Mode production (hors Docker)

```powershell
copy .env.example .env
.\scripts\run-prod.ps1
```

Ou manuellement :

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings_prod"
$env:DJANGO_DEBUG = "false"
$env:DJANGO_SECRET_KEY = "votre-cle-secrete"
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost"
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver 127.0.0.1:8000
```

Clé secrète :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## Variables d’environnement

| Variable | Rôle |
|----------|------|
| `DJANGO_SETTINGS_MODULE` | `config.settings` (dev) ou `config.settings_prod` (prod) |
| `DJANGO_SECRET_KEY` | Clé secrète (obligatoire en prod) |
| `DJANGO_DEBUG` | `true` / `false` |
| `DJANGO_ALLOWED_HOSTS` | Hôtes autorisés, séparés par des virgules |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origines CSRF (ex. `http://localhost:8000`) |
| `DJANGO_USE_HTTPS` | `true` derrière HTTPS |
| `DATABASE_URL` | PostgreSQL (Docker : `postgres://user:pass@db:5432/vaultis`) |
| `POSTGRES_*` | Alternative à `DATABASE_URL` (`HOST`, `PORT`, `DB`, `USER`, `PASSWORD`) |
| `NITROKEY_INTEGRATION` | `nethsm` pour forcer l’API sur tout le parc Nitrokey |
| `NITROKEY_NETHSM_USER` / `NITROKEY_NETHSM_PASSWORD` | Identifiants optionnels (sinon formulaire web) |
| `NITROKEY_NETHSM_VERIFY_TLS` | `false` si certificat auto-signé (`curl -k`) |
| `NITROKEY_BACKUP_ROOT` | Répertoire des fichiers `.bkp` |
| `WEB_PORT` | Port exposé Docker (défaut `8000`, ex. `8010`) |

**Accès par IP** (ex. `http://172.16.41.225:8010`) : ajouter l’IP dans `DJANGO_ALLOWED_HOSTS` et l’URL complète (avec port) dans `DJANGO_CSRF_TRUSTED_ORIGINS`. Garder `DJANGO_USE_HTTPS=false` sauf reverse proxy HTTPS.

Fichier modèle : `.env.example` — copier vers `.env` (non versionné).

## Structure du dépôt

```text
config/           Paramètres Django (settings, settings_prod, URLs)
equipment/        Modèles, vues, services, adaptateurs (nitrokey, stub, …)
templates/        Interface web
static/           CSS, JS
docker/           entrypoint conteneur
scripts/          run-prod.ps1
Dockerfile
docker-compose.yml
docker-compose.dev.yml
```

## Fonctionnalités

- Liste des équipements, fiche détail, hosts multiples par actif
- Sauvegarde avec confirmation modale et validation des champs (host, identifiants Nitrokey)
- Historique des jobs (statut, host, utilisateur, message)
- Types d’équipement extensibles via `EquipmentType.adapter_key`

## Tests

```powershell
python manage.py test
```

## Licence

Usage interne / selon la politique de votre organisation.
