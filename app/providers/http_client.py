"""
Client HTTP partagé avec retry + backoff automatique sur 429.
Utilisé par tous les providers cloud.
"""
import time
import logging
import httpx

logger = logging.getLogger("openchawn.http")

# Retry config — conservateur pour free tiers (20 RPM MiniMax, etc.)
MAX_RETRIES = 2
BACKOFF_SECONDS = [3.0, 8.0]  # 1er retry: 3s, 2ème: 8s


def post_with_retry(
    url: str,
    headers: dict,
    json_data: dict,
    timeout: float = 60.0,
    provider_name: str = "api",
) -> httpx.Response:
    """POST avec retry automatique sur 429 (rate limit).

    - 429 → retry avec backoff (max 2 essais, 3s puis 8s)
    - Respecte Retry-After header si présent (cap 15s)
    - Autres erreurs HTTP → raise immédiat, pas de retry
    - ConnectError → raise immédiat

    Returns: httpx.Response (succès)
    Raises: httpx.HTTPStatusError, httpx.ConnectError, Exception
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = httpx.post(url, headers=headers, json=json_data, timeout=timeout)

            if response.status_code < 400:
                if attempt > 0:
                    logger.info(f"[{provider_name}] OK après retry {attempt}")
                return response

            if response.status_code == 429:
                if attempt >= MAX_RETRIES:
                    logger.warning(f"[{provider_name}] 429 persistant après {MAX_RETRIES} retries — fallback")
                    response.raise_for_status()

                # Respecter Retry-After header (cap 15s)
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = min(float(retry_after), 15.0)
                    except ValueError:
                        wait = BACKOFF_SECONDS[attempt]
                else:
                    wait = BACKOFF_SECONDS[attempt]

                logger.info(f"[{provider_name}] 429 — attente {wait:.0f}s (retry {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue

            # Autre erreur HTTP (401, 500, etc.) → pas de retry
            response.raise_for_status()

        except httpx.HTTPStatusError:
            raise
        except httpx.ConnectError:
            raise
        except httpx.TimeoutException:
            logger.warning(f"[{provider_name}] timeout ({timeout}s)")
            raise
        except Exception as e:
            if attempt >= MAX_RETRIES:
                raise
            logger.warning(f"[{provider_name}] erreur inattendue: {e}, retry...")
            time.sleep(BACKOFF_SECONDS[attempt])

    raise RuntimeError(f"[{provider_name}] échec après retries")
