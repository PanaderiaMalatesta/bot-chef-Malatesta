"""Facturas de clientes: se adjuntan por Telegram, el archivo queda en la carpeta
Drive del cliente y aqui se registra a que cotizacion corresponde.

Igual que la cotizacion, es un flujo de preguntas en Python: nada pasa por el LLM.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

from . import drive_clientes, mayorista
from .paths import DATA_DIR

FACTURAS_PATH = DATA_DIR / "facturas.csv"
_COLUMNAS = ["numero", "fecha", "rut", "cliente", "cotizacion", "archivo_id", "link", "extension", "registrada"]
_PATRON_SIN = re.compile(r"^\s*(sin(\s+cotizaci[oó]n)?|ninguna?|no|omitir)\s*[.!]*\s*$", re.IGNORECASE)
_PATRON_NUMERO = re.compile(r"^\s*(?:n[°º.]?\s*)?(\d{1,12})\s*$", re.IGNORECASE)
_EXTENSIONES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
MAX_BYTES = 20 * 1024 * 1024  # lo maximo que un bot puede descargar de Telegram


def _cargar() -> pd.DataFrame:
    if not FACTURAS_PATH.exists():
        return pd.DataFrame(columns=_COLUMNAS)
    return pd.read_csv(FACTURAS_PATH, dtype=str).reindex(columns=_COLUMNAS).fillna("")


def _guardar_tabla(df: pd.DataFrame) -> None:
    FACTURAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporal = FACTURAS_PATH.with_suffix(".tmp")
    df.to_csv(temporal, index=False)
    temporal.replace(FACTURAS_PATH)


def _es_de(fila: dict, rut: str, nombre: str) -> bool:
    return drive_clientes.clave_cliente(fila["rut"], fila["cliente"]) == drive_clientes.clave_cliente(rut, nombre)


def de_cliente(cliente: dict) -> list[dict]:
    return [f for f in _cargar().to_dict("records") if _es_de(f, cliente["rut"], cliente["cliente"])]


def _nombre_archivo(numero: str, cotizacion: str, extension: str) -> str:
    sufijo = f"_Cotizacion_{int(cotizacion):04d}" if cotizacion else ""
    return f"Factura_{numero}{sufijo}{extension}"


def _cotizacion_texto(c: dict) -> str:
    total = f" · {mayorista.fmt(c['total'])}" if c["total"] is not None else ""
    return f"N° {c['numero']:04d} · {c['fecha']}{total}"


def _lista_cotizaciones(cotizaciones: list[dict]) -> str:
    return "\n".join(_cotizacion_texto(c) for c in cotizaciones)


# --- Adjuntar una factura ------------------------------------------------------

def iniciar() -> dict:
    return {"preguntando": "cliente"}


def siguiente_pregunta(estado: dict) -> str:
    paso = estado["preguntando"]
    if paso == "cliente":
        return '¿De qué cliente es la factura? Escribe su nombre o RUT, o "cancelar".'
    if paso == "elegir_cliente":
        return ("Encontré estos clientes:\n" + mayorista.clientes_texto(estado["opciones"])
                + "\n\nResponde el número o escribe otro nombre.")
    if paso == "archivo":
        return f"Cliente: {estado['cliente']['cliente']}\n\nEnvíame la factura en PDF o como foto."
    if paso == "cotizacion":
        return ("¿A qué cotización corresponde?\n" + _lista_cotizaciones(estado["cotizaciones"])
                + '\n\nResponde su número (ej. "' + str(estado["cotizaciones"][0]["numero"]) + '") o "sin cotización".')
    if paso == "numero":
        return "¿Cuál es el número de la factura?"
    if paso == "fecha":
        return '¿Qué fecha tiene? Escríbela así: 02-11-2026, o "hoy".'
    return resumen(estado)


def resumen(estado: dict) -> str:
    cotizacion = f"N° {int(estado['cotizacion']):04d}" if estado["cotizacion"] else "sin cotización"
    return (f"Factura {estado['numero']}\nCliente: {estado['cliente']['cliente']}\nFecha: {estado['fecha']}\n"
            f'Cotización: {cotizacion}\n\n¿La guardo en Drive? Responde "sí" o "cancelar".')


def _elegir_cliente(estado: dict, cliente: dict) -> None:
    estado["cliente"] = cliente
    estado.pop("opciones", None)
    estado["preguntando"] = "archivo"


def _leer_fecha(texto: str) -> str | None:
    if re.fullmatch(r"\s*hoy\s*", texto, re.IGNORECASE):
        return date.today().strftime("%d-%m-%Y")
    try:
        return datetime.strptime(texto.strip().replace("/", "-"), "%d-%m-%Y").strftime("%d-%m-%Y")
    except ValueError:
        return None


def aplicar_respuesta(estado: dict, texto: str) -> str | None:
    """Guarda la respuesta del paso actual y avanza; devuelve un error si no sirve."""
    paso = estado["preguntando"]
    if paso == "elegir_cliente" and re.fullmatch(r"\s*\d{1,3}\s*", texto):
        if not 1 <= int(texto) <= len(estado["opciones"]):
            return f"Responde un número del 1 al {len(estado['opciones'])}, u otro nombre."
        _elegir_cliente(estado, estado["opciones"][int(texto) - 1])
    elif paso in ("cliente", "elegir_cliente"):
        encontrados = mayorista.consultar_clientes(texto)
        if not encontrados:
            return f'No encontré clientes parecidos a "{texto.strip()}". Prueba con otro nombre o RUT.'
        if len(encontrados) == 1:
            _elegir_cliente(estado, encontrados[0])
        else:
            estado["opciones"] = encontrados[:30]
            estado["preguntando"] = "elegir_cliente"
    elif paso == "archivo":
        return "Necesito el archivo: envíame la factura en PDF o como foto."
    elif paso == "cotizacion":
        if _PATRON_SIN.match(texto):
            estado["cotizacion"] = ""
        else:
            m = _PATRON_NUMERO.match(texto)
            if not m or int(m.group(1)) not in {c["numero"] for c in estado["cotizaciones"]}:
                return 'Responde el número de una cotización de la lista, o "sin cotización".'
            estado["cotizacion"] = str(int(m.group(1)))
        estado["preguntando"] = "numero"
    elif paso == "numero":
        m = _PATRON_NUMERO.match(texto)
        if not m:
            return "Escribe solo el número de la factura (ej. 1234)."
        numero = str(int(m.group(1)))
        cliente = estado["cliente"]
        if any(f["numero"] == numero for f in de_cliente(cliente)):
            return f"La factura {numero} ya está registrada para {cliente['cliente']}. Revisa el número o \"cancelar\"."
        estado["numero"] = numero
        estado["preguntando"] = "fecha"
    elif paso == "fecha":
        fecha = _leer_fecha(texto)
        if not fecha:
            return 'No reconozco esa fecha. Escríbela así: 02-11-2026, o "hoy".'
        estado["fecha"] = fecha
        estado["preguntando"] = "confirmacion"
    return None


def recibir_archivo(estado: dict, contenido: bytes, tipo: str) -> None:
    estado["contenido"] = contenido
    estado["tipo"] = tipo
    estado["cotizaciones"] = mayorista._cotizaciones_de(estado["cliente"]["cliente"])
    if estado["cotizaciones"]:
        estado["preguntando"] = "cotizacion"
    else:
        estado["cotizacion"] = ""
        estado["preguntando"] = "numero"


def guardar(estado: dict) -> str:
    """Sube el archivo y recien entonces lo registra. Lanza ErrorDrive si falla."""
    cliente = estado["cliente"]
    nombre = _nombre_archivo(estado["numero"], estado["cotizacion"], _EXTENSIONES[estado["tipo"]])
    subido = drive_clientes.subir_factura(estado["contenido"], nombre, estado["tipo"], cliente["rut"], cliente["cliente"])
    fila = {"numero": estado["numero"], "fecha": estado["fecha"], "rut": cliente["rut"], "cliente": cliente["cliente"],
            "cotizacion": estado["cotizacion"], "archivo_id": subido["id"], "link": subido.get("webViewLink", ""),
            "extension": _EXTENSIONES[estado["tipo"]], "registrada": date.today().isoformat()}
    _guardar_tabla(pd.concat([_cargar(), pd.DataFrame([fila])], ignore_index=True))
    return f"Listo, guardé la factura {estado['numero']} de {cliente['cliente']}.\n{fila['link']}".strip()


# --- Asociar despues una factura guardada sin cotizacion --------------------------

def iniciar_asociar() -> dict | None:
    pendientes = [f for f in _cargar().to_dict("records") if not f["cotizacion"]]
    return {"preguntando": "factura", "pendientes": pendientes[:30]} if pendientes else None


def siguiente_pregunta_asociar(estado: dict) -> str:
    if estado["preguntando"] == "factura":
        opciones = "\n".join(f"{i}. Factura {f['numero']} · {f['cliente']} · {f['fecha']}"
                             for i, f in enumerate(estado["pendientes"], start=1))
        return f'Facturas sin cotización:\n{opciones}\n\nResponde el número de la lista o "cancelar".'
    return (f"¿A qué cotización corresponde la factura {estado['factura']['numero']}?\n"
            + _lista_cotizaciones(estado["cotizaciones"]) + '\n\nResponde su número o "cancelar".')


def aplicar_asociar(estado: dict, texto: str) -> tuple[str | None, bool]:
    """Devuelve (mensaje, terminado). Lanza ErrorDrive si no se pudo renombrar."""
    m = _PATRON_NUMERO.match(texto)
    if estado["preguntando"] == "factura":
        if not m or not 1 <= int(m.group(1)) <= len(estado["pendientes"]):
            return f"Responde un número del 1 al {len(estado['pendientes'])}, o \"cancelar\".", False
        estado["factura"] = estado["pendientes"][int(m.group(1)) - 1]
        estado["cotizaciones"] = mayorista._cotizaciones_de(estado["factura"]["cliente"])
        if not estado["cotizaciones"]:
            return f"{estado['factura']['cliente']} todavía no tiene cotizaciones.", True
        estado["preguntando"] = "cotizacion"
        return None, False
    if not m or int(m.group(1)) not in {c["numero"] for c in estado["cotizaciones"]}:
        return 'Responde el número de una cotización de la lista, o "cancelar".', False
    factura, cotizacion = estado["factura"], str(int(m.group(1)))
    drive_clientes.renombrar(factura["archivo_id"], _nombre_archivo(factura["numero"], cotizacion, factura["extension"]))
    df = _cargar()
    df.loc[df["archivo_id"] == factura["archivo_id"], "cotizacion"] = cotizacion
    _guardar_tabla(df)
    return f"Listo: la factura {factura['numero']} quedó asociada a la cotización N° {int(cotizacion):04d}.", True
