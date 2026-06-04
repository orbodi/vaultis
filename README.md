# Device backup (Vaultis)

Application web Django pour inventorier des équipements réseau et lancer des sauvegardes de configuration via des **adaptateurs** Python (`equipment.adapters.*`).

| Type | État |
|------|------|
| **Nitrokey / NetHSM** | API réelle (`POST /api/v1/system/backup`) |
| **Arbor AED** | Classement `arbor-backup-*` + archivage SCP |
| F5, Palo Alto, etc. | Simulé (adaptateur stub) |

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

Données persistantes (bind mount sur l’hôte, voir `.env`) :

| Variable | Montage conteneur | Contenu |
|----------|-------------------|---------|
| `VAULTIS_HOST_DATA_DIR` | `/app/data` | Sauvegardes NetHSM (`.bkp` sous `backups/nitrokey/`) |
| `POSTGRES_HOST_DATA_DIR` | `/var/lib/postgresql/data` | Base PostgreSQL |

Exemple sur le serveur :

```env
VAULTIS_HOST_DATA_DIR=/home/abourobodi/atos/vaultis
POSTGRES_HOST_DATA_DIR=/home/abourobodi/atos/postgres
NITROKEY_BACKUP_ROOT=/app/data/backups/nitrokey
```

Fichiers `.bkp` visibles sur l’hôte : `/home/abourobodi/atos/vaultis/backups/nitrokey/`.  
Au premier démarrage, créer les dossiers (`mkdir -p …`) et, pour PostgreSQL, s’assurer que le répertoire est vide ou déjà initialisé.

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
2. Sur la fiche : sélection du host, puis **identifiants par défaut** (`.env`) ou **autres credentials** via le bouton dédié.
3. Optionnel dans **extra** : `{"integration": "nethsm"}` ou variable `NITROKEY_INTEGRATION=nethsm`.

Dès que identifiant et mot de passe sont fournis dans le formulaire, l’appel API réel est utilisé.

### Fichiers de backup

Enregistrés sous `NITROKEY_BACKUP_ROOT` (défaut `backups/nitrokey/`), nom horodaté :

```text
2026-01-06_14-30-00_nethsm_172_16_42_112.bkp
```

Fuseau : `UTC` (GMT+0, paramètre Django `TIME_ZONE` / `DJANGO_TIME_ZONE`).

### Transfert vers dossier Windows distant

Après création locale du `.bkp`, l’application peut copier le fichier vers un répertoire configurable via `.env` :

```env
NITROKEY_WINDOWS_TRANSFER_DIR=/app/data/windows-transfer
```

Recommandé en Docker/Linux : monter un partage SMB/CIFS du PC Windows sur l’hôte, puis bind-mount ce point de montage dans le conteneur, et utiliser ce chemin comme `NITROKEY_WINDOWS_TRANSFER_DIR`.

Si le transfert échoue, le job passe en échec avec message fonctionnel et le détail technique est dans les logs (`docker compose logs -f web`).

### Transfert SMB direct (username/password)

Si tu veux envoyer directement sur un PC Windows distant sans montage préalable, configure :

```env
NITROKEY_WINDOWS_SMB_HOST=172.16.50.10
NITROKEY_WINDOWS_SMB_SHARE=Backups
NITROKEY_WINDOWS_SMB_REMOTE_DIR=NetHSM
NITROKEY_WINDOWS_SMB_USERNAME=svc_backup
NITROKEY_WINDOWS_SMB_PASSWORD=mot-de-passe
NITROKEY_WINDOWS_SMB_DOMAIN=
NITROKEY_WINDOWS_SMB_PORT=445
```

Quand `NITROKEY_WINDOWS_SMB_HOST` et `NITROKEY_WINDOWS_SMB_SHARE` sont définis, ce mode est prioritaire sur `NITROKEY_WINDOWS_TRANSFER_DIR`.

### Transfert SCP direct (username/password)

Si vous utilisez déjà une commande du type `scp fichier.bkp username@host:E:\NetConfig_Backup`, configure :

```env
NITROKEY_WINDOWS_SCP_HOST=172.16.12.187
NITROKEY_WINDOWS_SCP_PORT=22
NITROKEY_WINDOWS_SCP_USERNAME=username
NITROKEY_WINDOWS_SCP_PASSWORD="mot-de-passe"
NITROKEY_WINDOWS_SCP_REMOTE_DIR=E:/NetConfig_Backup
```

Le serveur Windows doit avoir OpenSSH/SFTP activé.

**Mot de passe avec `#`** : Docker Compose tronque souvent au `#` même avec guillemets. Solutions fiables :

1. Fichier secret (recommandé) : `printf '%s' 'Mon#MotDePasse' > secrets/scp_password` puis `NITROKEY_WINDOWS_SCP_PASSWORD_FILE=/app/secrets/scp_password` (et commenter `NITROKEY_WINDOWS_SCP_PASSWORD`).
2. Base64 : `NITROKEY_WINDOWS_SCP_PASSWORD_B64=$(echo -n 'Mon#MotDePasse' | base64)`.

### Sélection de la méthode

```env
NITROKEY_TRANSFER_MODE=auto
```

- `auto` : essaie `smb`, puis `scp`, puis `dir`
- `smb` : force SMB
- `scp` : force SCP
- `dir` : force copie dans `NITROKEY_WINDOWS_TRANSFER_DIR`
- `none` : pas de transfert distant

## Arbor AED (DDOS)

Pas d’appel API : l’adaptateur parcourt un **dossier source** contenant les fichiers déposés par l’AED, les classe par nom, puis les envoie en **SCP** vers une VM Windows.

### Noms reconnus

| Type | Préfixes de nom |
|------|-----------------|
| **full** | `arbor-backup-full.`, `arbor-backup-full-signatures.` |
| **inc** | `arbor-backup-inc.`, `arbor-backup-new-signatures.` |

La date de dossier est extraite du segment `YYYYMMDD` (ex. `20260603` → dossier `2026-06-03`).

### Arborescence produite (distant)

```text
E:/NetConfig_Backup/ArborAED/
  2026-06-03/
    full/
      arbor-backup-full.20260603T220003Z.manifest
      ...
    inc/
      arbor-backup-inc.20260603T220003Z.to.20260603T230003Z.manifest
      ...
```

### Configuration `.env` (DC01 / DC02)

Un **seul host** sur la fiche équipement. Les DC actifs et leurs dossiers incoming se règlent dans `.env` :

```env
ARBOR_AED_ACTIVE_DCS=DC01,DC02
ARBOR_AED_SOURCE_DIR_DC01=/app/data/arbor/incoming/dc01
ARBOR_AED_SOURCE_DIR_DC02=/app/data/arbor/incoming/dc02
ARBOR_AED_REMOTE_PARENT_DIR_DC01=E:/NetConfig_Backup/ArborAED/DC01
ARBOR_AED_REMOTE_PARENT_DIR_DC02=E:/NetConfig_Backup/ArborAED/DC02
```

- `ARBOR_AED_ACTIVE_DCS=DC01` → traite uniquement DC01 (répertoire source + distant DC01).
- `ARBOR_AED_ACTIVE_DCS=DC01,DC02` → traite les deux dans le même job.

Arborescence distante par DC :

```text
E:/NetConfig_Backup/ArborAED/DC01/2026-06-03/full|inc/
E:/NetConfig_Backup/ArborAED/DC02/2026-06-03/full|inc/
```

Chaque DC actif doit avoir `ARBOR_AED_REMOTE_PARENT_DIR_DCxx` défini dans `.env`.

SCP : réutilise `NITROKEY_WINDOWS_SCP_*` si `ARBOR_AED_SCP_*` est vide.

Optionnel : `ARBOR_AED_MOVE_SOURCE=true` pour **déplacer** les fichiers source (sinon **copie**). Fichiers non reconnus : ignorés (compteur dans le message du job).

Lancer depuis la fiche équipement type **Arbor AED** (bouton « Lancer une sauvegarde »).

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
| `NITROKEY_NETHSM_USER` / `NITROKEY_NETHSM_PASSWORD` | Identifiants API par défaut (formulaire web, mode par défaut) |
| `NITROKEY_NETHSM_VERIFY_TLS` | `false` si certificat auto-signé (`curl -k`) |
| `NITROKEY_BACKUP_ROOT` | Répertoire des fichiers `.bkp` (dans le conteneur, ex. `/app/data/backups/nitrokey`) |
| `NITROKEY_TRANSFER_MODE` | `auto`, `smb`, `scp`, `dir`, `none` |
| `NITROKEY_WINDOWS_TRANSFER_DIR` | Répertoire de copie post-backup (ex. dossier monté depuis un partage Windows) |
| `NITROKEY_WINDOWS_SMB_*` | Paramètres SMB pour transfert direct vers un partage Windows distant |
| `NITROKEY_WINDOWS_SCP_*` | Paramètres SCP pour transfert direct vers un hôte Windows |
| `VAULTIS_HOST_DATA_DIR` | Dossier hôte monté sur `/app/data` |
| `POSTGRES_HOST_DATA_DIR` | Dossier hôte pour les données PostgreSQL |
| `WEB_PORT` | Port exposé Docker (défaut `8010`) |
| `ARBOR_AED_ACTIVE_DCS` | DC à traiter, ex. `DC01` ou `DC01,DC02` |
| `ARBOR_AED_SOURCE_DIR_DC01` / `_DC02` | Dossiers incoming par datacenter |
| `ARBOR_AED_REMOTE_PARENT_DIR_DC01` / `_DC02` | Dossier mère distant SCP par DC (obligatoire si DC actif) |
| `ARBOR_AED_MOVE_SOURCE` | `true` pour déplacer au lieu de copier depuis la source |

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
