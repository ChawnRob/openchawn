"""Politique de langue runtime unique (anglais) — source de vérité pour prompts système OpenChawn."""

from __future__ import annotations

# Remplace les anciennes règles prototype « français obligatoire ».
OPENCHAWN_RUNTIME_LANGUAGE_POLICY_EN = (
    "Language policy: answer in the language determined by response_language_mode. "
    "Default mode is auto, meaning the dominant language of the latest user message. "
    "Explicit translation and explicit language requests override auto. "
    "Never force French by default."
)
