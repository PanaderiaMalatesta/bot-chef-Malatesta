"""Sincroniza clientes, recetas e insumos desde las planillas dos veces al dia.

Sin nadie que confirme, solo se aplica lo nuevo o modificado. Las eliminaciones
siempre esperan autorizacion en la sincronizacion manual, y un dato invalido deja
esa planilla sin cambios. Solo se avisa si paso algo.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import planilla_clientes, planilla_recetas
from .paths import DATA_DIR

HORAS = (7, 19)
ZONA = ZoneInfo("America/Santiago")
CHAT_AVISOS_PATH = DATA_DIR / "chat_avisos.txt"


def proxima_ejecucion(ahora: datetime) -> datetime:
    for dias in range(2):
        dia = ahora.date() + timedelta(days=dias)
        for hora in HORAS:
            candidata = datetime(dia.year, dia.month, dia.day, hora, tzinfo=ZONA)
            if candidata > ahora:
                return candidata
    raise AssertionError("HORAS no puede estar vacio")


def guardar_chat_avisos(chat_id: int) -> None:
    CHAT_AVISOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHAT_AVISOS_PATH.write_text(str(chat_id), encoding="utf-8")


def _chat_avisos() -> int | None:
    return int(CHAT_AVISOS_PATH.read_text(encoding="utf-8")) if CHAT_AVISOS_PATH.exists() else None


def _clientes() -> list[str]:
    c = planilla_clientes.comparar(planilla_clientes.descargar_filas())
    lineas = []
    if c.nuevos or c.cambios:
        lineas.append(planilla_clientes.reemplazar(c, con_eliminaciones=False))
    if c.solo_bot:
        lineas.append(f"{len(c.solo_bot)} clientes ya no están en la planilla. Para autorizar su eliminación: "
                      "/sincronizarclientes")
    return lineas


def _recetas() -> list[str]:
    c = planilla_recetas.comparar(*planilla_recetas.descargar())
    lineas = []
    if c.hay_aplicables:
        lineas.append(planilla_recetas.reemplazar(c, con_eliminaciones=False))
    else:
        planilla_recetas.registrar_base(c, pendientes=True)
    if c.eliminadas or c.insumos_eliminados:
        lineas.append(f"{len(c.eliminadas)} recetas y {len(c.insumos_eliminados)} insumos ya no están en la planilla. "
                      "Para autorizar su eliminación: /sincronizarrecetas")
    return lineas


def ejecutar() -> str | None:
    """Devuelve el aviso para el chat, o None si no hubo novedades."""
    secciones = []
    for titulo, sincronizar in (("Clientes", _clientes), ("Recetas e insumos", _recetas)):
        try:
            lineas = sincronizar()
        except planilla_clientes.ErrorPlanilla as exc:
            lineas = [str(exc)]
        except Exception:  # noqa: BLE001
            logging.exception("Fallo la sincronizacion automatica de %s", titulo)
            lineas = ["Falló la sincronización; no se aplicó el resto. Revisa los registros del bot."]
        if lineas:
            secciones.append(f"{titulo}:\n" + "\n".join(lineas))
    return "Sincronización automática\n\n" + "\n\n".join(secciones) if secciones else None


async def bucle(app) -> None:
    while True:
        ahora = datetime.now(ZONA)
        await asyncio.sleep((proxima_ejecucion(ahora) - ahora).total_seconds())
        aviso = await asyncio.to_thread(ejecutar)
        chat = _chat_avisos()
        if aviso and chat:
            try:
                await app.bot.send_message(chat, aviso)
            except Exception:  # noqa: BLE001
                logging.exception("No se pudo enviar el aviso de sincronizacion")
        elif aviso:
            logging.info("Sincronizacion automatica sin chat de avisos: %s", aviso)
