import logging

from app.providers.base import BaseProvider
from app.provider_manager import get_provider_manager

logger = logging.getLogger("openchawn.selector")


def select_providers() -> list[tuple[str, BaseProvider]]:
    """Ordre défini par ProviderManager, intersecté avec le registry chargé."""
    from app.router import get_registry

    pm = get_provider_manager()
    reg = get_registry()
    out: list[tuple[str, BaseProvider]] = []
    for name in pm.resolution_order():
        prov = reg.get(name)
        if not prov:
            continue
        try:
            if hasattr(prov, "is_available") and not prov.is_available():
                continue
        except Exception:
            continue
        out.append((name, prov))

    if not out:
        logger.warning("Aucun provider registry disponible après filtrage")

    return out
