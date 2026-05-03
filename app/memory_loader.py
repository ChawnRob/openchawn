from pathlib import Path

BRAIN_PATH = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/openchawn-brain"

def load_obsidian_memory():
    notes = []

    if not BRAIN_PATH.exists():
        return {
            "status": "error",
            "message": f"Obsidian brain not found: {BRAIN_PATH}",
            "notes": []
        }

    for file in BRAIN_PATH.rglob("*.md"):
        try:
            notes.append({
                "title": file.stem,
                "path": str(file),
                "content": file.read_text(encoding="utf-8")
            })
        except Exception as e:
            notes.append({
                "title": file.stem,
                "path": str(file),
                "error": str(e)
            })

    return {
        "status": "ok",
        "count": len(notes),
        "notes": notes
    }
