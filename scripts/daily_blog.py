#!/usr/bin/env python3
"""
Nova-Blog — Génère un article de blog quotidien à partir de ton activité Hermès.
Scrape : sessions Hermès, commits Git, fichiers modifiés → MiniMax génère l'article.
"""

import json, os, sys, glob, subprocess, re
import argparse
from datetime import datetime, date
from pathlib import Path

# ── Config — load from config.yaml.local (pas de clés en dur) ─────────────────
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import load_config, get_working_ollama_key

_cfg = None

def _get_cfg():
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg

def _ollama_key():
    return get_working_ollama_key(_get_cfg())

# ── Paths ─────────────────────────────────────────────────────────────────────
SESSIONS_DIR = Path.home() / ".hermes" / "sessions"
BLOG_DIR     = SCRIPT_DIR.parent
ARTICLES_DIR  = BLOG_DIR / "articles"
DATA_DIR      = BLOG_DIR / "data"
TEMPLATES_DIR = BLOG_DIR / "templates"

GIT_REPOS = [
    Path.home() / "Nova-Atlas",
    Path.home() / "hermes-agent",
    Path.home() / "hermes-workspace",
    Path.home() / "nova-blog",
    Path.home() / "StellarSiege",
    Path.home() / "nova-game-engine",
    Path.home() / "scanwiz",
    Path.home() / "hermes-lite",
]

DAY_START_HOUR = 6
YEAR = date.today().year

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_chinese_text(text: str) -> str:
    """Supprime les caractères non-latins qui polluent le HTML."""
    text = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u3000-\u303f\uff00-\uffef]+', '', text)
    text = re.sub(r'[\u0600-\u06ff\u0750-\u077f]+', '', text)
    text = re.sub(r'[\u0400-\u04ff\u0500-\u052f]+', '', text)
    text = re.sub(r'[\u0370-\u03ff]+', '', text)
    text = re.sub(r'[\u0530-\u058f]+', '', text)
    text = re.sub(r'[\u0590-\u05ff]+', '', text)
    return text


def ollama_chat(messages, model=None, max_retries=5):
    """
    Appelle Ollama Cloud avec retry automatique sur 429.
    Lit la clé fonctionnelle depuis config.yaml.local au moment de l'appel.
    """
    import urllib.request, urllib.error, time
    api_key, base_url = _ollama_key()
    cfg = _get_cfg()
    model = model or cfg.get("ollama", {}).get("model", "minimax-m2.7")

    payload = {"model": model, "messages": messages, "stream": False, "temperature": 0.7}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.load(resp)
            return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = (attempt + 1) * 15
                print(f"     ⚠  429 — retry {attempt+1}/{max_retries} dans {wait}s...")
                time.sleep(wait)
            else:
                body = e.read().decode(errors="replace")
                raise RuntimeError(f"Ollama API error {e.code}: {body[:200]}")


def get_today():
    return date.today()


def parse_session_file(path):
    """
    Handles THREE session file formats:
    1. session_*.json     — single JSON with 'messages' list, session_start at top
    2. request_dump_*.json — same as above, also has 'messages' in request.body.messages
    3. *.jsonl           — JSON Lines (legacy), one JSON object per line
    """
    messages = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()

        if not raw.strip():
            return messages

        # Try parsing as single-JSON first (session_*.json or request_dump_*.json)
        try:
            obj = json.loads(raw)
            # Single-JSON format: has 'messages' key at top level
            if "messages" in obj:
                session_ts = obj.get("session_start", "")
                for m in obj["messages"]:
                    if m.get("role") in ("user", "assistant"):
                        content = m.get("content", "")
                        if isinstance(content, str) and len(content) > 2:
                            # Per-message timestamp if available, else session_start
                            ts = m.get("timestamp", session_ts)
                            messages.append({"role": m["role"], "content": content[:500], "ts": ts})
                return messages

            # request_dump format: messages are nested in request.body.messages
            # (already covered above via "messages" key check, but handle explicitly)
            if "request" in obj and "body" in obj["request"]:
                body = obj["request"]["body"]
                if isinstance(body, dict) and "messages" in body:
                    session_ts = obj.get("timestamp", "")
                    for m in body["messages"]:
                        if m.get("role") in ("user", "assistant"):
                            content = m.get("content", "")
                            if isinstance(content, str) and len(content) > 2:
                                ts = m.get("timestamp", session_ts)
                                messages.append({"role": m["role"], "content": content[:500], "ts": ts})
                    return messages

            # If single-JSON but no messages key, skip (not a session file)
            return messages

        except json.JSONDecodeError:
            pass

        # Fall back to JSONL format (one JSON per line)
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("role") in ("user", "assistant"):
                    content = obj.get("content", "")
                    if isinstance(content, str) and len(content) > 2:
                        ts = obj.get("timestamp", "")
                        messages.append({"role": obj["role"], "content": content[:500], "ts": ts})
            except json.JSONDecodeError:
                continue

    except Exception:
        pass
    return messages


def filter_today_messages(messages, day):
    filtered = []
    for msg in messages:
        ts_str = msg.get("ts", "")
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=None)
            if dt.date() == day and dt.hour >= DAY_START_HOUR:
                filtered.append(msg)
        except Exception:
            continue
    return filtered


def get_git_today(repo_path, day):
    commits = []
    if not repo_path.exists():
        return commits
    # Resolve GitHub remote URL
    github_url = ""
    try:
        remote_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, cwd=repo_path
        )
        remote = remote_result.stdout.strip()
        if remote.startswith("https://github.com/"):
            github_url = remote.rstrip(".git")
        elif remote.startswith("git@github.com:"):
            github_url = "https://github.com/" + remote.split(":")[1].rstrip(".git")
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "log", f"--since={day} {DAY_START_HOUR}:00",
             f"--until={day} 23:59:59", "--pretty=format:%H|%s|%an|%ad",
             "--date=iso", str(repo_path)],
            capture_output=True, text=True, timeout=10, cwd=repo_path
        )
        for line in result.stdout.strip().split("\n"):
            if "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                commit_hash = parts[0][:7]
                commits.append({
                    "repo": repo_path.name,
                    "hash": commit_hash,
                    "message": parts[1],
                    "author": parts[2],
                    "date": parts[3][:10],
                    "url": f"{github_url}/commit/{commit_hash}" if github_url else "",
                })
    except Exception:
        pass
    return commits


def get_recent_files(home, day, max_files=20):
    files = []
    for repo in GIT_REPOS:
        if not repo.exists():
            continue
        try:
            result = subprocess.run(
                ["git", "log", f"--since={day} {DAY_START_HOUR}:00",
                 f"--until={day} 23:59:59",
                 "--name-only", "--pretty=format:%n", str(repo)],
                capture_output=True, text=True, timeout=10, cwd=repo
            )
            for fname in result.stdout.strip().split("\n"):
                if fname and not fname.startswith("."):
                    files.append({"repo": repo.name, "file": fname})
        except Exception:
            continue
    seen = set()
    unique = []
    for f in files:
        key = f["file"]
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique[:max_files]


def summarize_content(sessions_data, git_data, files_data, day):
    system_prompt = (
        f"Tu génères un résumé de l'activité journalière d'un développeur.\n\n"
        f"RÈGLES ABSOLUES :\n"
        f"- Réponds en HTML BRUT — pas de markdown, pas de bloc de code, pas de ```html\n"
        f"- Chaque paragraphe dans <p>, sections dans <h2>\n"
        f"- Sois FACTUEL et CONCIS — n'invente RIEN qui ne soit pas dans les données\n"
        f"- N'ajoute PAS de détails personnels (lieu, âge, situation) — utilise uniquement l'activité fournie\n"
        f"- 300-500 mots maximum\n"
        f"- PAS de conclusion типа 'En résumé'\n"
        f"- Date : {day.isoformat()}\n\n"
        f"STRUCTURE :\n"
        f"<h2>📌 Activité du jour</h2> ... paragraphes ...\n"
        f"<h2>💻 Projets/Travail</h2> ... paragraphes ...\n"
        f"<h2>🎯 Suite</h2> ... paragraphes ...\n\n"
        f"CONSEIL : Si peu d'activité, dis-le simplement. Ne cherche pas à remplir avec des détails imaginés."
    )

    user_prompt = (
        f"Activité du {day.isoformat()} :\\n\\n"
        f"=== SESSIONS HERMÈS ===\\n{sessions_data[:6000]}\\n\\n"
        f"=== COMMITS GIT ===\\n{git_data[:3000]}\\n\\n"
        f"=== FICHIERS MODIFIÉS ===\\n{files_data[:2000]}\\n\\n"
        f"Génère le résumé en HTML. Sois factuel. N'invente rien."
    )

    return ollama_chat([{"role": "system", "content": system_prompt},
                         {"role": "user", "content": user_prompt}])


# ── TEMPLATE ──────────────────────────────────────────────────────────────────

ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nova-Blog — {{DATE}}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Source+Sans+3:wght@300;400;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#0a0a0f; --bg2:#111118; --bg3:#1a1a24; --border:#2a2a3a;
  --accent:#e8612a; --accent2:#c44d1e; --gold:#c9a84c;
  --text:#e2e2e8; --text-dim:#8888a0; --text-muted:#555568;
  --radius:8px; --shadow:0 4px 24px rgba(0,0,0,0.5);
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Source Sans 3',sans-serif; font-size:17px; line-height:1.7; }
.topbar { position:sticky; top:0; z-index:100; background:var(--bg); border-bottom:1px solid var(--border); padding:14px 24px; display:flex; align-items:center; justify-content:space-between; backdrop-filter:blur(12px); }
.topbar-brand { font-family:'Playfair Display',serif; font-size:1.4rem; font-weight:700; color:var(--accent); text-decoration:none; }
.topbar-brand span { color:var(--gold); }
.topbar-nav { display:flex; gap:20px; }
.topbar-nav a { color:var(--text-dim); text-decoration:none; font-size:.9rem; font-weight:600; transition:color .2s; }
.topbar-nav a:hover { color:var(--accent); }
.container { max-width:780px; margin:0 auto; padding:48px 24px 80px; }
.post-header { margin-bottom:40px; }
.post-date { font-family:'JetBrains Mono',monospace; font-size:.8rem; color:var(--accent); letter-spacing:.1em; text-transform:uppercase; margin-bottom:12px; }
.post-stats { display:flex; gap:24px; margin-top:20px; font-size:.85rem; color:var(--text-muted); }
.post-stats span { display:flex; align-items:center; gap:6px; }
.post-divider { border:none; border-top:1px solid var(--border); margin:36px 0; }
.post-content h2 { font-family:'Playfair Display',serif; font-size:1.6rem; color:var(--text); margin:32px 0 14px; display:flex; align-items:center; gap:10px; }
.post-content h3 { font-size:1.15rem; color:var(--accent); margin:20px 0 8px; }
.post-content p { margin-bottom:16px; color:var(--text); }
.post-content strong { color:var(--gold); }
.post-content em { color:var(--text-dim); }
.post-content ul { margin:12px 0 16px 24px; }
.post-content li { margin-bottom:6px; color:var(--text); }
.post-content code { font-family:'JetBrains Mono',monospace; font-size:.85em; background:var(--bg3); padding:2px 6px; border-radius:4px; color:var(--accent); }
.post-content blockquote { border-left:3px solid var(--accent); padding-left:20px; margin:20px 0; color:var(--text-dim); font-style:italic; }
.footer { text-align:center; padding:40px 24px; color:var(--text-muted); font-size:.85rem; border-top:1px solid var(--border); margin-top:60px; }
.footer a { color:var(--accent); text-decoration:none; }
</style>
</head>
<body>
<nav class="topbar">
  <a href="/" class="topbar-brand">Nova<span>-Blog</span></a>
  <div class="topbar-nav">
    <a href="/">Archives</a>
  </div>
</nav>
<main class="container">
  <header class="post-header">
    <div class="post-date">{{DATE}}</div>
    <div class="post-stats">
      <span>💬 {{NB_MESSAGES}} messages</span>
      <span>💻 {{NB_COMMITS}} commits</span>
      <span>📁 {{NB_FILES}} fichiers</span>
    </div>
  </header>
  <hr class="post-divider">
  <div class="post-content">
    {{CONTENT}}
  </div>
</main>
<footer class="footer">
  <p>Rédigé automatiquement par <a href="#">Nova-Blog</a> &middot; """ + str(YEAR) + """</p>
</footer>
</body>
</html>"""


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nova-Blog — Archives</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Source+Sans+3:wght@300;400;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
:root { --bg:#0a0a0f; --bg2:#111118; --bg3:#1a1a24; --border:#2a2a3a; --accent:#e8612a; --accent2:#c44d1e; --gold:#c9a84c; --text:#e2e2e8; --text-dim:#8888a0; --text-muted:#555568; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Source Sans 3',sans-serif; font-size:17px; line-height:1.7; }
.topbar { position:sticky; top:0; z-index:100; background:var(--bg); border-bottom:1px solid var(--border); padding:14px 24px; display:flex; align-items:center; justify-content:space-between; backdrop-filter:blur(12px); }
.topbar-brand { font-family:'Playfair Display',serif; font-size:1.4rem; font-weight:700; color:var(--accent); text-decoration:none; }
.topbar-brand span { color:var(--gold); }
.container { max-width:900px; margin:0 auto; padding:56px 24px 80px; }
.page-title { font-family:'Playfair Display',serif; font-size:2.8rem; font-weight:700; margin-bottom:8px; }
.page-subtitle { color:var(--text-dim); margin-bottom:48px; font-size:1rem; }
.posts-grid { display:grid; gap:16px; }
.post-card { background:var(--bg2); border:1px solid var(--border); border-radius:10px; overflow:hidden; transition:border-color .2s, transform .2s; }
.post-card:hover { border-color:var(--accent); transform:translateY(-2px); }
.post-link { display:block; padding:20px 24px; text-decoration:none; color:inherit; }
.post-link time { font-family:'JetBrains Mono',monospace; font-size:.75rem; color:var(--accent); letter-spacing:.08em; text-transform:uppercase; }
.post-link h3 { font-family:'Playfair Display',serif; font-size:1.2rem; color:var(--text); margin-top:6px; font-weight:400; }
.footer { text-align:center; padding:40px 24px; color:var(--text-muted); font-size:.85rem; border-top:1px solid var(--border); margin-top:60px; }
.footer a { color:var(--accent); text-decoration:none; }
</style>
</head>
<body>
<nav class="topbar">
  <a href="/" class="topbar-brand">Nova<span>-Blog</span></a>
</nav>
<main class="container">
  <h1 class="page-title">Archives</h1>
  <p class="page-subtitle">Tous les bilans de journée, rédigés automatiquement.</p>
  <div class="posts-grid">
{{ARTICLES_LIST}}  </div>
</main>
<footer class="footer">
  <p>Propulsé par <a href="#">Nova-Blog</a> &middot; """ + str(YEAR) + """</p>
</footer>
</body>
</html>"""


def build_article_html(article_content, day, stats):
    html = ARTICLE_TEMPLATE
    html = html.replace("{{DATE}}", day.strftime("%d %B %Y"))
    html = html.replace("{{DATE_ISO}}", day.isoformat())
    html = html.replace("{{CONTENT}}", article_content)
    html = html.replace("{{NB_MESSAGES}}", str(stats.get("messages", 0)))
    html = html.replace("{{NB_COMMITS}}", str(stats.get("commits", 0)))
    html = html.replace("{{NB_FILES}}", str(stats.get("files", 0)))
    return html


def update_index(articles_dir):
    index_path = articles_dir / "index.html"
    article_files = sorted([f for f in articles_dir.glob("????-??-??.html")], reverse=True)
    articles_list = ""
    for f in article_files:
        day_str = f.stem
        try:
            dt = datetime.fromisoformat(day_str)
            date_display = dt.strftime("%d %B %Y")
        except Exception:
            date_display = day_str
        try:
            content = f.read_text(encoding="utf-8")
            title_match = re.search(r"<h[12][^>]*>([^<]+)", content)
            title = title_match.group(1).strip() if title_match else date_display
        except Exception:
            title = date_display
        articles_list += (
            '        <article class="post-card">\n'
            '          <a href="/' + day_str + '.html" class="post-link">\n'
            '            <time datetime="' + day_str + '">' + date_display + '</time>\n'
            '            <h3>' + title + '</h3>\n'
            '          </a>\n'
            '        </article>\n'
        )
    index_html = INDEX_TEMPLATE.replace("{{ARTICLES_LIST}}", articles_list)
    index_path.write_text(index_html, encoding="utf-8")
    print(f"  ✓ index.html mis à jour ({len(article_files)} articles)")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nova-Blog daily generator")
    parser.add_argument("date", nargs="?", default=None, help="Date ISO (ex: 2026-04-22). Si absent = today.")
    args = parser.parse_args()

    now = datetime.now()
    if args.date:
        try:
            day = date.fromisoformat(args.date)
        except ValueError:
            print(f"Date invalide : {args.date} — utiliser ISO format (YYYY-MM-DD)")
            sys.exit(1)
    else:
        # Si on est avant 6h du mat, on considère qu'on est encore
        # dans la "nuit de transition" → générer pour la veille
        from datetime import timedelta
        if now.hour < DAY_START_HOUR:
            day = date.today() - timedelta(days=1)
        else:
            day = date.today()

    # Vérifier si l'article existe déjà
    article_path = ARTICLES_DIR / (day.isoformat() + ".html")
    if article_path.exists():
        print(f"\n  Article déjà existant pour {day.isoformat()} —SKIP")
        print(f"  → {article_path.name}")
        update_index(ARTICLES_DIR)
        return

    print(f"\n{'='*50}")
    print(f"  Nova-Blog — Génération du {day.isoformat()}")
    print(f"{'='*50}\n")

    # 1. Sessions Hermès
    print("  📡 Lecture des sessions Hermès...")
    all_messages = []
    # Include session_*.json, request_dump_*.json, and *.jsonl
    session_files = (
        sorted(list(SESSIONS_DIR.glob("session_*.json"))
               + list(SESSIONS_DIR.glob("request_dump_*.json"))
               + list(SESSIONS_DIR.glob("*.jsonl")),
              key=lambda p: p.stat().st_mtime, reverse=True)
    )
    for sf in session_files:
        msgs = parse_session_file(sf)
        today_msgs = filter_today_messages(msgs, day)
        all_messages.extend(today_msgs)

    seen_content = set()
    unique_messages = []
    for msg in all_messages:
        key = msg["content"][:80]
        if key not in seen_content:
            seen_content.add(key)
            unique_messages.append(msg)

    print(f"     → {len(unique_messages)} messages collectés")

    # 2. Git commits
    print("  💻 Scan des commits Git...")
    all_commits = []
    for repo in GIT_REPOS:
        commits = get_git_today(repo, day)
        all_commits.extend(commits)
    print(f"     → {len(all_commits)} commits collectés")

    # 3. Fichiers modifiés
    print("  📁 Scan des fichiers travaillés...")
    recent_files = get_recent_files(Path.home(), day)
    print(f"     → {len(recent_files)} fichiers collectés")

    sessions_text = "\n".join(
        f"[{m['role']}] {m['content']}" for m in unique_messages
    ) if unique_messages else "Aucun message aujourd'hui."

    git_text = "\n".join(
        (f"- [{c['repo']}] {c['hash']} — {c['message']}"
         + (f"  → {c['url']}" if c.get('url') else ""))
        for c in all_commits
    ) if all_commits else "Aucun commit aujourd'hui."

    files_text = "\n".join(
        f"- [{f['repo']}] {f['file']}" for f in recent_files
    ) if recent_files else "Aucun fichier."

    stats = {"messages": len(unique_messages), "commits": len(all_commits), "files": len(recent_files)}

    # 4. Génération
    print("\n  ✍️  Génération de l'article avec MiniMax...")
    try:
        article = summarize_content(sessions_text, git_text, files_text, day)
        article = clean_chinese_text(article)  # Nettoie les caracteres chinois/residus
        print("     → Article généré !")
    except Exception as e:
        print(f"     ✗ Erreur : {e}")
        article = f"<p>Erreur lors de la génération : {e}</p>"

    # 5. Sauvegarde
    ARTICLES_DIR.mkdir(exist_ok=True)
    article_path = ARTICLES_DIR / (day.isoformat() + ".html")
    html = build_article_html(article, day, stats)
    article_path.write_text(html, encoding="utf-8")
    print(f"\n  ✅ Article : {article_path.name}")

    update_index(ARTICLES_DIR)
    print(f"\n{'='*50}")
    print(f"  Done! → {article_path.name}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
