#!/usr/bin/env python3
"""
Nova-Blog — Config Loader
Charge la configuration depuis config.yaml (priorité haute).
Si les clés ollama-cloud ne sont pas definies, tente de les recuperer depuis auth.json d'Hermes.
Genere config.yaml.local au premier lancement.
"""

import json, os, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BLOG_DIR    = Path(__file__).parent.parent
CONFIG_FILE = BLOG_DIR / "config.yaml"
CONFIG_LOCAL = BLOG_DIR / "config.yaml.local"
AUTH_JSON   = Path.home() / ".hermes" / "auth.json"


# ── YAML (stdlib) ─────────────────────────────────────────────────────────────

try:
    import yaml  # pip install pyyaml / standard en pratique
    def load_yaml(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    def save_yaml(data: dict, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    def load_yaml(path: Path) -> dict:
        raise RuntimeError("PyYAML requis. pip install pyyaml")
    def save_yaml(data: dict, path: Path) -> None:
        raise RuntimeError("PyYAML requis. pip install pyyaml")


# ── Auth JSON Hermes ──────────────────────────────────────────────────────────

def load_auth() -> dict:
    if not AUTH_JSON.exists():
        return {}
    with open(AUTH_JSON) as f:
        return json.load(f)


def get_ollama_cloud_creds() -> list[dict]:
    """
    Lit auth.json et retourne les clés ollama-cloud avec last_status.
    Les clés sont dans 'credential_pool', pas dans 'providers'.
    Les clés sont MASQUEES dans auth.json (affichage tronqué) donc on
    ne peut pas les utiliser directement — on lit juste les métadonnées.
    """
    auth = load_auth()
    pool = auth.get("credential_pool", {})
    ollama_cloud = pool.get("ollama-cloud", [])
    return [
        {
            "id": k["id"],
            "label": k.get("label", ""),
            "status": k.get("last_status"),
            "base_url": k.get("base_url", "https://ollama.com/v1"),
            "api_key": k.get("access_token", ""),
        }
        for k in ollama_cloud
    ]


# ── Test de clé ───────────────────────────────────────────────────────────────

def test_ollama_key(api_key: str, base_url: str = "https://ollama.com/v1",
                    model: str = "minimax-m2.7", timeout: int = 30) -> tuple[bool, str]:
    """
    Teste une clé Ollama Cloud avec un appel minimal.
    Retourne (True, "ok") si la clé fonctionne.
    Retourne (False, "rate_limited") si 429 (weekly limit).
    Retourne (False, "error_reason") sinon.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 5,
    }
    data = json.dumps(payload).encode()
    req = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            result = json.load(resp)
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return True, "ok"
    except HTTPError as e:
        if e.code == 429:
            body = e.read().decode(errors="replace")
            if "weekly usage limit" in body:
                return False, "rate_limited"
            return False, f"http_429:{body[:100]}"
        return False, f"http_{e.code}"
    except (URLError, OSError) as e:
        return False, f"network:{e}"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return False, f"parse:{e}"


# ── Config loader principal ────────────────────────────────────────────────────

def load_config() -> dict:
    """
    Charge config.yaml (ou config.yaml.local).
    Raise une erreur si aucune config trouvée.
    """
    for cfg_path in [CONFIG_LOCAL, CONFIG_FILE]:
        if cfg_path.exists():
            return load_yaml(cfg_path)
    raise FileNotFoundError(
        f"Pas de config — copie config.yaml.example vers config.yaml "
        f"et lance python3 scripts/setup_keys.py"
    )


def get_working_ollama_key(config: dict = None) -> tuple[str, str]:
    """
    Retourne (api_key, base_url) de la première clé ollama-cloud fonctionnelle.
    Lit config.yaml -> si api_key vide/null, essaie setup_keys.py d'abord.
    """
    if config is None:
        config = load_config()

    # 1) Clé explicite dans config
    ollama = config.get("ollama", {})
    key = ollama.get("api_key", "").strip()
    base_url = ollama.get("base_url", "https://ollama.com/v1").strip()
    if key:
        return key, base_url

    # 2) Clés multiples dans ollama_cloud_keys
    cloud_keys = config.get("ollama_cloud_keys", [])
    for ck in cloud_keys:
        k = ck.get("api_key", "").strip()
        if k:
            ok = test_ollama_key(k, ck.get("base_url", base_url))
            if ok:
                return k, ck.get("base_url", base_url)

    # 3) Rien ne marche — erreur claire
    raise RuntimeError(
        "Aucune clé ollama-cloud fonctionnelle trouvée.\n"
        "Lance: python3 scripts/setup_keys.py\n"
        "Cela va tester les clés depuis auth.json et générer config.yaml.local"
    )


# ── Setup / bootstrap ────────────────────────────────────────────────────────

def bootstrap_config():
    """
    Lis auth.json, affiche les clés ollama-cloud avec leur status,
    genere config.yaml.local avec les clés fonctionnelles.
    """
    print("=== Nova-Blog — Setup Keys ===\n")

    creds = get_ollama_cloud_creds()
    if not creds:
        print("Aucune clé ollama-cloud dans ~/.hermes/auth.json")
        return

    print("Clés ollama-cloud dans auth.json:\n")
    working = []
    for c in creds:
        label = c["label"] or c["id"]
        status = c["status"] or "unknown"
        base = c["base_url"]
        masked = "(masquée — clé non accessible depuis auth.json)"
        print(f"  [{status:10}] {label:30} {base}")

        # Tester uniquement celles avec status ok ou null
        if c["status"] in ("ok", None):
            # status=null = pas encore testée
            # On ne peut pas tester les clés masquées directement.
            # On note juste qu'elle est "candidates" et on les inclut
            # pour que l'utilisateur vérifie manuellement.
            working.append(c)

    print(f"\n{len(creds)} clé(s) détectées dans auth.json.\n")

    if not creds:
        print("Aucune clé ollama-cloud dans ~/.hermes/auth.json")
        return

    # Test de toutes les clés non-vides
    tested_ok = []
    rate_limited = []
    for c in creds:
        key = c.get("api_key", "")
        if not key or len(key) < 10:
            print(f"  SKIP {c['label']} — clé vide ou illisible")
            continue
        print(f"  Test {c['label']}...", end=" ", flush=True)
        ok, reason = test_ollama_key(key, c["base_url"])
        if ok:
            print("OK ✓")
            tested_ok.append(c)
        elif reason == "rate_limited":
            print(f"RATE LIMIT (week.ly atteint)")
            rate_limited.append(c)
        else:
            print(f"FAIL ({reason})")

    if tested_ok:
        # Génère config.yaml.local
        local_cfg = {
            "ollama": {
                "base_url": tested_ok[0]["base_url"],
                "model": "minimax-m2.7",
                "api_key": tested_ok[0]["api_key"],
            },
            "minimax": {"api_key": ""},
            "ollama_cloud_keys": [
                {
                    "label": c["label"],
                    "api_key": c["api_key"],
                    "base_url": c["base_url"],
                }
                for c in tested_ok
            ],
        }

        # Écrit le header manuellement, puis save_yaml pour le body
        header = (
            "# Nova-Blog — Configuration locale (NE PAS PUSH SUR GIT)\n"
            "# Généré automatiquement par setup_keys.py\n\n"
        )
        with open(CONFIG_LOCAL, "w", encoding="utf-8") as f:
            f.write(header)
        save_yaml(local_cfg, CONFIG_LOCAL)

        print(f"\n✓ config.yaml.local généré avec {len(tested_ok)} clé(s) fonctionnelle(s).")
        print("Relance ton script (backfill.py ou daily_blog.py).")
    else:
        print(f"\n✗ Aucune clé fonctionnelle.")
        if rate_limited:
            print(f"  {len(rate_limited)} clé(s) à cours de quota weekly.")
            print(f"  Toutes les autres clés ont échoué pour une autre raison.")


if __name__ == "__main__":
    bootstrap_config()
