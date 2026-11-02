"""Sincroniza los clientes del bot desde la planilla de Google Sheets.

Solo se lee la planilla y solo cuando alguien lo pide: se descarga, se compara y,
tras confirmar en el chat, sus datos reemplazan a los del bot. Cada cliente se
reconoce por su RUT. Los que estan solo en el bot se mantienen, para no perder
un cliente recien cotizado que aun no se copia a la planilla.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime

import google.auth.exceptions
import pandas as pd
import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from . import mayorista

_ALCANCE = "https://www.googleapis.com/auth/spreadsheets.readonly"
_URL_VALORES = "https://sheets.googleapis.com/v4/spreadsheets/{id}/values/A:Z"
_COLUMNAS = {"cliente": "cliente", "rut": "rut", "razon social": "razon_social", "contacto": "contacto"}
_CAMPOS = {"cliente": "nombre", "razon_social": "razón social", "contacto": "contacto"}
MAX_TEXTO_TELEGRAM = 3800


class ErrorPlanilla(Exception):
    """Mensaje para el usuario; nada se reemplaza si ocurre."""


@dataclass
class Comparacion:
    filas: list[dict]
    nuevos: list[dict] = field(default_factory=list)
    cambios: list[tuple[dict, dict]] = field(default_factory=list)
    solo_bot: list[dict] = field(default_factory=list)
    sin_rut: list[str] = field(default_factory=list)

    @property
    def hay_cambios(self) -> bool:
        return bool(self.nuevos or self.cambios)


def descargar_filas() -> list[list[str]]:
    id_planilla = os.environ.get("CLIENTES_SHEET_ID", "")
    credencial = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not id_planilla or not credencial:
        raise ErrorPlanilla("La conexión con la planilla todavía no está configurada.")
    try:
        cuenta = service_account.Credentials.from_service_account_info(json.loads(credencial), scopes=[_ALCANCE])
        cuenta.refresh(Request())
        respuesta = requests.get(_URL_VALORES.format(id=id_planilla), timeout=30,
                                 headers={"Authorization": f"Bearer {cuenta.token}"})
    except (ValueError, google.auth.exceptions.GoogleAuthError, requests.RequestException) as exc:
        raise ErrorPlanilla("No pude conectarme con la planilla. No cambié nada.") from exc
    if respuesta.status_code in (403, 404):
        raise ErrorPlanilla("No tengo acceso a la planilla. Revisa que esté compartida con la cuenta del bot.")
    if not respuesta.ok:
        raise ErrorPlanilla("Google no entregó la planilla. No cambié nada; inténtalo de nuevo más tarde.")
    return respuesta.json().get("values", [])


def _limpiar(valor: str) -> str:
    return " ".join(str(valor).split())


def interpretar_filas(filas: list[list[str]]) -> tuple[list[dict], list[str]]:
    """Valida la planilla completa antes de usarla: un RUT malo o repetido detiene
    la sincronizacion, para no reemplazar datos con una planilla dañada."""
    if not filas:
        raise ErrorPlanilla("La planilla está vacía. No cambié nada.")
    encabezados = {mayorista._normalizar(c).strip(): i for i, c in enumerate(filas[0])}
    faltan = [c for c in _COLUMNAS if c not in encabezados]
    if faltan:
        raise ErrorPlanilla(f"A la planilla le faltan columnas ({', '.join(faltan)}). No cambié nada.")

    clientes, sin_rut, ruts = [], [], set()
    for n, fila in enumerate(filas[1:], start=2):
        datos = {campo: _limpiar(fila[encabezados[col]]) if encabezados[col] < len(fila) else ""
                 for col, campo in _COLUMNAS.items()}
        if not any(datos.values()):
            continue
        if not datos["rut"]:
            sin_rut.append(datos["cliente"] or f"fila {n}")
            continue
        rut, error = mayorista.normalizar_rut(datos["rut"])
        if error:
            raise ErrorPlanilla(f"Fila {n}: el RUT \"{datos['rut']}\" no es válido. No cambié nada.")
        if rut in ruts:
            raise ErrorPlanilla(f"Fila {n}: el RUT {rut} está repetido. No cambié nada.")
        if not datos["cliente"]:
            raise ErrorPlanilla(f"Fila {n}: falta el nombre del cliente. No cambié nada.")
        ruts.add(rut)
        clientes.append({**datos, "rut": rut})
    if not clientes:
        raise ErrorPlanilla("La planilla no tiene clientes con RUT. No cambié nada.")
    return clientes, sin_rut


def comparar(filas: list[list[str]]) -> Comparacion:
    clientes, sin_rut = interpretar_filas(filas)
    actuales = {c["rut"]: c for c in mayorista._cargar_clientes().to_dict("records")}
    resultado = Comparacion(filas=clientes, sin_rut=sin_rut)
    for cliente in clientes:
        actual = actuales.get(cliente["rut"])
        if actual is None:
            resultado.nuevos.append(cliente)
        elif any(_limpiar(actual[c]) != cliente[c] for c in _CAMPOS):
            resultado.cambios.append((actual, cliente))
    ruts = {c["rut"] for c in clientes}
    resultado.solo_bot = [c for rut, c in actuales.items() if rut not in ruts]
    return resultado


def comparacion_texto(c: Comparacion) -> str:
    lineas = [f"Comparé la planilla con el bot: {len(c.nuevos)} nuevos y {len(c.cambios)} con cambios."]
    if c.nuevos:
        lineas += ["", "Nuevos:"] + [f"- {n['cliente']} (RUT {n['rut']})" for n in c.nuevos]
    if c.cambios:
        lineas += ["", "Cambios (bot → planilla):"]
        for actual, nuevo in c.cambios:
            lineas.append(f"- RUT {nuevo['rut']}")
            lineas += [f"  {nombre}: {actual[campo] or 'vacío'} → {nuevo[campo] or 'vacío'}"
                       for campo, nombre in _CAMPOS.items() if _limpiar(actual[campo]) != nuevo[campo]]
    if c.solo_bot:
        lineas += ["", "Solo en el bot (se mantienen):"] + [f"- {s['cliente']} (RUT {s['rut']})" for s in c.solo_bot]
    if c.sin_rut:
        lineas += ["", "Sin RUT en la planilla (no se cargan):"] + [f"- {s}" for s in c.sin_rut]
    if not c.hay_cambios:
        lineas += ["", "No hay nada que reemplazar."]
        return "\n".join(lineas)[:MAX_TEXTO_TELEGRAM]
    pie = '\n\n¿Reemplazo los datos del bot? Responde "sí" o "cancelar".'
    return "\n".join(lineas)[:MAX_TEXTO_TELEGRAM - len(pie)] + pie


def reemplazar(c: Comparacion) -> str:
    """Aplica lo mostrado, con respaldo previo. Un cliente sin cambios conserva su
    fecha, y los creados mientras se esperaba la confirmacion no se pierden."""
    actuales = {f["rut"]: f for f in mayorista._cargar_clientes().to_dict("records")}
    hoy = date.today().isoformat()
    filas = []
    for cliente in c.filas:
        actual = actuales.pop(cliente["rut"], None)
        igual = actual is not None and all(_limpiar(actual[campo]) == cliente[campo] for campo in _CAMPOS)
        filas.append(actual if igual else {**cliente, "actualizado": hoy})
    filas.extend(actuales.values())

    ruta = mayorista.CLIENTES_PATH
    respaldo = ruta.with_name(f"{ruta.stem}.bak_{datetime.now():%Y%m%d_%H%M%S}{ruta.suffix}")
    if ruta.exists():
        shutil.copy2(ruta, respaldo)
    temporal = ruta.with_suffix(".tmp")
    pd.DataFrame(filas, columns=mayorista._COLUMNAS_CLIENTES).to_csv(temporal, index=False)
    temporal.replace(ruta)
    return f"Listo: {len(c.nuevos)} nuevos y {len(c.cambios)} actualizados. Dejé un respaldo de los datos anteriores."
