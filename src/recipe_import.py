"""Extraccion deterministica de recetas desde URLs, imagenes o texto crudo.

Nunca inventa informacion: si una fuente no da un dato, queda ausente (texto
vacio / advertencia explicita), nunca se completa con un valor inventado.
Cada extractor individual atrapa sus propios errores -- un fallo de red o de
una fuente puntual nunca debe tumbar el bot (mismo principio que
sync_server.start_background).

Deliberadamente sin LLM aca: la clasificacion/estructuracion de este texto
crudo vive en recipe_standardize.py.
"""
from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import pytesseract
import requests
from bs4 import BeautifulSoup
from PIL import Image

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_DOMINIOS_NO_SOPORTADOS = {
    "instagram.com": "Instagram",
    "www.instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "www.facebook.com": "Facebook",
    "m.facebook.com": "Facebook",
    "fb.watch": "Facebook",
}

_DOMINIOS_YOUTUBE = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}
_DOMINIOS_TIKTOK = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com"}
_DOMINIOS_PINTEREST = {"pinterest.com", "www.pinterest.com", "pin.it", "cl.pinterest.com"}


@dataclass
class RawExtraction:
    texto_crudo: str = ""
    titulo: str | None = None
    autor: str | None = None
    url: str | None = None
    fuente_tipo: str = "desconocido"
    advertencias: list[str] = field(default_factory=list)
    exitosa: bool = True


def extraer_de_url(url: str) -> RawExtraction:
    """Punto de entrada principal: detecta la fuente por dominio y enruta al
    extractor que corresponda."""
    dominio = (urlparse(url).netloc or "").lower()

    if dominio in _DOMINIOS_NO_SOPORTADOS:
        nombre = _DOMINIOS_NO_SOPORTADOS[dominio]
        return RawExtraction(
            url=url,
            fuente_tipo=nombre.lower(),
            exitosa=False,
            advertencias=[
                f"{nombre} no está soportado automáticamente todavía (bloquea el acceso sin "
                "login desde afuera). Pega el texto de la publicación (con el prefijo "
                "'Receta:') o mándame una captura de pantalla y lo proceso igual."
            ],
        )

    if dominio in _DOMINIOS_YOUTUBE:
        return _extraer_de_video(url, "youtube")
    if dominio in _DOMINIOS_TIKTOK:
        return _extraer_de_video(url, "tiktok")
    if dominio in _DOMINIOS_PINTEREST:
        return _extraer_de_pinterest(url)

    return _extraer_de_blog(url)


def _extraer_de_video(url: str, fuente_tipo: str) -> RawExtraction:
    try:
        import yt_dlp
    except Exception as exc:  # noqa: BLE001
        return RawExtraction(
            url=url, fuente_tipo=fuente_tipo, exitosa=False,
            advertencias=[f"No pude cargar el extractor de video: {exc}"],
        )

    opciones = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["es", "es-*", "en"],
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        return RawExtraction(
            url=url, fuente_tipo=fuente_tipo, exitosa=False,
            advertencias=[f"No pude acceder a este video ({exc}). Pega el texto o una captura."],
        )

    advertencias: list[str] = []
    titulo = info.get("title")
    descripcion = info.get("description") or ""

    subtitulos_texto = _extraer_texto_subtitulos(info)
    if not subtitulos_texto:
        advertencias.append("No encontré subtítulos en este video -- solo usé título y descripción.")

    partes = [p for p in [f"Título: {titulo}" if titulo else None, descripcion, subtitulos_texto] if p]
    texto_crudo = "\n\n".join(partes)

    if not texto_crudo.strip():
        advertencias.append("No pude extraer texto útil de este video (sin subtítulos ni descripción). Pega la receta a mano.")

    return RawExtraction(
        texto_crudo=texto_crudo,
        titulo=titulo,
        autor=info.get("uploader"),
        url=url,
        fuente_tipo=fuente_tipo,
        advertencias=advertencias,
        exitosa=bool(texto_crudo.strip()),
    )


def _extraer_texto_subtitulos(info: dict) -> str:
    """Baja el archivo de subtitulos (manual o automatico, prefiriendo espanol)
    y lo limpia, quedandose solo con el texto hablado sin timestamps."""
    subs = info.get("subtitles") or {}
    autosubs = info.get("automatic_captions") or {}

    candidatos: list[dict] = []
    for idioma in ("es", "en"):
        for fuente in (subs, autosubs):
            for clave, lista in fuente.items():
                if clave == idioma or clave.startswith(f"{idioma}-"):
                    candidatos.extend(lista)

    # Preferir el formato vtt (texto plano con timestamps simples) sobre json3/srv.
    candidatos.sort(key=lambda c: 0 if c.get("ext") == "vtt" else 1)

    for cand in candidatos:
        url_sub = cand.get("url")
        if not url_sub:
            continue
        try:
            resp = requests.get(url_sub, timeout=15)
            resp.raise_for_status()
        except Exception:  # noqa: BLE001
            continue
        return _limpiar_subtitulos(resp.text)
    return ""


_PATRON_TIMESTAMP = re.compile(r"-->")
_PATRON_ETIQUETA_VTT = re.compile(r"<[^>]+>")


def _limpiar_subtitulos(contenido: str) -> str:
    """Quita timestamps/numeros de cue de un archivo VTT/SRT, dejando solo el
    texto, sin repetir lineas duplicadas consecutivas (comun en VTT auto-generado)."""
    lineas_limpias: list[str] = []
    anterior = None
    for linea in contenido.splitlines():
        linea = linea.strip()
        if not linea or linea.upper().startswith("WEBVTT") or linea.isdigit():
            continue
        if _PATRON_TIMESTAMP.search(linea):
            continue
        linea = _PATRON_ETIQUETA_VTT.sub("", linea).strip()
        if linea and linea != anterior:
            lineas_limpias.append(linea)
            anterior = linea
    return " ".join(lineas_limpias)


def _extraer_de_pinterest(url: str) -> RawExtraction:
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return RawExtraction(
            url=url, fuente_tipo="pinterest", exitosa=False,
            advertencias=[f"No pude acceder al pin ({exc})."],
        )

    soup = BeautifulSoup(resp.text, "html.parser")
    url_original = _meta(soup, "og:see_also")
    titulo = _meta(soup, "og:title")
    descripcion = _meta(soup, "og:description")

    if url_original and "pinterest." not in urlparse(url_original).netloc:
        extraccion = _extraer_de_blog(url_original)
        extraccion.advertencias.insert(0, f"Se siguió el pin hasta su sitio original: {url_original}")
        return extraccion

    texto_crudo = "\n\n".join(p for p in [titulo, descripcion] if p)
    advertencias = (
        ["No pude resolver el pin a su sitio original -- solo tengo el título/descripción del pin."]
        if texto_crudo else ["No pude extraer nada de este pin."]
    )
    return RawExtraction(
        texto_crudo=texto_crudo, titulo=titulo, url=url, fuente_tipo="pinterest",
        advertencias=advertencias, exitosa=bool(texto_crudo.strip()),
    )


def _meta(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    return tag.get("content") if tag else None


def _extraer_de_blog(url: str) -> RawExtraction:
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return RawExtraction(
            url=url, fuente_tipo="blog", exitosa=False,
            advertencias=[f"No pude acceder a esta página ({exc})."],
        )

    soup = BeautifulSoup(resp.text, "html.parser")

    receta_jsonld = _buscar_recipe_jsonld(soup)
    if receta_jsonld is not None:
        texto_crudo, titulo, autor = _texto_desde_jsonld(receta_jsonld)
        return RawExtraction(
            texto_crudo=texto_crudo, titulo=titulo, autor=autor, url=url,
            fuente_tipo="blog_jsonld",
            advertencias=["Se encontraron datos estructurados (schema.org/Recipe) en la página -- extracción de alta confianza."],
            exitosa=bool(texto_crudo.strip()),
        )

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    titulo_tag = soup.find("h1") or soup.find("title")
    titulo = titulo_tag.get_text(strip=True) if titulo_tag else None
    texto_crudo = soup.get_text("\n", strip=True)

    advertencias = [
        "No se encontraron datos estructurados (schema.org/Recipe) en la página -- se "
        "extrajo el texto plano completo, puede incluir contenido ajeno a la receta."
    ]
    return RawExtraction(
        texto_crudo=texto_crudo, titulo=titulo, url=url, fuente_tipo="blog_texto",
        advertencias=advertencias, exitosa=bool(texto_crudo.strip()),
    )


def _buscar_recipe_jsonld(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for candidato in _aplanar_jsonld(data):
            tipo = candidato.get("@type")
            tipos = tipo if isinstance(tipo, list) else [tipo]
            if tipos and any(str(t).lower() == "recipe" for t in tipos):
                return candidato
    return None


def _aplanar_jsonld(data):
    if isinstance(data, list):
        for item in data:
            yield from _aplanar_jsonld(item)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from _aplanar_jsonld(data["@graph"])
        else:
            yield data


def _texto_desde_jsonld(receta: dict) -> tuple[str, str | None, str | None]:
    titulo = receta.get("name")
    autor = receta.get("author")
    if isinstance(autor, dict):
        autor = autor.get("name")
    elif isinstance(autor, list) and autor:
        autor = autor[0].get("name") if isinstance(autor[0], dict) else str(autor[0])

    partes = [f"Título: {titulo}" if titulo else None]

    rendimiento = receta.get("recipeYield")
    if isinstance(rendimiento, list):
        rendimiento = ", ".join(str(r) for r in rendimiento)
    if rendimiento:
        partes.append(f"Rendimiento (texto original de la fuente): {rendimiento}")

    prep = receta.get("prepTime")
    coccion = receta.get("cookTime")
    if prep:
        partes.append(f"Tiempo de preparación (ISO 8601): {prep}")
    if coccion:
        partes.append(f"Tiempo de cocción (ISO 8601): {coccion}")

    ingredientes = receta.get("recipeIngredient") or receta.get("ingredients") or []
    if ingredientes:
        partes.append("Ingredientes:\n" + "\n".join(f"- {i}" for i in ingredientes))

    instrucciones = receta.get("recipeInstructions")
    if instrucciones:
        pasos = _texto_instrucciones(instrucciones)
        if pasos:
            partes.append("Procedimiento:\n" + "\n".join(f"{i + 1}. {p}" for i, p in enumerate(pasos)))

    descripcion = receta.get("description")
    if descripcion:
        partes.append(f"Descripción: {descripcion}")

    return "\n\n".join(p for p in partes if p), titulo, autor


def _texto_instrucciones(instrucciones) -> list[str]:
    if isinstance(instrucciones, str):
        return [instrucciones]
    pasos: list[str] = []
    for item in instrucciones:
        if isinstance(item, str):
            pasos.append(item)
        elif isinstance(item, dict):
            if item.get("@type") == "HowToSection" and "itemListElement" in item:
                pasos.extend(_texto_instrucciones(item["itemListElement"]))
            else:
                texto = item.get("text") or item.get("name")
                if texto:
                    pasos.append(texto)
    return pasos


def extraer_de_imagen(contenido: bytes) -> str:
    """OCR de una foto/captura (recetas, etiquetas, tablas de costos)."""
    imagen = Image.open(io.BytesIO(contenido))
    return pytesseract.image_to_string(imagen, lang="spa+eng")
