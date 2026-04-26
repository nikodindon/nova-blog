# Nova-Blog

Ton blog personnel automatisé — chaque soir, un article de blog est généré en résumant ta journée de travail. Sessions Hermès, commits Git, fichiers modifiés, tout est envoyé à un modèle de langue qui transforme ta journée en récit.

**Exemple :** [22 avril 2026](http://localhost:5056/2026-04-22) — dernier article généré.

---

## Comment ça marche

Chaque soir à 20h (avec retries à 21h, 22h, 23h si besoin), le script `daily_blog.py` :

1. **Scrape tes sessions Hermès** — lit tous les fichiers `.json` et `.jsonl` de la journée (CLI + Telegram)
2. **Collecte les commits Git** — scan tes repos (`Nova-Atlas`, `hermes-agent`, `hermes-workspace`, `nova-blog`)
3. **Liste les fichiers travaillés** — fichiers modifiés dans la journée via Git
4. **Envoie tout à MiniMax Cloud** — modèle `minimax-m2.7:cloud` via le proxy Ollama Cloud
5. **Génère l'article en HTML** — structuré en 3 sections (`📌 L'actu du jour`, `💻 Ce qu'on a fait`, `🎯 Objectifs et suite`)
6. **Injecte dans le template** — et écrit `articles/YYYY-MM-DD.html`
7. **Met à jour l'index** — `articles/index.html` liste tous les articles

---

## Routing

```
/               → redirige vers le dernier article (302)
/archives       → page de toutes les archives
/YYYY-MM-DD     → article de cette date
```

---

## Structure du projet

```
nova-blog/
├── articles/              # Articles générés (YYYY-MM-DD.html)
│   └── index.html         # Page des archives (accessibles via /archives)
├── scripts/
│   ├── daily_blog.py      # Script principal — scrape + génère l'article du jour
│   ├── backfill.py        # Backfill — génère des articles pour des jours passés
│   ├── config_loader.py   # Charge la config (auth.json → config.yaml.local)
│   └── setup_keys.py      # Bootstrap — vérifie les clés API et génère la config
├── templates/
│   └── article.html       # Template HTML de base
├── config.yaml.example    # Config example (non versionné)
├── .gitignore             # Ignore auth.json et config.yaml.local
├── auth.json              # Clés API (NON COMMITTÉ — voir Configuration)
└── serve.py               # Serveur web local
```

---

## Installation

```bash
# Cloner le repo
git clone https://github.com/nikodindon/nova-blog.git
cd nova-blog

# 1. Créer auth.json avec les clés API
cp config.yaml.example config.yaml.local
# → editer config.yaml.local avec OLLAMA_API_KEY

# OU utiliser setup_keys.py (interactive)
python3 scripts/setup_keys.py

# Tester la génération du jour
python3 scripts/daily_blog.py
```

---

## Configuration

```bash
# config.yaml.local (non versionné — ignoré par .gitignore)
OLLAMA_URL     = "https://ollama.com/v1"   # Proxy Ollama Cloud
OLLAMA_API_KEY = "ton-api-key"              # Clé MiniMax
MODEL          = "minimax-m2.7:cloud"       # Modèle MiniMax
SESSIONS_DIR   = ~/.hermes/sessions         # Dossier des sessions Hermès
DAY_START_HOUR = 6                          # Heure de début de journée
GIT_REPOS      = [Nova-Atlas, hermes-agent, hermes-workspace, nova-blog, ...]
```

**`config_loader.py`** détecte automatiquement `auth.json` (ancien format) et génère `config.yaml.local` au format YAML.

Pour changer de provider LLM, remplace `OLLAMA_URL` et `OLLAMA_API_KEY` par ceux de ton choix (OpenRouter, Groq, etc.).

---

## Génération manuelle

```bash
cd ~/nova-blog

# Génère l'article du jour (skip si déjà existant)
python3 scripts/daily_blog.py

# Backfill : générer pour un jour précis
python3 scripts/backfill.py 2026-04-18

# Backfill : générer pour tous les jours avec des sessions
python3 scripts/backfill.py all
```

---

## Serveur local

```bash
python3 serve.py --port 5056
# → http://localhost:5056/         (dernière journée)
# → http://localhost:5056/archives (tous les articles)
```

---

## Parsing des sessions

Le script lit les sessions Hermès dans plusieurs formats :

- **CLI** : fichiers `.jsonl` (un message par ligne)
- **CLI** : fichiers `.json` (format single-JSON avec clé `messages` au top-level)
- **Telegram** : fichiers `request_dump_*.json` (format nested avec `request.body.messages`)

---

## Déploiement

Les articles sont du HTML statique pur — hebergeables n'importe où :

```bash
# GitHub Pages : push sur main, active GitHub Pages dans les settings
# Netlify : drag & drop du dossier articles/
# Nginx : serve le dossier articles/ directement
```

---

## Stack

- **Génération** : Python 3 + MiniMax Cloud (`minimax-m2.7:cloud`) via Ollama proxy
- **Template HTML** : design dark (Playfair Display + Source Sans 3)
- **Planification** : cron jobs Hermès (20h, 21h, 22h, 23h)
- **Source des données** : sessions Hermès (`.json` + `.jsonl` + Telegram dumps) + Git log + Git name-only
