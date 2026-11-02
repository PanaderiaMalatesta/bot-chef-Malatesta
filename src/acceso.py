"""Control de acceso del bot: pide la clave (env var BOT_CLAVE) por cuenta de
Telegram, y la sesion dura 24 horas.

Las sesiones (user_id y hora de ingreso) se guardan en el Volume para que un
redeploy no obligue a escribir la clave de nuevo. Sin BOT_CLAVE configurada
nadie entra: es preferible un bot cerrado a uno abierto por un error de
configuracion.
"""
from __future__ import annotations

import hmac
import os
import time

from .paths import DATA_DIR

AUTORIZADOS_PATH = DATA_DIR / "usuarios_autorizados.txt"

MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 15 * 60
SESION_SEGUNDOS = 24 * 60 * 60

# En memoria a proposito: un reinicio solo limpia los contadores de intentos.
_intentos: dict[int, int] = {}
_bloqueado_hasta: dict[int, float] = {}
# Quienes ya recibieron el aviso: su primer mensaje no es un intento de clave.
_avisados: set[int] = set()


def _sesiones_vigentes() -> dict[int, float]:
    """user_id -> hora de ingreso. Ignora sesiones vencidas y lineas sin hora."""
    if not AUTORIZADOS_PATH.exists():
        return {}
    ahora = time.time()
    sesiones = {}
    for linea in AUTORIZADOS_PATH.read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if len(partes) == 2 and ahora - float(partes[1]) < SESION_SEGUNDOS:
            sesiones[int(partes[0])] = float(partes[1])
    return sesiones


def esta_autorizado(user_id: int) -> bool:
    return user_id in _sesiones_vigentes()


def _autorizar(user_id: int) -> None:
    sesiones = _sesiones_vigentes()
    sesiones[user_id] = time.time()
    _guardar_sesiones(sesiones)


def _guardar_sesiones(sesiones: dict[int, float]) -> None:
    AUTORIZADOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporal = AUTORIZADOS_PATH.with_suffix(".tmp")
    temporal.write_text("".join(f"{u} {t}\n" for u, t in sesiones.items()), encoding="utf-8")
    temporal.replace(AUTORIZADOS_PATH)


def cerrar_sesion(user_id: int) -> None:
    sesiones = _sesiones_vigentes()
    sesiones.pop(user_id, None)
    _guardar_sesiones(sesiones)


def intentar_clave(user_id: int, texto: str | None) -> str:
    """Evalua un mensaje de alguien no autorizado. Devuelve "correcta",
    "incorrecta", "bloqueado", "pedir" (no mando texto) o "sin_clave"."""
    clave = os.environ.get("BOT_CLAVE", "")
    if not clave:
        return "sin_clave"
    if time.monotonic() < _bloqueado_hasta.get(user_id, 0):
        return "bloqueado"
    if texto is None:
        _avisados.add(user_id)
        return "pedir"
    if hmac.compare_digest(texto.strip().encode("utf-8"), clave.encode("utf-8")):
        _intentos.pop(user_id, None)
        _bloqueado_hasta.pop(user_id, None)
        # asi, cuando venza la sesion, su primer mensaje vuelve a pedir la clave
        _avisados.discard(user_id)
        _autorizar(user_id)
        return "correcta"
    if user_id not in _avisados:
        _avisados.add(user_id)
        return "pedir"
    _intentos[user_id] = _intentos.get(user_id, 0) + 1
    if _intentos[user_id] >= MAX_INTENTOS:
        _intentos.pop(user_id)
        _bloqueado_hasta[user_id] = time.monotonic() + BLOQUEO_SEGUNDOS
        return "bloqueado"
    return "incorrecta"
