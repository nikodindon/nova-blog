# Nova-Blog

Ton blog personnel automatisé — chaque soir, un article de blog est généré en résumant ta journée de travail. Sessions Hermès, commits Git, fichiers modifiés, tout est envoyé à un modèle de langue qui transforme ta journée en récit.

**Exemple :** [21 April 2026](https://nikodindon.github.io/nova-blog/2026-04-21) — premier article généré automatiquement.

---

## Comment ça marche

Chaque soir à 20h (avec retries à 21h, 22h, 23h si besoin), le script `daily_blog.py` :

1. **Scrape tes sessions Hermès** — lit tous les messages `.jsonl` de la journée (Telegram + CLI)
2. **Collecte les commits Git** — scan tes repos (`Nova-Atlas`, `hermes-agent`, `hermes-workspace`, `nova-blog`)
3. **Liste les fichiers travaillés** — fichiers modifiés dans la journée via Git
4. **Envoie tout à MiniMax Cloud** — modèle `minimax-m2.7:cloud` via Ollama proxy
5. **Génère l'article en HTML** — structuré en 3 sections (`📌 L'actu du jour`, `💻 Ce qu'on a fait`, `🎯 Objectifs et suite`)
6. **Injecte dans le template** — et écrit `articles/YYYY-MM-DD.html`
7. **Met à jour l'index** — `articles/index.html` liste tous les articles

---

## Structure du projet

```
nova-blog/
├── articles/              # Articles générés (YYYY-MM-DD.html)
│   └── index.html         # Page d'accueil / archives
├── scripts/
│   └── daily_blog.py     # Script principal — scrape + génère l'article
└── serve.py              # Serveur web local (python3 serve.py --port 5056)
```

---

## Installation

```bash
# Cloner le repo
git clone https://github.com/nikodindon/nova-blog.git
cd nova-blog

# Installer les dépendances (seul Python 3 requis)
# Le script utilise le proxy Ollama déjà configuré dans ~/.hermes/config.yaml

# Tester la génération
python3 scripts/daily_blog.py
```

---

## Génération manuelle

```bash
cd ~/nova-blog
python3 scripts/daily_blog.py

# Sortie → articles/YYYY-MM-DD.html
```

---

## Serveur local

```bash
python3 serve.py --port 5056
# → http://localhost:5056/
```

---

## Configuration

Modifiable dans `scripts/daily_blog.py` :

```python
OLLAMA_URL   = "http://localhost:11434/v1"   # Proxy Ollama
MODEL        = "minimax-m2.7:cloud"          # Modèle MiniMax
SESSIONS_DIR = Path.home() / ".hermes" / "sessions"
DAY_START_HOUR = 6                            # Heures considérée comme "journée"
GIT_REPOS    = [...]                          # Repos Git à scanner
```

Pour changer de provider LLM, remplace l'URL Ollama par celle de ton choix (OpenRouter, Groq, etc.) et le nom du modèle.

---

## Déploiement

Les articles sont du HTML statique pur — hébergeables n'importe où :

```bash
# GitHub Pages : push sur main, active GitHub Pages dans les settings
# Netlify : drag & drop du dossier articles/
# Nginx : serve le dossier articles/ directement
```

---

## Stack

- **Génération** : Python 3 + MiniMax Cloud (`minimax-m2.7:cloud`) via Ollama proxy
- **Template HTML** : inspiré du design Nova-Atlas (Playfair Display + Source Sans 3)
- **Planification** : cron jobs Hermes (20h, 21h, 22h, 23h)
- **数据来源** : sessions Hermès `.jsonl` + Git log + Git name-only
