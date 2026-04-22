# Nova-Blog

Ton blog personnel automatisé — chaque soir, un article de blog est généré en résumant ta journée de travail. Sessions Hermès, commits Git, fichiers modifiés, tout est envoyé à un modèle de langue qui transforme ta journée en récit.

**Exemple :** [22 avril 2026](http://localhost:5056/2026-04-22) — dernier article généré.

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
│   └── backfill.py        # Backfill — génère des articles pour des jours passés
└── serve.py               # Serveur web local
```

---

## Installation

```bash
# Cloner le repo
git clone https://github.com/nikodindon/nova-blog.git
cd nova-blog

# Tester la génération du jour
python3 scripts/daily_blog.py
```

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
# → http://localhost:5056/         (derniere journee)
# → http://localhost:5056/archives (tous les articles)
```

---

## Configuration

Modifiable dans `scripts/daily_blog.py` et `scripts/backfill.py` :

```python
OLLAMA_URL   = "http://localhost:11434"  # Proxy Ollama local
MODEL        = "minimax-m2.7:cloud"      # Modele MiniMax
SESSIONS_DIR = Path.home() / ".hermes" / "sessions"
DAY_START_HOUR = 6                        # Heure de debut de journee
GIT_REPOS    = [...]                      # Repos Git a scanner
```

Pour changer de provider LLM, remplace l'URL Ollama par celle de ton choix (OpenRouter, Groq, etc.) et le nom du modele.

---

## deploiement

Les articles sont du HTML statique pur — hebergeables n'importe ou :

```bash
# GitHub Pages : push sur main, active GitHub Pages dans les settings
# Netlify : drag & drop du dossier articles/
# Nginx : serve le dossier articles/ directement
```

---

## Stack

- **Generation** : Python 3 + MiniMax Cloud (`minimax-m2.7:cloud`) via Ollama proxy
- **Template HTML** : design dark (Playfair Display + Source Sans 3)
- **Planification** : cron jobs Hermes (20h, 21h, 22h, 23h)
- **Source des donnees** : sessions Hermès `.jsonl` + Git log + Git name-only
