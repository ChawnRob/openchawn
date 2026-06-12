"""Obsidian URI handoff — no vault write claim."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from app.integrations.obsidian.markdown_builder import note_path_for_folder


def build_obsidian_new_uri(
    *,
    vault: str = "",
    note_path: str,
    markdown: str,
) -> str:
    params: list[tuple[str, str]] = []
    if vault:
        params.append(("vault", vault))
    if note_path:
        params.append(("name", note_path))
    if markdown:
        params.append(("content", markdown))
    if not params:
        return "obsidian://new"
    return "obsidian://new?" + urlencode(params, quote_via=quote)


def build_uri_handoff(
    *,
    title: str,
    markdown: str,
    folder: str,
    vault: str = "",
) -> dict[str, str]:
    note_path = note_path_for_folder(folder, title)
    uri = build_obsidian_new_uri(vault=vault, note_path=note_path, markdown=markdown)
    return {
        "mode": "uri_handoff",
        "note_path": note_path,
        "uri": uri,
        "markdown": markdown,
    }
