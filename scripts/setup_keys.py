#!/usr/bin/env python3
"""
Nova-Blog — Setup Keys
Script de bootstrap pour initialiser les clés API.

Usage:
    python3 scripts/setup_keys.py

Ce script:
  1. Lit ~/.hermes/auth.json pour extraire les clés ollama-cloud
  2. Teste chaque clé (celles avec status 'ok' ou null)
  3. Génère config.yaml.local avec les clés fonctionnelles

Ne push JAMAIS config.yaml.local sur GitHub — il est dans .gitignore.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import bootstrap_config

if __name__ == "__main__":
    bootstrap_config()
