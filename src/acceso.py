"""Control de acceso del bot: pide la clave (env var BOT_CLAVE) una vez por
cuenta de Telegram.

Las cuentas autorizadas se guardan en el Volume para que un redeploy no obligue
a escribir la clave de nuevo. Sin BOT_CLAVE configurada nadie entra: es
preferible un bot cerrado a uno abierto por un error de configuracion.
"""
from __future__ import annotations

import hmac
import os
import time

from .paths import DATA_DIR

AUTORIZADOS_PATH = DATA_DIR / "usuarios_autorizados.txt"

MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 15 * 60

# En memoria a proposito: un reinicio solo limpia los contadores de intentos.
_intentos: dict[int, int] = {}
_bloqueado_hasta: dict[int, float] = {}


def esta_autorizado(user_id: int) -> bool:
    if not AUTORIZADOS_PATH.exists():
        return False
    return str(user_id) in AUTORIZADOS_PATH.read_text(encoding="utf-8").split()


def _autorizar(user_id: int) -> None:
    AUTORIZADOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUTORIZADOS_PATH.open("a", encoding="utf-8") as archivo:
        archivo.write(f"{user_id}\n")


def intentar_clave(user_id: int, texto: str | None) -> str:
    """Evalua un mensaje de alguien no autorizado. Devuelve "correcta",
    "incorrecta", "bloqueado", "pedir" (no mando texto) o "sin_clave"."""
    clave = os.environ.get("BOT_CLAVE", "")
    if not clave:
        return "sin_clave"
    if time.monotonic() < _bloqueado_hasta.get(user_id, 0):
        return "bloqueado"
    if texto is None:
        return "pedir"
    if hmac.compare_digest(texto.strip().encode("utf-8"), clave.encode("utf-8")):
        _intentos.pop(user_id, None)
        _bloqueado_hasta.pop(user_id, None)
        _autorizar(user_id)
        return "correcta"
    _intentos[user_id] = _intentos.get(user_id, 0) + 1
    if _intentos[user_id] >= MAX_INTENTOS:
        _intentos.pop(user_id)
        _bloqueado_hasta[user_id] = time.monotonic() + BLOQUEO_SEGUNDOS
        return "bloqueado"
    return "incorrecta"
