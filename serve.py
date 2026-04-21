#!/usr/bin/env python3
"""
Nova-Blog Web Server
Sert les articles HTML statiques sur http://localhost:5060
Usage : python3 serve.py          (démarre le serveur)
        python3 serve.py --port 6060  (port personnalisé)
        python3 serve.py --build      (build + démarre)
"""

import argparse
import logging
import os
import mimetypes
from pathlib import Path
from datetime import datetime
import http.server
import socketserver

# ── CONFIG ────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent.resolve()
ARTICLES_DIR = BASE_DIR / "articles"
STATIC_DIR   = BASE_DIR / "assets"
PORT     = 5056
HOST     = "0.0.0.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [nova-blog] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("nova-blog.serve")


# ── HANDLER ───────────────────────────────────────────────────────────────────

class NovaBlogHandler(http.server.SimpleHTTPRequestHandler):
    """Sert les articles et assets du blog. Route / → index.html des archives."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        path = self.path.strip("/")

        # Route / → index.html
        if not path or path == "index.html":
            return self.serve_index()

        # Assets statiques
        if path.startswith("assets/"):
            return super().do_GET()

        # Article par date: /2026-04-21 → articles/2026-04-21.html
        article_match = self._match_article(path)
        if article_match:
            return self.serve_article(article_match)

        # Liste des articles → /articles/
        if path == "articles" or path.startswith("articles/"):
            # Retirer "articles/" pour servir le fichier
            rest = path[len("articles/"):] if len(path) > len("articles/") else ""
            if not rest:
                return self.serve_index()
            # Delegating to parent for static files
            return super().do_GET()

        # Inconnu → index
        return self.serve_index()

    def _match_article(self, path):
        """Reconnaît /YYYY-MM-DD, YYYY-MM-DD.html ou /YYYY-MM-DD.html."""
        import re
        # Retire .html si présent
        path = re.sub(r'\.html$', '', path)
        m = re.match(r"^(\d{4}-\d{2}-\d{2})$", path)
        if m:
            return m.group(1)
        return None

    def serve_index(self):
        """Sert articles/index.html."""
        index_path = ARTICLES_DIR / "index.html"
        if index_path.exists():
            self.send_path(index_path)
        else:
            self.send_error(404, "Index not found — run the blog generator first")

    def serve_article(self, date_str):
        """Sert un article spécifique."""
        article_path = ARTICLES_DIR / f"{date_str}.html"
        if article_path.exists():
            self.send_path(article_path)
        else:
            self.send_error(404, f"Article {date_str} not found")

    def send_path(self, path):
        """Envoie un fichier HTML."""
        with open(path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "public, max-age=60")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} — {args[0]}")


# ── SERVER ────────────────────────────────────────────────────────────────────

def start_server(port=PORT, host=HOST):
    logger.info(f"Démarrage du serveur → http://{host}:{port}")
    logger.info(f"Articles : {ARTICLES_DIR}")

    # Créer index si absent
    if not (ARTICLES_DIR / "index.html").exists():
        logger.warning("index.html absent — les articles existent-ils ?")

    os.chdir(BASE_DIR)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), NovaBlogHandler) as httpd:
        logger.info(f"Nova-Blog est joignable sur http://localhost:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Arrêt du serveur.")


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nova-Blog Web Server")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port d'écoute (défaut: {PORT})")
    parser.add_argument("--host", default=HOST, help=f"Host (défaut: {HOST})")
    args = parser.parse_args()

    logger.info(f"Serveur Nova-Blog sur http://{args.host}:{args.port}")
    start_server(port=args.port, host=args.host)
