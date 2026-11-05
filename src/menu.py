"""Botones del bot: el menu, la navegacion de recetas y las respuestas de un toque.

Los botones no agregan caminos nuevos: un boton de respuesta envia el mismo texto que
se podria escribir, asi que todo lo que se escribe sigue funcionando igual. Los
productos salen del catalogo, para que una receta nueva aparezca sola.
"""
from __future__ import annotations

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from . import tools

BOTON_MENU = "☰ Menú"
TECLADO_PERSISTENTE = ReplyKeyboardMarkup([[KeyboardButton(BOTON_MENU)]], resize_keyboard=True, is_persistent=True)
PATRON_MENU = re.compile(r"\s*(☰\s*)?/?men[uú]\s*[.!]?\s*", re.IGNORECASE)
PREFIJO_RESPUESTA = "t:"

MAX_OPCIONES = 30
MAX_LARGO_BOTON = 45
CANTIDADES_RAPIDAS = (6, 12, 24, 50, 100)
LOTES_RAPIDOS = (("½", "0,5"), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"))

# Solo estas palabras entre comillas son opciones: un ejemplo como "5%" no lo es.
_OPCIONES = {
    "sí": ("✅ Sí", "success"),
    "no": ("No", None),
    "cancelar": ("❌ Cancelar", "danger"),
    "cambiar productos": ("✏️ Cambiar productos", None),
    "actualizar": ("✏️ Actualizar", None),
    "omitir": ("⏭ Omitir", None),
    "hoy": ("📅 Hoy", None),
    "sin cotización": ("Sin cotización", None),
    "nuevo": ("➕ Es nuevo", None),
    "igual": ("Mantener", None),
    "ok": ("👍 Ok", None),
    "sin descuento": ("Sin descuento", None),
}
_PATRON_ENTRE_COMILLAS = re.compile(r'"([^"]+)"')
_PATRON_SI_CANCELAR = re.compile(r"\(sí\s*/\s*cancelar\)", re.IGNORECASE)
_PATRON_OPCION_NUMERADA = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_PATRON_COTIZACION_NUMERADA = re.compile(r"^\s*N°\s*(\d+)\s*·\s*(.+?)\s*$", re.MULTILINE)
# "Responde los números" admite varios a la vez: eso se escribe.
_PATRON_PIDE_UN_NUMERO = re.compile(r"(?<!los )\bn[uú]mero\b", re.IGNORECASE)


def _boton(texto: str, dato: str, estilo: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(texto, callback_data=dato, style=estilo)


def _en_filas(botones: list[InlineKeyboardButton], por_fila: int = 2) -> list[list[InlineKeyboardButton]]:
    return [botones[i:i + por_fila] for i in range(0, len(botones), por_fila)]


def principal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_boton("📖 Recetas y costos", "m:recetas", "success"), _boton("🥖 Calcular masa", "a:masa", "success")],
        [_boton("📄 Cotizar", "a:cotizar", "primary"), _boton("🗂 Cotizaciones", "a:cotizaciones", "primary")],
        [_boton("👥 Clientes", "a:clientes", "primary"), _boton("🧾 Factura", "a:factura", "primary")],
        [_boton("📋 Lista mayorista", "a:lista", "primary"), _boton("🏭 Producción", "m:produccion", "primary")],
        [_boton("⚙️ Administración", "m:admin")],
    ])


def administracion() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_boton("🔄 Sincronizar recetas", "a:sync_recetas"), _boton("🔄 Sincronizar clientes", "a:sync_clientes")],
        [_boton("➕ Agregar a mayorista", "a:agregar"), _boton("➖ Quitar de mayorista", "a:quitar")],
        [_boton("🔗 Asociar factura", "a:asociar"), _boton("☁️ Subir cotizaciones", "a:subir")],
        [_boton("🔔 Avisos en este chat", "a:avisos"), _boton("🚪 Cerrar sesión", "a:salir", "danger")],
        [_boton("⬅️ Volver", "m:principal")],
    ])


def produccion() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_boton("📊 Costo de hoy", "a:costo_hoy", "primary")],
        [_boton("⬅️ Volver", "m:principal")],
    ])


def cancelar_en_curso() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_boton("❌ Cancelar lo que está en curso", "a:cancelar", "danger")]])


def volver_al_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_boton("⬅️ Volver a recetas", "a:recetas")]])


def productos() -> list[str]:
    nombres = {str(p) for p in tools._load_catalogo()["producto"].dropna()}
    return sorted((n for n in nombres if re.search(r"[^\W\d_]", n)), key=tools._normalizar)


def variantes(producto: str) -> list[str]:
    catalogo = tools._load_catalogo()
    return sorted({str(v) for v in catalogo[catalogo["producto"] == producto]["variante"]}, key=tools._normalizar)


def teclado_productos() -> InlineKeyboardMarkup:
    botones = [_boton(tools._legible(p), f"rp:{i}") for i, p in enumerate(productos())]
    return InlineKeyboardMarkup([*_en_filas(botones), [_boton("⬅️ Volver", "m:principal")]])


def teclado_variantes(i: int, producto: str) -> InlineKeyboardMarkup:
    botones = [_boton(tools._legible(v) or tools._legible(producto), f"rv:{i}:{j}") for j, v in enumerate(variantes(producto))]
    return InlineKeyboardMarkup([*_en_filas(botones), [_boton("⬅️ Volver", "m:recetas")]])


def teclado_receta(i: int, j: int, hay_mas_variantes: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_boton("🧮 Calcular lotes", f"rl:{i}:{j}", "success")],
        [_boton("🔢 Por unidades", f"rc:{i}:{j}", "primary"), _boton("📝 Preparación", f"rt:{i}:{j}", "primary")],
        [_boton("⬅️ Volver", f"rp:{i}" if hay_mas_variantes else "m:recetas")],
    ])


def teclado_cantidades() -> InlineKeyboardMarkup:
    rapidas = [_boton(str(n), f"{PREFIJO_RESPUESTA}{n}", "primary") for n in CANTIDADES_RAPIDAS]
    return InlineKeyboardMarkup([rapidas, [_boton("❌ Cancelar", f"{PREFIJO_RESPUESTA}cancelar", "danger")]])


def teclado_lotes() -> InlineKeyboardMarkup:
    rapidos = [_boton(texto, f"{PREFIJO_RESPUESTA}{valor}", "primary") for texto, valor in LOTES_RAPIDOS]
    return InlineKeyboardMarkup([rapidos, [_boton("❌ Cancelar", f"{PREFIJO_RESPUESTA}cancelar", "danger")]])


def teclado_masa(opciones: list[tuple[str, str]], con_atras: bool) -> InlineKeyboardMarkup:
    botones = [_boton(etiqueta, f"{PREFIJO_RESPUESTA}{valor}", "primary") for etiqueta, valor in opciones]
    largo = max(len(etiqueta) for etiqueta, _ in opciones)
    por_fila = 4 if largo <= 8 else 2 if largo <= 14 else 1
    salida = [_boton("❌ Cancelar", f"{PREFIJO_RESPUESTA}cancelar", "danger")]
    if con_atras:
        salida.insert(0, _boton("⬅️ Atrás", f"{PREFIJO_RESPUESTA}atrás"))
    return InlineKeyboardMarkup([*_en_filas(botones, por_fila), salida])


def otra_masa() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_boton("🥖 Calcular otra masa", "a:masa", "success")]])


def _opciones_numeradas(texto: str) -> list[InlineKeyboardButton]:
    if not _PATRON_PIDE_UN_NUMERO.search(texto.rsplit("\n\n", 1)[-1]):
        return []
    opciones = [(int(n), f"{int(n)}. {nombre}") for n, nombre in _PATRON_OPCION_NUMERADA.findall(texto)]
    opciones += [(int(n), f"N° {int(n):04d} · {nombre}") for n, nombre in _PATRON_COTIZACION_NUMERADA.findall(texto)]
    if not opciones or len(opciones) > MAX_OPCIONES:
        return []
    return [_boton(etiqueta[:MAX_LARGO_BOTON], f"{PREFIJO_RESPUESTA}{n}") for n, etiqueta in opciones]


def _opciones_de_palabras(texto: str) -> list[InlineKeyboardButton]:
    ultimo_parrafo = texto.rsplit("\n\n", 1)[-1]
    palabras = [p.lower() for p in _PATRON_ENTRE_COMILLAS.findall(ultimo_parrafo)]
    if _PATRON_SI_CANCELAR.search(ultimo_parrafo):
        palabras += ["sí", "cancelar"]
    palabras = [p for p in dict.fromkeys(palabras) if p in _OPCIONES]
    return [_boton(*_texto_y_estilo(p, _OPCIONES[p])) for p in palabras]


def _texto_y_estilo(palabra: str, opcion: tuple[str, str | None]) -> tuple[str, str, str | None]:
    return opcion[0], f"{PREFIJO_RESPUESTA}{palabra}", opcion[1]


def botones_de_respuesta(texto: str) -> InlineKeyboardMarkup | None:
    """Botones para las opciones que pide una pregunta, o None si no pide ninguna."""
    numeradas = _opciones_numeradas(texto)
    palabras = _opciones_de_palabras(texto)
    if not numeradas and not palabras:
        return None
    filas = [[b] for b in numeradas]
    if palabras:
        filas += _en_filas(palabras, por_fila=3)
    return InlineKeyboardMarkup(filas)


def es_pregunta(markup) -> bool:
    """Si el teclado responde una pregunta: solo vale para la ultima que se hizo."""
    if not isinstance(markup, InlineKeyboardMarkup):
        return False
    return any(str(b.callback_data).startswith(PREFIJO_RESPUESTA) for fila in markup.inline_keyboard for b in fila)
