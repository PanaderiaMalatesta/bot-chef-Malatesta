"""Guarda en Google Drive las cotizaciones y facturas de cada cliente.

Sube en nombre de la cuenta de la panaderia (autorizacion OAuth con alcance
drive.file: solo ve lo que el propio bot creo), porque una cuenta de servicio no
tiene espacio para guardar archivos en un Gmail normal. Cada carpeta de cliente
se reconoce por una propiedad con su RUT, asi un cambio de nombre no la duplica.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import google.auth.exceptions
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from . import mayorista
from .paths import DATA_DIR

_ALCANCE = "https://www.googleapis.com/auth/drive.file"
_URL_TOKEN = "https://oauth2.googleapis.com/token"
_URL_ARCHIVOS = "https://www.googleapis.com/drive/v3/files"
_URL_SUBIDA = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink"
_TIPO_CARPETA = "application/vnd.google-apps.folder"
_LIMITE_PROPIEDAD = 100
NOMBRE_RAIZ = "Clientes Malatesta"

# Solo para mostrar el link en la ficha sin llamar a Google.
CARPETAS_PATH = DATA_DIR / "carpetas_clientes.json"

_credenciales: Credentials | None = None


class ErrorDrive(Exception):
    """Drive no respondio o rechazo la operacion."""


def configurado() -> bool:
    return all(os.environ.get(v) for v in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                                           "GOOGLE_OAUTH_REFRESH_TOKEN"))


def _token() -> str:
    global _credenciales
    if not configurado():
        raise ErrorDrive("Drive no está configurado")
    if _credenciales is None:
        _credenciales = Credentials(None, refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"], token_uri=_URL_TOKEN,
                                    client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
                                    client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"], scopes=[_ALCANCE])
    if not _credenciales.valid:
        try:
            _credenciales.refresh(Request())
        except google.auth.exceptions.GoogleAuthError as exc:
            raise ErrorDrive("Google rechazó la autorización") from exc
    return _credenciales.token


def _api(metodo: str, url: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {_token()}", **kwargs.pop("headers", {})}
    try:
        respuesta = requests.request(metodo, url, headers=headers, timeout=60, **kwargs)
    except requests.RequestException as exc:
        raise ErrorDrive("No pude conectarme con Drive") from exc
    if not respuesta.ok:
        logging.warning("Drive respondio %s en %s %s", respuesta.status_code, metodo, url.split("?")[0])
        raise ErrorDrive(f"Drive respondió {respuesta.status_code}")
    return respuesta.json() if respuesta.content else {}


def _texto_consulta(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace("'", "\\'")


def _buscar(consulta: str) -> list[dict]:
    datos = _api("GET", _URL_ARCHIVOS, params={"q": f"{consulta} and trashed=false", "fields": "files(id,webViewLink)",
                                               "pageSize": 10})
    return datos.get("files", [])


def _crear_carpeta(nombre: str, padre: str | None = None, propiedades: dict | None = None) -> str:
    cuerpo = {"name": nombre, "mimeType": _TIPO_CARPETA, "parents": [padre] if padre else [],
              "appProperties": propiedades or {}}
    return _api("POST", _URL_ARCHIVOS, json=cuerpo, params={"fields": "id"})["id"]


def _por_propiedad(clave: str, valor: str) -> str:
    return f"appProperties has {{ key='{clave}' and value='{_texto_consulta(valor)}' }} and mimeType='{_TIPO_CARPETA}'"


def _carpeta_raiz() -> str:
    encontradas = _buscar(_por_propiedad("rol", "raiz"))
    return encontradas[0]["id"] if encontradas else _crear_carpeta(NOMBRE_RAIZ, propiedades={"rol": "raiz"})


def clave_cliente(rut: str, nombre: str) -> str:
    return rut or f"nombre:{mayorista._normalizar(nombre).strip()}"[:_LIMITE_PROPIEDAD]


def _carpeta_cliente(rut: str, nombre: str) -> str:
    clave = clave_cliente(rut, nombre)
    encontradas = _buscar(_por_propiedad("cliente", clave))
    if encontradas:
        carpeta = encontradas[0]["id"]
    else:
        titulo = f"{nombre} - {rut}" if rut else nombre
        carpeta = _crear_carpeta(titulo, _carpeta_raiz(), {"cliente": clave})
    _recordar_carpeta(clave, carpeta)
    return carpeta


def _subcarpeta(padre: str, nombre: str) -> str:
    encontradas = _buscar(f"name='{nombre}' and '{padre}' in parents and mimeType='{_TIPO_CARPETA}'")
    return encontradas[0]["id"] if encontradas else _crear_carpeta(nombre, padre)


def _cargar_carpetas() -> dict[str, str]:
    return json.loads(CARPETAS_PATH.read_text(encoding="utf-8")) if CARPETAS_PATH.exists() else {}


def _recordar_carpeta(clave: str, carpeta: str) -> None:
    carpetas = _cargar_carpetas()
    if carpetas.get(clave) != carpeta:
        carpetas[clave] = carpeta
        CARPETAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CARPETAS_PATH.write_text(json.dumps(carpetas, ensure_ascii=False), encoding="utf-8")


def link_carpeta(cliente: dict) -> str:
    carpeta = _cargar_carpetas().get(clave_cliente(cliente["rut"], cliente["cliente"]))
    return f"https://drive.google.com/drive/folders/{carpeta}" if carpeta else ""


def _subir(carpeta: str, nombre: str, contenido: bytes, tipo: str) -> dict:
    limite = "malatesta_limite_de_partes"
    metadatos = json.dumps({"name": nombre, "parents": [carpeta]})
    cuerpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadatos}\r\n"
              f"--{limite}\r\nContent-Type: {tipo}\r\n\r\n").encode("utf-8") + contenido + f"\r\n--{limite}--".encode()
    return _api("POST", _URL_SUBIDA, data=cuerpo, headers={"Content-Type": f"multipart/related; boundary={limite}"})


def subir_cotizacion(ruta: Path, rut: str, cliente: str) -> bool:
    """Devuelve False si ya estaba: se puede reintentar sin duplicar."""
    carpeta = _subcarpeta(_carpeta_cliente(rut, cliente), "Cotizaciones")
    if _buscar(f"name='{_texto_consulta(ruta.name)}' and '{carpeta}' in parents"):
        return False
    _subir(carpeta, ruta.name, ruta.read_bytes(), "application/pdf")
    return True


def subir_cotizaciones_pendientes() -> tuple[int, int, int]:
    """Sube las cotizaciones que falten. Devuelve (subidas, ya estaban, con error)."""
    ruts = {mayorista._normalizar(c["cliente"]): c["rut"] for c in mayorista.listar_clientes()}
    subidas = ya_estaban = errores = 0
    for cotizacion in mayorista.listar_cotizaciones():
        ruta = mayorista.COTIZACIONES_DIR / cotizacion["archivo"]
        rut = ruts.get(mayorista._normalizar(cotizacion["cliente"]), "")
        try:
            if subir_cotizacion(ruta, rut, cotizacion["cliente"]):
                subidas += 1
            else:
                ya_estaban += 1
        except ErrorDrive:
            errores += 1
    return subidas, ya_estaban, errores


def subir_factura(contenido: bytes, nombre: str, tipo: str, rut: str, cliente: str) -> dict:
    carpeta = _subcarpeta(_carpeta_cliente(rut, cliente), "Facturas")
    return _subir(carpeta, nombre, contenido, tipo)


def renombrar(archivo_id: str, nombre: str) -> None:
    _api("PATCH", f"{_URL_ARCHIVOS}/{archivo_id}", json={"name": nombre})
