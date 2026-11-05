"""Bot de Telegram -- interfaz principal del agente interno Malatesta.

Usa long-polling (sin webhook), asi que en OCI no hace falta abrir ningun
puerto: el servidor solo hace conexiones salientes hacia la API de Telegram.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from telegram import BotCommand, ReplyKeyboardRemove, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ExtBot,
    MessageHandler,
    TypeHandler,
    filters,
)

from . import (
    acceso,
    drive_clientes,
    facturas,
    flujo_masa,
    mayorista,
    menu,
    planilla_clientes,
    planilla_recetas,
    recipe_import,
    recipe_pipeline,
    sync_automatica,
    sync_server,
    tools,
)
from .agent import build_agent

load_dotenv()
logging.basicConfig(level=logging.INFO)
# httpx registra en INFO cada URL de Telegram, y esas URL llevan el token del bot.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Un grafo de agente + historial de mensajes por chat, para que cada
# conversacion de Telegram tenga su propio contexto.
_graph = None
_chat_messages: dict[int, list] = {}

# Sin limite, el historial de una conversacion larga crece para siempre y
# termina rompiendo al modelo (respuestas truncadas/corruptas, el agente
# "se pierde" y empieza a inventar numeros en vez de usar las herramientas).
# Se recorta por TURNOS completos (desde un mensaje humano en adelante) para
# nunca cortar a mitad de un tool_call/tool_result, lo que rompería el turno
# siguiente.
MAX_TURNOS_HISTORIAL = 15


def _recortar_historial(messages: list) -> list:
    indices_humanos = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(indices_humanos) <= MAX_TURNOS_HISTORIAL:
        return messages
    corte = indices_humanos[-MAX_TURNOS_HISTORIAL]
    return messages[corte:]


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_agent()
    return _graph


# Confiar en que el LLM siempre infiera correctamente que un mensaje de una
# sola palabra ("1") se refiere a una posicion de la ultima lista numerada
# es fragil (se observo en produccion: a veces no llama a ninguna
# herramienta y responde que "hubo un problema", o pasa el nombre completo
# mal separado en producto/variante). En vez de pedirle al LLM que recuerde
# la lista, Python guarda la ULTIMA lista numerada que el bot mostro (por
# chat) y resuelve el numero al nombre real ANTES de mandarle el mensaje al
# agente -- asi el LLM nunca tiene que "adivinar" a que se refiere el numero.
_chat_ultima_lista: dict[int, dict[int, str]] = {}

_PATRON_NUMERO_SUELTO = re.compile(r"^\s*(?:la|el|opci[oó]n|n[uú]mero)?\s*(\d+)\s*\.?\s*$", re.IGNORECASE)
_PATRON_ITEM_LISTA = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$", re.MULTILINE)


def _extraer_lista_numerada(texto: str) -> dict[int, str]:
    return {int(n): nombre.strip() for n, nombre in _PATRON_ITEM_LISTA.findall(texto)}


def _expandir_respuesta_numerica(texto: str, ultima_lista: dict[int, str]) -> str:
    match = _PATRON_NUMERO_SUELTO.match(texto)
    if not match:
        return texto
    numero = int(match.group(1))
    nombre = ultima_lista.get(numero)
    if nombre:
        return f'Quiero información sobre "{nombre}" (era la opción {numero} de la lista que me mostraste).'
    return f"Quiero la opción número {numero} de la última lista numerada que me mostraste."


# --- Importacion de recetas desde links/texto/fotos -----------------------
#
# Un link o una foto activan la importacion automaticamente (el bot nunca
# manejaba fotos antes, y un link no tiene otro uso en este bot, asi que no
# hay ambiguedad con una pregunta normal). Texto pegado sin link necesita el
# prefijo "Receta:" para no confundirse con una pregunta al agente.
_chat_importacion: dict[int, dict] = {}

# Al copiar desde el celular el link suele venir sin https://. Sin eso, se exige una ruta
# despues del dominio: un correo o "malatestachile.cl" en una frase no son para importar.
_PATRON_URL = re.compile(r"https?://\S+|(?<![@\w.-])(?:www\.\S+|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/\S+)", re.IGNORECASE)
_PREFIJO_RECETA = re.compile(r"^\s*receta\s*:\s*(.*)$", re.IGNORECASE | re.DOTALL)
_PATRON_SI = re.compile(r"^\s*(s[ií]|dale|ok|confirmo|correcto)\b", re.IGNORECASE)
# Para cancelar una importacion en CUALQUIER pregunta pendiente, no solo en
# la confirmacion final -- exige que el mensaje entero sea uno de estos
# (no solo que empiece con la palabra) porque "para" es una palabra comun
# que podria aparecer al inicio de una respuesta legitima en otro contexto;
# como comando suelto para cancelar, en cambio, no hay ambiguedad posible.
_PATRON_CANCELAR = re.compile(
    r"^\s*(no|cancela\w*|descarta\w*|olv[ií]da(?:lo|la)?|detente|para|basta|d[eé]jalo)\s*[.!¡]*\s*$",
    re.IGNORECASE,
)


async def _continuar_importacion(update: Update, chat_id: int, texto_respuesta: str | None = None) -> None:
    """Avanza el estado de una importacion pendiente: aplica la respuesta del
    usuario (si corresponde), pregunta lo siguiente que falte, o muestra el
    resumen final para confirmar."""
    estado = _chat_importacion[chat_id]

    if estado["preguntando"] and texto_respuesta is not None and _PATRON_CANCELAR.match(texto_respuesta):
        del _chat_importacion[chat_id]
        await update.message.reply_text("Ok, cancelé la importación. Mándamela de nuevo si quieres reintentar.")
        return

    if estado["preguntando"] and estado["preguntando"][0] != "confirmacion" and texto_respuesta is not None:
        error = recipe_pipeline.aplicar_respuesta(estado, texto_respuesta)
        if error:
            await update.message.reply_text(error)
            return

    if estado["preguntando"] and estado["preguntando"][0] == "confirmacion":
        if _PATRON_SI.match(texto_respuesta or ""):
            await update.message.reply_text("Guardando en la planilla...")
            try:
                mensaje = await asyncio.to_thread(recipe_pipeline.guardar, estado)
            except planilla_recetas.RecetaYaExiste as exc:
                estado["producto"] = None
                estado["preguntando"] = ("producto", None)
                await update.message.reply_text(str(exc))
                await _continuar_importacion(update, chat_id)
                return
            except planilla_clientes.ErrorPlanilla as exc:
                await update.message.reply_text(f'{exc}\n\nResponde "sí" para reintentar o "no" para descartar.')
                return
            del _chat_importacion[chat_id]
            await update.message.reply_text(f"Listo, guardada. {mensaje}")
            return
        await update.message.reply_text('Responde "sí" para guardar o "no" para descartar.')
        return

    pregunta = recipe_pipeline.siguiente_pregunta(estado)
    if pregunta is None:
        await update.message.reply_text(recipe_pipeline.formatear_resumen(estado))
    else:
        await update.message.reply_text(pregunta)


async def _iniciar_importacion(update: Update, chat_id: int, texto_crudo: str, metadata: recipe_import.RawExtraction) -> None:
    if not texto_crudo.strip():
        advertencias = "\n".join(f"- {a}" for a in metadata.advertencias) or "No encontré texto en la fuente."
        await update.message.reply_text(f"No pude extraer una receta de ahí:\n{advertencias}")
        return

    await update.message.reply_text("Recibido, estoy analizando la receta...")
    estado = recipe_pipeline.iniciar_importacion(texto_crudo, metadata)
    _chat_importacion[chat_id] = estado
    await update.message.reply_text(recipe_pipeline.formatear_extraccion(estado))
    await _continuar_importacion(update, chat_id)


# --- Venta mayorista: lista de precios y cotizaciones -------------------------
#
# Igual que la importacion, la cotizacion es un flujo de preguntas en Python
# (mayorista.py): los montos nunca pasan por el LLM.
_chat_cotizacion: dict[int, dict] = {}

# Cualquier mencion de "cotizacion"/"cotizar" en singular inicia el flujo
# ("hagamos otra cotización" no calzaba con una lista de verbos y caia al
# LLM, que inventaba preguntas). El plural ("ver las cotizaciones") lo
# atiende antes _PATRON_VER_COTIZACIONES.
_PATRON_COTIZACION = re.compile(r"^\s*cotiza|\bcotiza(r|ci[oó]n)\b", re.IGNORECASE)
_PATRON_LISTA_MAYORISTA = re.compile(r"lista\s+(de\s+)?precios?\s+(al\s+por\s+)?mayor|lista\s+mayorist", re.IGNORECASE)


async def _enviar_pdf(update: Update, ruta, caption: str | None = None) -> None:
    with open(ruta, "rb") as archivo:
        await update.message.reply_document(document=archivo, filename=ruta.name, caption=caption)


async def _iniciar_cotizacion(update: Update, chat_id: int) -> None:
    _chat_clientes.pop(chat_id, None)
    estado = mayorista.iniciar()
    _chat_cotizacion[chat_id] = estado
    await update.message.reply_text(
        'Vamos con la cotización mayorista. Puedes escribir "cancelar" en cualquier momento.\n\n'
        + mayorista.siguiente_pregunta(estado)
    )


async def _guardar_cotizacion_en_drive(update: Update, ruta, estado: dict) -> None:
    if not drive_clientes.configurado():
        return
    try:
        await asyncio.to_thread(drive_clientes.subir_cotizacion, ruta, estado.get("rut", ""), estado["cliente"])
    except drive_clientes.ErrorDrive:
        await update.message.reply_text("No pude guardar esta cotización en Drive. Para reintentar: /subircotizaciones")


async def _continuar_cotizacion(update: Update, chat_id: int, texto: str) -> None:
    estado = _chat_cotizacion[chat_id]
    if re.match(r"^\s*(cancela\w*|descarta\w*|olv[ií]da(?:lo|la)?|detente|basta)\s*[.!]*\s*$", texto, re.IGNORECASE):
        del _chat_cotizacion[chat_id]
        await update.message.reply_text("Ok, cancelé la cotización.")
        return

    if estado["preguntando"] == "confirmacion":
        if mayorista.es_si(texto):
            ruta = mayorista.generar_pdf_cotizacion(estado)
            del _chat_cotizacion[chat_id]
            numero = int(ruta.name.split("_")[1])
            await _enviar_pdf(update, ruta, caption=f"Cotización N° {numero:04d} para {estado['cliente']}")
            await _guardar_cotizacion_en_drive(update, ruta, estado)
            return
        if mayorista.pide_editar_productos(texto):
            mayorista.volver_a_productos(estado)
            await update.message.reply_text(mayorista.siguiente_pregunta(estado))
            return
        await update.message.reply_text('Responde "sí" para generar el PDF, "cambiar productos" o "cancelar".')
        return

    error = mayorista.aplicar_respuesta(estado, texto)
    if error:
        await update.message.reply_text(error)
        return
    await update.message.reply_text(mayorista.siguiente_pregunta(estado))


# Agregar o quitar productos de la lista mayorista. Las recetas estan por
# lote; al agregar se enlaza la receta y se pregunta el precio UNITARIO de
# venta (mayorista.py muestra el costo unitario como referencia).
_chat_gestion_mayorista: dict[int, dict] = {}

_PATRON_AGREGAR_MAYORISTA = re.compile(r"\b(agreg|añad|anad|incorpor)\w*\b.*\bmayor", re.IGNORECASE)
_PATRON_QUITAR_MAYORISTA = re.compile(r"\b(quit|elimin|sac|borr|remuev)\w*\b.*\bmayor", re.IGNORECASE)
_PATRON_CANCELAR_FLUJO = re.compile(
    r"^\s*(cancela\w*|descarta\w*|olv[ií]da(?:lo|la)?|detente|basta)\s*[.!]*\s*$", re.IGNORECASE
)


async def _iniciar_gestion_mayorista(update: Update, chat_id: int, modo: str) -> None:
    estado = mayorista.iniciar_agregar() if modo == "agregar" else mayorista.iniciar_quitar()
    _chat_gestion_mayorista[chat_id] = estado
    await update.message.reply_text(mayorista.siguiente_pregunta_gestion(estado))


async def _continuar_gestion_mayorista(update: Update, chat_id: int, texto: str) -> None:
    estado = _chat_gestion_mayorista[chat_id]
    if _PATRON_CANCELAR_FLUJO.match(texto):
        del _chat_gestion_mayorista[chat_id]
        await update.message.reply_text("Ok, cancelado. La lista mayorista quedó igual.")
        return

    if estado["preguntando"] in ("agregar_confirmacion", "quitar_confirmacion"):
        if mayorista.es_si(texto):
            mensaje = mayorista.guardar_gestion(estado)
            del _chat_gestion_mayorista[chat_id]
            await update.message.reply_text(mensaje)
            return
        await update.message.reply_text('Responde "sí" para confirmar o "cancelar".')
        return

    error = mayorista.aplicar_respuesta_gestion(estado, texto)
    if error:
        await update.message.reply_text(error)
        return
    await update.message.reply_text(mayorista.siguiente_pregunta_gestion(estado))


async def agregar_mayorista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_gestion_mayorista(update, update.effective_chat.id, "agregar")


async def quitar_mayorista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_gestion_mayorista(update, update.effective_chat.id, "quitar")


async def cotizacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_cotizacion(update, update.effective_chat.id)


async def lista_mayorista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _enviar_pdf(update, mayorista.generar_pdf_lista())


# Historial: lista las cotizaciones emitidas y reenvia el PDF que se elija.
# Va antes que _PATRON_COTIZACION: "quiero ver las cotizaciones" no debe
# iniciar una cotizacion nueva.
_chat_ver_cotizaciones: set[int] = set()

_PATRON_VER_COTIZACIONES = re.compile(
    r"\b(ver|veo|lista\w*|muestra\w*|mis|historial|reenv\w*|busca\w*|d[oó]nde)\b.*\bcotizaciones\b"
    r"|\bcotizaciones\s+(emitidas|anteriores|hechas|guardadas)\b",
    re.IGNORECASE,
)


async def _mostrar_cotizaciones(update: Update, chat_id: int) -> None:
    texto = mayorista.listar_cotizaciones_texto()
    if texto is None:
        await update.message.reply_text("Todavía no hay cotizaciones emitidas. Para hacer una: /cotizacion")
        return
    _chat_ver_cotizaciones.add(chat_id)
    await update.message.reply_text(texto)


async def _reenviar_cotizacion(update: Update, chat_id: int, texto: str) -> None:
    if _PATRON_CANCELAR_FLUJO.match(texto):
        _chat_ver_cotizaciones.discard(chat_id)
        await update.message.reply_text("Ok.")
        return
    ruta, error = mayorista.buscar_cotizacion(texto)
    if error:
        await update.message.reply_text(error)
        return
    _chat_ver_cotizaciones.discard(chat_id)
    numero = int(ruta.name.split("_")[1])
    await _enviar_pdf(update, ruta, caption=f"Cotización N° {numero:04d}")


async def cotizaciones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _mostrar_cotizaciones(update, update.effective_chat.id)


# Consulta de clientes: lista, busqueda por nombre o RUT, y ficha con sus
# cotizaciones. Los datos no pasan por el LLM.
_chat_clientes: dict[int, list[dict]] = {}

_PATRON_VER_CLIENTES = re.compile(
    r"\b(?:ver|veo|lista\w*|muestra\w*|mu[eé]stra\w*|mis|busca\w*|consulta\w*|datos|informaci[oó]n|info|ficha|"
    r"qu[eé]|cu[aá]les|cu[aá]ntos)\b(?:(?!cotiza).)*\bclientes?\b(?P<busqueda>(?:(?!cotiza).)*)$",
    re.IGNORECASE,
)
_PATRON_RELLENO_CLIENTES = re.compile(r"^\s*(tengo|hay|guardados?|mayoristas?)\b", re.IGNORECASE)
# Sin la palabra "cliente" ("ficha de nicolas gedda"): solo se atiende aca si el
# nombre calza con un cliente; "datos del alfajor" sigue siendo para el agente.
_PATRON_FICHA_NOMBRE = re.compile(r"\b(?:ficha|datos|informaci[oó]n|info)\s+del?\s+(?P<busqueda>(?:(?!cotiza).)+)$",
                                  re.IGNORECASE)
MAX_CLIENTES_LISTA = 30


async def _mostrar_ficha(update: Update, chat_id: int, cliente: dict) -> None:
    _chat_clientes.pop(chat_id, None)
    texto, tiene_cotizaciones = mayorista.ficha_cliente(cliente, facturas=facturas.de_cliente(cliente),
                                                        carpeta=drive_clientes.link_carpeta(cliente))
    if tiene_cotizaciones:
        _chat_ver_cotizaciones.add(chat_id)
    await update.message.reply_text(texto)


async def _mostrar_opciones_clientes(update: Update, chat_id: int, encontrados: list[dict]) -> None:
    if len(encontrados) == 1:
        await _mostrar_ficha(update, chat_id, encontrados[0])
        return
    _chat_clientes[chat_id] = encontrados[:MAX_CLIENTES_LISTA]
    await update.message.reply_text(
        f"Encontré estos clientes:\n{mayorista.clientes_texto(_chat_clientes[chat_id])}\n\n"
        'Responde el número para ver su ficha, escribe un nombre o RUT, o "cancelar".'
    )


async def _consultar_clientes(update: Update, chat_id: int, busqueda: str = "") -> None:
    _chat_ver_cotizaciones.discard(chat_id)
    if not busqueda.strip():
        todos = mayorista.listar_clientes()
        if not todos:
            await update.message.reply_text("Todavía no hay clientes. Se guardan al hacer una /cotizacion con RUT.")
            return
        _chat_clientes[chat_id] = todos[:MAX_CLIENTES_LISTA]
        await update.message.reply_text(
            f"Clientes ({len(todos)}):\n{mayorista.clientes_texto(_chat_clientes[chat_id])}\n\n"
            'Responde el número para ver su ficha, escribe un nombre o RUT, o "cancelar".'
        )
        return
    encontrados = mayorista.consultar_clientes(busqueda)
    if not encontrados:
        await update.message.reply_text(f'No encontré clientes parecidos a "{busqueda.strip()}". Para ver todos: /clientes')
        return
    await _mostrar_opciones_clientes(update, chat_id, encontrados)


async def _continuar_clientes(update: Update, chat_id: int, texto: str) -> bool:
    """Devuelve False si el mensaje no era para esta consulta: se atiende como
    mensaje normal."""
    opciones = _chat_clientes[chat_id]
    if _PATRON_CANCELAR_FLUJO.match(texto):
        del _chat_clientes[chat_id]
        await update.message.reply_text("Ok.")
        return True
    if re.fullmatch(r"\s*\d{1,3}\s*", texto):
        if not 1 <= int(texto) <= len(opciones):
            await update.message.reply_text(f'Responde un número del 1 al {len(opciones)}, o "cancelar".')
            return True
        await _mostrar_ficha(update, chat_id, opciones[int(texto) - 1])
        return True
    encontrados = mayorista.consultar_clientes(texto)
    if not encontrados:
        del _chat_clientes[chat_id]
        return False
    await _mostrar_opciones_clientes(update, chat_id, encontrados)
    return True


async def clientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _consultar_clientes(update, update.effective_chat.id, " ".join(context.args or []))


# Sincronizar clientes: descarga la planilla, muestra las diferencias y solo
# reemplaza los datos del bot si se confirma.
_chat_sincronizacion: dict[int, planilla_clientes.Comparacion] = {}

_PATRON_SINCRONIZAR = re.compile(r"\b(sincroniz|actualiz)\w*\b.*\b(clientes|planilla)\b", re.IGNORECASE)


# Recetas e insumos: el mismo camino, desde su propia planilla.
_chat_sync_recetas: dict[int, planilla_recetas.Comparacion] = {}

_PATRON_SINCRONIZAR_RECETAS = re.compile(
    r"\bsincroniz\w*\b.*\b(recetas|insumos|precios)\b|\bactualiz\w*\b.*\bplanilla\b.*\b(recetas|insumos|precios)\b",
    re.IGNORECASE,
)


async def _iniciar_sync_recetas(update: Update, chat_id: int) -> None:
    await update.message.reply_text("Descargando la planilla de recetas...")
    try:
        filas_recetas, filas_insumos = await asyncio.to_thread(planilla_recetas.descargar)
        comparacion = planilla_recetas.comparar(filas_recetas, filas_insumos)
    except planilla_clientes.ErrorPlanilla as exc:
        await update.message.reply_text(str(exc))
        return
    if comparacion.hay_cambios:
        _chat_sync_recetas[chat_id] = comparacion
    else:
        planilla_recetas.registrar_base(comparacion)
    await update.message.reply_text(planilla_recetas.comparacion_texto(comparacion))


async def _continuar_sync_recetas(update: Update, chat_id: int, texto: str) -> None:
    if _PATRON_CANCELAR_FLUJO.match(texto) or re.fullmatch(r"\s*no\s*[.!]*\s*", texto, re.IGNORECASE):
        del _chat_sync_recetas[chat_id]
        await update.message.reply_text("Ok, no cambié nada.")
        return
    if not mayorista.es_si(texto):
        await update.message.reply_text('Responde "sí" para reemplazar o "cancelar".')
        return
    await update.message.reply_text(planilla_recetas.reemplazar(_chat_sync_recetas.pop(chat_id)))


async def avisos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sync_automatica.guardar_chat_avisos(update.effective_chat.id)
    await update.message.reply_text("Listo: los avisos de la sincronización automática llegarán a este chat.")


async def _al_iniciar(app: Application) -> None:
    app.create_task(sync_automatica.bucle(app))
    try:
        await app.bot.set_my_commands([
            BotCommand("menu", "Abrir el menú"),
            BotCommand("cotizacion", "Hacer una cotización"),
            BotCommand("clientes", "Consultar clientes"),
            BotCommand("salir", "Cerrar sesión"),
        ])
    except TelegramError:
        logging.warning("No se pudieron registrar los comandos del bot")


async def sincronizar_recetas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_sync_recetas(update, update.effective_chat.id)


async def _iniciar_sincronizacion(update: Update, chat_id: int) -> None:
    _chat_clientes.pop(chat_id, None)
    _chat_ver_cotizaciones.discard(chat_id)
    await update.message.reply_text("Descargando la planilla...")
    try:
        filas = await asyncio.to_thread(planilla_clientes.descargar_filas)
        comparacion = planilla_clientes.comparar(filas)
    except planilla_clientes.ErrorPlanilla as exc:
        await update.message.reply_text(str(exc))
        return
    if comparacion.hay_cambios:
        _chat_sincronizacion[chat_id] = comparacion
    await update.message.reply_text(planilla_clientes.comparacion_texto(comparacion))


async def _continuar_sincronizacion(update: Update, chat_id: int, texto: str) -> None:
    if _PATRON_CANCELAR_FLUJO.match(texto) or re.fullmatch(r"\s*no\s*[.!]*\s*", texto, re.IGNORECASE):
        del _chat_sincronizacion[chat_id]
        await update.message.reply_text("Ok, no cambié nada.")
        return
    if not mayorista.es_si(texto):
        await update.message.reply_text('Responde "sí" para reemplazar o "cancelar".')
        return
    comparacion = _chat_sincronizacion.pop(chat_id)
    await update.message.reply_text(planilla_clientes.reemplazar(comparacion))


async def sincronizar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_sincronizacion(update, update.effective_chat.id)


# Facturas: se adjuntan en un flujo de preguntas y quedan en la carpeta Drive del
# cliente. "Factura" tambien es un producto de la panaderia: una frase con numeros
# o que habla de precios, recetas o la lista mayorista sigue su camino normal.
_chat_factura: dict[int, dict] = {}
_chat_asociar: dict[int, dict] = {}

_PATRON_ASOCIAR_FACTURA = re.compile(r"\basoci\w*\b.*\bfacturas?\b|\bfacturas?\b.*\basoci\w*\b", re.IGNORECASE)
_PATRON_ADJUNTAR_FACTURA = re.compile(r"\b(adjunt|agreg|sub|carg|registr|guard|anex)\w*\b.*\bfacturas?\b", re.IGNORECASE)
_PATRON_FACTURA_PRODUCTO = re.compile(r"\d|mayor|precio|receta|costo|insumo|producci", re.IGNORECASE)
_AVISO_SIN_DRIVE = "La conexión con Drive todavía no está configurada."


async def _iniciar_factura(update: Update, chat_id: int) -> None:
    if not drive_clientes.configurado():
        await update.message.reply_text(_AVISO_SIN_DRIVE)
        return
    _chat_clientes.pop(chat_id, None)
    _chat_ver_cotizaciones.discard(chat_id)
    _chat_factura[chat_id] = facturas.iniciar()
    await update.message.reply_text(facturas.siguiente_pregunta(_chat_factura[chat_id]))


async def _continuar_factura(update: Update, chat_id: int, texto: str) -> None:
    estado = _chat_factura[chat_id]
    if _PATRON_CANCELAR_FLUJO.match(texto):
        del _chat_factura[chat_id]
        await update.message.reply_text("Ok, no guardé la factura.")
        return
    if estado["preguntando"] == "confirmacion":
        if not mayorista.es_si(texto):
            await update.message.reply_text('Responde "sí" para guardarla o "cancelar".')
            return
        await update.message.reply_text("Subiendo la factura...")
        try:
            mensaje = await asyncio.to_thread(facturas.guardar, estado)
        except drive_clientes.ErrorDrive:
            await update.message.reply_text('No pude subirla a Drive. Responde "sí" para reintentar o "cancelar".')
            return
        del _chat_factura[chat_id]
        await update.message.reply_text(mensaje)
        return
    error = facturas.aplicar_respuesta(estado, texto)
    await update.message.reply_text(error or facturas.siguiente_pregunta(estado))


async def _recibir_archivo_factura(update: Update, chat_id: int, archivo, tipo: str | None, tamano: int | None) -> None:
    estado = _chat_factura[chat_id]
    if estado["preguntando"] != "archivo":
        await update.message.reply_text("Todavía no necesito el archivo.\n\n" + facturas.siguiente_pregunta(estado))
        return
    if tipo not in ("application/pdf", "image/jpeg", "image/png"):
        await update.message.reply_text("Envíame la factura en PDF, JPG o PNG.")
        return
    if tamano and tamano > facturas.MAX_BYTES:
        await update.message.reply_text("El archivo es demasiado grande: el máximo es 20 MB.")
        return
    descarga = await archivo.get_file()
    facturas.recibir_archivo(estado, bytes(await descarga.download_as_bytearray()), tipo)
    await update.message.reply_text(facturas.siguiente_pregunta(estado))


async def recibir_documento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id not in _chat_factura:
        await update.message.reply_text("Para adjuntar una factura, primero escribe /factura.")
        return
    documento = update.message.document
    await _recibir_archivo_factura(update, chat_id, documento, documento.mime_type, documento.file_size)


async def _iniciar_asociar(update: Update, chat_id: int) -> None:
    if not drive_clientes.configurado():
        await update.message.reply_text(_AVISO_SIN_DRIVE)
        return
    estado = facturas.iniciar_asociar()
    if estado is None:
        await update.message.reply_text("No hay facturas sin cotización.")
        return
    _chat_asociar[chat_id] = estado
    await update.message.reply_text(facturas.siguiente_pregunta_asociar(estado))


async def _continuar_asociar(update: Update, chat_id: int, texto: str) -> None:
    estado = _chat_asociar[chat_id]
    if _PATRON_CANCELAR_FLUJO.match(texto):
        del _chat_asociar[chat_id]
        await update.message.reply_text("Ok, no cambié nada.")
        return
    try:
        mensaje, terminado = await asyncio.to_thread(facturas.aplicar_asociar, estado, texto)
    except drive_clientes.ErrorDrive:
        await update.message.reply_text('No pude actualizarla en Drive. Responde el número de nuevo o "cancelar".')
        return
    if terminado:
        del _chat_asociar[chat_id]
    await update.message.reply_text(mensaje or facturas.siguiente_pregunta_asociar(estado))


async def factura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_factura(update, update.effective_chat.id)


async def asociar_factura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_asociar(update, update.effective_chat.id)


async def subir_cotizaciones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not drive_clientes.configurado():
        await update.message.reply_text(_AVISO_SIN_DRIVE)
        return
    await update.message.reply_text("Guardando las cotizaciones en Drive...")
    subidas, ya_estaban, errores = await asyncio.to_thread(drive_clientes.subir_cotizaciones_pendientes)
    texto = f"Listo: {subidas} subidas y {ya_estaban} ya estaban."
    if errores:
        texto += f" {errores} fallaron; vuelve a escribir /subircotizaciones para reintentar."
    await update.message.reply_text(texto)


async def recibir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id in _chat_factura:
        foto = update.message.photo[-1]
        await _recibir_archivo_factura(update, chat_id, foto, "image/jpeg", foto.file_size)
        return
    archivo = await update.message.photo[-1].get_file()
    contenido = bytes(await archivo.download_as_bytearray())
    try:
        texto = recipe_import.extraer_de_imagen(contenido)
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"No pude leer la imagen (OCR falló: {exc}). Prueba con una foto más nítida.")
        return
    metadata = recipe_import.RawExtraction(texto_crudo=texto, fuente_tipo="imagen", exitosa=bool(texto.strip()))
    if not texto.strip():
        metadata.advertencias.append("El OCR no encontró texto legible en la imagen.")
    await _iniciar_importacion(update, chat_id, texto, metadata)


_RESPUESTAS_ACCESO = {
    "pedir": "¡Hola! Tu sesión está cerrada. Por favor, ingresa tu clave para continuar.",
    "incorrecta": "Clave incorrecta. Inténtalo de nuevo.",
    "bloqueado": "Demasiados intentos. Vuelve a intentarlo en 15 minutos.",
    "sin_clave": "El acceso no está disponible en este momento.",
}


_PATRON_SALIR = re.compile(r"\s*/?salir\s*[.!]?\s*", re.IGNORECASE)


def _flujo_en_curso(chat_id: int) -> str | None:
    """Lo que se perderia si otra accion lo interrumpe."""
    for estado, nombre in ((_chat_cotizacion, "una cotización"), (_chat_factura, "una factura"),
                           (_chat_asociar, "asociar una factura"), (_chat_sync_recetas, "una sincronización de recetas"),
                           (_chat_sincronizacion, "una sincronización de clientes"),
                           (_chat_gestion_mayorista, "un cambio en la lista mayorista"),
                           (_chat_importacion, "importar una receta")):
        if chat_id in estado:
            return nombre
    return None


def _limpiar_consultas(chat_id: int) -> None:
    _chat_clientes.pop(chat_id, None)
    _chat_ver_cotizaciones.discard(chat_id)
    _chat_calculo.pop(chat_id, None)
    _chat_masa.pop(chat_id, None)


def _cancelar_flujos(chat_id: int) -> None:
    for estado in (_chat_importacion, _chat_cotizacion, _chat_gestion_mayorista, _chat_sincronizacion, _chat_sync_recetas,
                   _chat_factura, _chat_asociar, _chat_ultima_pregunta):
        estado.pop(chat_id, None)
    _limpiar_consultas(chat_id)


def _olvidar_chat(chat_id: int) -> None:
    """Al cerrar sesion no debe quedar la conversacion ni un flujo a medias."""
    for estado in (_chat_messages, _chat_ultima_lista, _chat_ultima_receta):
        estado.pop(chat_id, None)
    _cancelar_flujos(chat_id)


async def verificar_acceso(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Corre antes que todos los demas handlers (grupo -1): si la cuenta no esta
    autorizada, ningun comando, foto ni mensaje llega al agente."""
    usuario = update.effective_user
    mensaje = update.effective_message
    if usuario is None or mensaje is None:
        raise ApplicationHandlerStop
    if update.callback_query:
        # el texto de un boton es del bot: nunca cuenta como intento de clave
        if acceso.esta_autorizado(usuario.id):
            return
        await update.callback_query.answer("Tu sesión terminó. Escribe tu clave para continuar.", show_alert=True)
        raise ApplicationHandlerStop
    if acceso.esta_autorizado(usuario.id):
        if mensaje.text and _PATRON_SALIR.fullmatch(mensaje.text):
            acceso.cerrar_sesion(usuario.id)
            _olvidar_chat(mensaje.chat.id)
            await mensaje.reply_text("Sesión cerrada.", reply_markup=ReplyKeyboardRemove())
            raise ApplicationHandlerStop
        # un comando deja atras el calculo a medias: si no, este se quedaria con sus respuestas
        if mensaje.text and mensaje.text.startswith("/") and not menu.PATRON_MENU.fullmatch(mensaje.text):
            _chat_calculo.pop(mensaje.chat.id, None)
            _chat_masa.pop(mensaje.chat.id, None)
        return

    # un comando, el boton de menu o una foto nunca cuentan como intento de clave
    es_comando = bool(mensaje.text) and (mensaje.text.startswith("/") or bool(menu.PATRON_MENU.fullmatch(mensaje.text)))
    resultado = acceso.intentar_clave(usuario.id, None if es_comando else mensaje.text)
    if resultado == "correcta":
        # para que la clave no quede a la vista en el chat
        try:
            await mensaje.delete()
        except TelegramError:
            logging.warning("No se pudo borrar el mensaje con la clave")
        await mensaje.chat.send_message("Clave correcta. Tu sesión dura 24 horas; escribe tu consulta o usa el menú.")
        await _enviar_menu(context.bot, mensaje.chat.id)
    else:
        await mensaje.reply_text(_RESPUESTAS_ACCESO[resultado], reply_markup=ReplyKeyboardRemove())
    raise ApplicationHandlerStop


# --- Botones ------------------------------------------------------------------
#
# Un boton de respuesta manda el mismo texto que se podria escribir, por el mismo
# camino. Solo vale para la ultima pregunta: un boton viejo no puede responder otra.
_TEXTO_MENU = "¿Qué necesitas?"
_TEXTO_ADMINISTRACION = "Administración"
_TEXTO_RECETAS = "Elige un producto:"
_TEXTO_PRODUCCION = ('Para registrar lo producido, escríbelo así: "hoy hicimos 100 facturas de membrillo".\n\n'
                     "También puedes ver el costo de lo que llevas hoy.")
_RUTA_IMAGEN_MENU = Path(__file__).resolve().parent.parent / "assets" / "menu.jpg"
_id_imagen_menu: str | None = None
_chat_ultima_pregunta: dict[int, int] = {}
_chat_calculo: dict[int, dict] = {}
_chat_masa: dict[int, dict] = {}
_chat_ultima_receta: dict[int, tuple[str, str]] = {}
_PATRON_CANTIDAD = re.compile(r"\d+(?:[.,]\d+)?")
MAX_CANTIDAD = 100000


def _hay_flujo(chat_id: int) -> bool:
    return bool(_flujo_en_curso(chat_id)) or chat_id in _chat_clientes or chat_id in _chat_ver_cotizaciones or chat_id in _chat_calculo \
        or chat_id in _chat_masa


async def _enviar_menu(bot, chat_id: int) -> None:
    """Telegram guarda la imagen al primer envio: despues basta con su identificador."""
    global _id_imagen_menu
    try:
        if _id_imagen_menu:
            await bot.send_photo(chat_id=chat_id, photo=_id_imagen_menu, caption=_TEXTO_MENU, reply_markup=menu.principal())
            return
        with open(_RUTA_IMAGEN_MENU, "rb") as imagen:
            enviado = await bot.send_photo(chat_id=chat_id, photo=imagen, caption=_TEXTO_MENU, reply_markup=menu.principal())
        _id_imagen_menu = enviado.photo[-1].file_id
    except (TelegramError, OSError):
        # el menu importa mas que la imagen
        logging.warning("No se pudo enviar la imagen del menú")
        await bot.send_message(chat_id, _TEXTO_MENU, reply_markup=menu.principal())


class _BotConBotones(ExtBot):
    """Agrega los botones a todos los mensajes, para no repetirlo en cada flujo."""

    async def send_message(self, chat_id, text, *args, **opciones):
        if opciones.get("reply_markup") is None:
            botones = menu.botones_de_respuesta(text) if _hay_flujo(chat_id) else None
            opciones["reply_markup"] = botones or menu.TECLADO_PERSISTENTE
        enviado = await super().send_message(chat_id, text, *args, **opciones)
        if menu.es_pregunta(opciones["reply_markup"]):
            _chat_ultima_pregunta[chat_id] = enviado.message_id
        return enviado


class _MensajeDeBoton:
    def __init__(self, bot, chat_id: int, texto: str) -> None:
        self._bot, self._chat_id, self.text = bot, chat_id, texto

    async def reply_text(self, texto: str, **opciones):
        return await self._bot.send_message(self._chat_id, texto, **opciones)

    async def reply_document(self, **opciones):
        return await self._bot.send_document(self._chat_id, **opciones)


class _UpdateDeBoton:
    """Deja que un boton use las mismas funciones que un mensaje escrito."""

    def __init__(self, update: Update, bot, texto: str = "") -> None:
        self.effective_chat = update.effective_chat
        self.effective_user = update.effective_user
        self.message = _MensajeDeBoton(bot, update.effective_chat.id, texto)


async def _quitar_botones(query) -> None:
    try:
        await query.edit_message_reply_markup(None)
    except TelegramError:
        logging.info("No se pudieron quitar los botones de un mensaje")


async def _editar(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str, botones) -> None:
    try:
        await update.callback_query.edit_message_text(texto[:MAX_TEXTO_BOTON], reply_markup=botones)
    except TelegramError:
        # un mensaje muy antiguo ya no se puede editar
        await context.bot.send_message(update.effective_chat.id, texto[:MAX_TEXTO_BOTON], reply_markup=botones)


MAX_TEXTO_BOTON = 4000
_HERRAMIENTAS_DE_RECETA = {"herramienta_receta_estandar", "herramienta_escalar_ingredientes", "herramienta_escalar_por_lotes",
                           "herramienta_escalar_receta", "herramienta_buscar_receta"}


def _receta_de(i: int, j: int) -> tuple[str, str]:
    producto = menu.productos()[i]
    return producto, menu.variantes(producto)[j]


def _recordar_receta(chat_id: int, producto: str, variante: str, pedido: str, respuesta: str) -> None:
    """Lo resuelto sin el agente tambien es parte de la conversacion: sin esto, el agente
    sigue hablando del ultimo producto que el vio (se pedian lotes de brownie viendo su
    receta en los botones, y respondia con alfajores)."""
    _chat_ultima_receta[chat_id] = (producto, variante)
    _chat_messages.setdefault(chat_id, []).extend([("human", pedido), ("ai", respuesta)])


async def _navegar_recetas(update: Update, context: ContextTypes.DEFAULT_TYPE, tipo: str, partes: list[int]) -> None:
    chat_id = update.effective_chat.id
    if tipo == "rp":
        producto = menu.productos()[partes[0]]
        variantes = menu.variantes(producto)
        if len(variantes) > 1:
            await _editar(update, context, f"{tools._legible(producto)}: elige una opción:", menu.teclado_variantes(partes[0], producto))
            return
        partes = [partes[0], 0]
        tipo = "rv"
    producto, variante = _receta_de(*partes)
    nombre = f"{tools._legible(producto)} {tools._legible(variante)}".strip()
    if tipo == "rv":
        hay_mas = len(menu.variantes(producto)) > 1
        receta = tools.receta_estandar(producto, variante)
        _recordar_receta(chat_id, producto, variante, f"Muéstrame la receta de {nombre}.", receta)
        await _editar(update, context, receta, menu.teclado_receta(*partes, hay_mas))
        return
    en_curso = _flujo_en_curso(chat_id)
    if en_curso:
        await context.bot.send_message(chat_id, f"Tienes {en_curso} sin terminar. Termínala o cancélala primero.",
                                       reply_markup=menu.cancelar_en_curso())
        return
    _limpiar_consultas(chat_id)
    if tipo == "rl":
        rinde = tools.rinde_del_lote(producto, variante)
        if rinde is None:
            await context.bot.send_message(chat_id, tools.escalar_por_lotes(producto, variante, 1))
            return
        _chat_calculo[chat_id] = {"producto": producto, "variante": variante, "nombre": nombre, "en_lotes": True}
        await context.bot.send_message(chat_id, f"¿Cuántos lotes de {nombre}? Un lote rinde {rinde:g}. Elige o escribe el número.",
                                       reply_markup=menu.teclado_lotes())
        return
    if tipo == "rc":
        _chat_calculo[chat_id] = {"producto": producto, "variante": variante, "nombre": nombre}
        await context.bot.send_message(chat_id, f"¿Cuántas unidades de {nombre}? Elige o escribe el número.",
                                       reply_markup=menu.teclado_cantidades())
        return
    await responder(_UpdateDeBoton(update, context.bot, f"¿Cómo se prepara {nombre}? Muéstrame el procedimiento."), context)
    _chat_ultima_receta[chat_id] = (producto, variante)


async def _continuar_calculo(update: Update, chat_id: int, texto: str) -> None:
    estado = _chat_calculo[chat_id]
    if _PATRON_CANCELAR_FLUJO.match(texto):
        del _chat_calculo[chat_id]
        await update.message.reply_text("Ok.")
        return
    if "opciones" in estado:
        await _elegir_receta_de_lotes(update, chat_id, estado, texto)
        return
    numero = _PATRON_CANTIDAD.search(texto)
    cantidad = float(numero.group(0).replace(",", ".")) if numero else 0
    if not 0 < cantidad <= MAX_CANTIDAD:
        await update.message.reply_text("Escribe cuántos lotes, por ejemplo 4, o \"cancelar\"." if estado.get("en_lotes")
                                        else 'Escribe cuántas unidades, por ejemplo 24, o "cancelar".')
        return
    del _chat_calculo[chat_id]
    if estado.get("en_lotes"):
        await _enviar_lotes(update, chat_id, estado["producto"], estado["variante"], cantidad)
        return
    respuesta = tools.escalar_ingredientes(estado["producto"], estado["variante"], cantidad)
    try:
        respuesta += "\n\n" + tools.escalar_receta(estado["producto"], estado["variante"], cantidad)
    except ValueError as exc:
        respuesta += f"\n\nNo pude calcular el costo: {exc}"
    _recordar_receta(chat_id, estado["producto"], estado["variante"], f"Calcula {cantidad:g} unidades de {estado['nombre']}.", respuesta)
    await update.message.reply_text(respuesta[:MAX_TEXTO_BOTON], reply_markup=menu.volver_al_menu())


# --- Lotes --------------------------------------------------------------------
#
# En cocina se trabaja por lotes, y "4 lotes" no puede depender de que el LLM recuerde de
# qué receta se habla ni de que multiplique bien: se observo en produccion que devolvia 4
# unidades como si fueran 4 lotes, y que multiplicaba sobre su respuesta anterior. Lo que
# no se entienda aca (nombra algo que no es una receta, "hoy hicimos...") sigue al agente,
# que tiene la misma cuenta en herramienta_escalar_por_lotes.
_NUMEROS_ESCRITOS = {"medio": 0.5, "media": 0.5, "un": 1.0, "una": 1.0, "dos": 2.0, "tres": 3.0, "cuatro": 4.0, "cinco": 5.0,
                     "seis": 6.0, "siete": 7.0, "ocho": 8.0, "nueve": 9.0, "diez": 10.0}
_NUMERO = r"\d+(?:[.,]\d+)?"
_PATRON_LOTES = re.compile(rf"(?<![\w.,])({_NUMERO}|{'|'.join(_NUMEROS_ESCRITOS)})\s*(?:lotes?|batch(?:e?s)?|tandas?)\b", re.IGNORECASE)
# "2 recetas de brownie" son dos lotes; "una receta de brownie" sigue pidiendo la receta
_PATRON_RECETAS_DE = re.compile(rf"(?<![\w.,])({_NUMERO}|{'|'.join(n for n, v in _NUMEROS_ESCRITOS.items() if v > 1)})\s*recetas\s+de\b", re.IGNORECASE)
_PATRON_MULTIPLICAR = re.compile(r"\bmultipl\w*", re.IGNORECASE)
_PATRON_POR_N = re.compile(rf"\b(?:x|por)\s*({_NUMERO})(?![\w%])", re.IGNORECASE)
_PATRON_RECETA_POR_N = re.compile(rf"\brecetas?\s*(?:x|por)\s*({_NUMERO})(?![\w%])|\bx\s*({_NUMERO})\s+(?:la\s+|esta\s+|esa\s+)?receta\b", re.IGNORECASE)
_VECES_ESCRITAS = {"el doble": 2.0, "el triple": 3.0, "duplica": 2.0, "triplica": 3.0}
_PATRON_VECES_ESCRITAS = re.compile(rf"\b({'|'.join(_VECES_ESCRITAS)})\b", re.IGNORECASE)
# Lo que puede acompañar a un pedido de lotes sin nombrar una receta.
_PALABRAS_DEL_PEDIDO = {
    "necesito", "necesitamos", "quiero", "queremos", "hacer", "haz", "hazme", "hagamos", "hare", "haremos", "voy", "vamos", "a",
    "hay", "que", "tengo", "tenemos", "de", "del", "la", "el", "los", "las", "lo", "un", "una", "esta", "este", "esa", "ese", "receta",
    "recetas", "calcula", "calcular", "calculame", "calculemos", "dame", "dime", "muestrame", "prepara", "preparar", "preparemos",
    "producir", "por", "favor", "porfa", "ahora", "hoy", "manana", "solo", "otro", "otros", "otra", "otras", "me", "nos", "y", "x",
}


def _pedido_de_lotes(texto: str) -> tuple[float, str] | None:
    """Cuantos lotes se piden y lo que se dice de la receta, o None si no se piden lotes."""
    coincide = (_PATRON_LOTES.search(texto) or _PATRON_RECETAS_DE.search(texto) or _PATRON_RECETA_POR_N.search(texto)
                or _PATRON_VECES_ESCRITAS.search(texto))
    if not coincide and _PATRON_MULTIPLICAR.search(texto):
        coincide = _PATRON_POR_N.search(texto)
    if not coincide:
        return None
    crudo = next(grupo for grupo in coincide.groups() if grupo).lower()
    lotes = _VECES_ESCRITAS.get(crudo) or _NUMEROS_ESCRITOS.get(crudo) or float(crudo.replace(",", "."))
    if not 0 < lotes <= MAX_CANTIDAD:
        return None
    resto = re.split(r"\bpara\b", f"{texto[:coincide.start()]} {texto[coincide.end():]}", maxsplit=1, flags=re.IGNORECASE)[0]
    palabras = [p for p in re.findall(r"\w+", resto) if tools._normalizar(p) not in _PALABRAS_DEL_PEDIDO
                and not _PATRON_MULTIPLICAR.match(p) and not p.isdigit()]
    return lotes, " ".join(palabras)


async def _enviar_lotes(update: Update, chat_id: int, producto: str, variante: str, lotes: float) -> None:
    respuesta = tools.escalar_por_lotes(producto, variante, lotes)
    rinde = tools.rinde_del_lote(producto, variante)
    if rinde:
        try:
            respuesta += "\n\n" + tools.escalar_receta(producto, variante, lotes * rinde)
        except ValueError as exc:
            respuesta += f"\n\nNo pude calcular el costo: {exc}"
    _recordar_receta(chat_id, producto, variante, f"Calcula {lotes:g} lotes de {tools.nombre_receta(producto, variante)}.", respuesta)
    await update.message.reply_text(respuesta[:MAX_TEXTO_BOTON], reply_markup=menu.volver_al_menu())


async def _elegir_receta_de_lotes(update: Update, chat_id: int, estado: dict, texto: str) -> None:
    opciones = estado["opciones"]
    if not re.fullmatch(r"\s*\d{1,3}\s*", texto) or not 1 <= int(texto) <= len(opciones):
        await update.message.reply_text(f'Responde un número del 1 al {len(opciones)}, o "cancelar".')
        return
    del _chat_calculo[chat_id]
    await _enviar_lotes(update, chat_id, *opciones[int(texto) - 1], estado["lotes"])


async def _atender_lotes(update: Update, chat_id: int, texto: str) -> bool:
    """Devuelve False si el mensaje no es un pedido de lotes que se entienda aca."""
    pedido = _pedido_de_lotes(texto)
    if pedido is None:
        return False
    lotes, nombre = pedido
    recetas = tools.recetas_que_calzan(nombre) if nombre else [_chat_ultima_receta[chat_id]] if chat_id in _chat_ultima_receta else []
    if nombre and not recetas:
        return False
    cifra = f"{lotes:g}".replace(".", ",")
    if not recetas:
        await update.message.reply_text(f"¿De qué receta quieres {cifra} {'lote' if lotes <= 1 else 'lotes'}? Elige el producto, "
                                        f'o escríbelo: "{cifra} lotes de brownie".', reply_markup=menu.teclado_productos())
    elif len(recetas) == 1:
        await _enviar_lotes(update, chat_id, *recetas[0], lotes)
    else:
        _chat_calculo[chat_id] = {"opciones": recetas, "lotes": lotes}
        lista = "\n".join(f"{i}. {tools.nombre_receta(*r)}" for i, r in enumerate(recetas, start=1))
        await update.message.reply_text(f"¿De cuál quieres {cifra} {'lote' if lotes <= 1 else 'lotes'}?\n{lista}\n\n"
                                        'Responde el número o "cancelar".')
    return True


async def _preguntar_masa(update: Update, chat_id: int, texto: str | None = None) -> None:
    estado = _chat_masa[chat_id]
    await update.message.reply_text(texto or flujo_masa.siguiente_pregunta(estado),
                                    reply_markup=menu.teclado_masa(flujo_masa.opciones(estado), flujo_masa.puede_volver(estado)))


async def _iniciar_masa(update: Update, chat_id: int) -> None:
    _chat_masa[chat_id] = flujo_masa.iniciar()
    await _preguntar_masa(update, chat_id)


async def _continuar_masa(update: Update, chat_id: int, texto: str) -> None:
    estado = _chat_masa[chat_id]
    if _PATRON_CANCELAR_FLUJO.match(texto):
        del _chat_masa[chat_id]
        await update.message.reply_text("Ok.")
        return
    error = flujo_masa.aplicar_respuesta(estado, texto)
    if error:
        await _preguntar_masa(update, chat_id, error)
        return
    if estado["preguntando"]:
        await _preguntar_masa(update, chat_id)
        return
    resultado = flujo_masa.calcular(estado)
    if resultado is None:
        await _preguntar_masa(update, chat_id)
        return
    del _chat_masa[chat_id]
    await update.message.reply_text(resultado, reply_markup=menu.otra_masa())


async def _accion_de_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, accion: str) -> None:
    chat_id = update.effective_chat.id
    boton = _UpdateDeBoton(update, context.bot)
    if accion == "cancelar":
        _cancelar_flujos(chat_id)
        await boton.message.reply_text("Listo, cancelado.")
        await _enviar_menu(context.bot, chat_id)
        return
    if accion == "salir":
        acceso.cerrar_sesion(update.effective_user.id)
        _olvidar_chat(chat_id)
        await boton.message.reply_text("Sesión cerrada.", reply_markup=ReplyKeyboardRemove())
        return
    if accion == "recetas":
        # en un mensaje nuevo: lo calculado sigue a la vista
        await boton.message.reply_text(_TEXTO_RECETAS, reply_markup=menu.teclado_productos())
        return
    if accion == "lista":
        await _enviar_pdf(boton, mayorista.generar_pdf_lista())
        return
    if accion == "avisos":
        await avisos(boton, context)
        return
    if accion == "costo_hoy":
        hoy = datetime.now(sync_automatica.ZONA).date().isoformat()
        await boton.message.reply_text(tools.costo_diario(hoy))
        return

    en_curso = _flujo_en_curso(chat_id)
    if en_curso:
        await boton.message.reply_text(f"Tienes {en_curso} sin terminar. Termínala o cancélala primero.",
                                       reply_markup=menu.cancelar_en_curso())
        return
    _limpiar_consultas(chat_id)
    if accion == "masa":
        await _iniciar_masa(boton, chat_id)
    elif accion == "cotizar":
        await _iniciar_cotizacion(boton, chat_id)
    elif accion == "cotizaciones":
        await _mostrar_cotizaciones(boton, chat_id)
    elif accion == "clientes":
        await _consultar_clientes(boton, chat_id)
    elif accion == "factura":
        await _iniciar_factura(boton, chat_id)
    elif accion == "asociar":
        await _iniciar_asociar(boton, chat_id)
    elif accion == "sync_recetas":
        await _iniciar_sync_recetas(boton, chat_id)
    elif accion == "sync_clientes":
        await _iniciar_sincronizacion(boton, chat_id)
    elif accion in ("agregar", "quitar"):
        await _iniciar_gestion_mayorista(boton, chat_id, accion)
    elif accion == "subir":
        await subir_cotizaciones(boton, context)


async def pulsar_boton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = update.effective_chat.id
    dato = query.data or ""

    if dato.startswith(menu.PREFIJO_RESPUESTA):
        if not _hay_flujo(chat_id) or query.message.message_id != _chat_ultima_pregunta.get(chat_id):
            await query.answer("Esta pregunta ya no está vigente.", show_alert=True)
            await _quitar_botones(query)
            return
        await query.answer()
        await _quitar_botones(query)
        await responder(_UpdateDeBoton(update, context.bot, dato[len(menu.PREFIJO_RESPUESTA):]), context)
        return

    await query.answer()
    tipo, _, resto = dato.partition(":")
    if tipo == "a":
        await _accion_de_menu(update, context, resto)
    elif tipo == "m":
        pantallas = {"principal": (_TEXTO_MENU, menu.principal), "admin": (_TEXTO_ADMINISTRACION, menu.administracion),
                     "recetas": (_TEXTO_RECETAS, menu.teclado_productos), "produccion": (_TEXTO_PRODUCCION, menu.produccion)}
        if resto in pantallas:
            texto, teclado = pantallas[resto]
            await _editar(update, context, texto, teclado())
    elif tipo in ("rp", "rv", "rc", "rl", "rt"):
        try:
            await _navegar_recetas(update, context, tipo, [int(n) for n in resto.split(":")])
        except IndexError:
            # el catalogo cambio desde que se dibujo este boton
            await _editar(update, context, _TEXTO_RECETAS, menu.teclado_productos())


async def menu_comando(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _enviar_menu(context.bot, update.effective_chat.id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Agente interno Malatesta. Usa los botones o pregúntame por recetas, costos de "
        "fabricación para un pedido, o el costo de producción del día."
    )
    await _enviar_menu(context.bot, update.effective_chat.id)


def _recordar_receta_del_agente(chat_id: int, mensajes: list) -> None:
    """Un "4 lotes" despues de hablar con el agente es de la receta que el consulto. Si no
    consulto una sola, no se sabe de cual: se pregunta, no se usa una anterior."""
    _chat_ultima_receta.pop(chat_id, None)
    for mensaje in reversed(mensajes):
        if isinstance(mensaje, HumanMessage):
            return
        for llamada in reversed(getattr(mensaje, "tool_calls", None) or []):
            if llamada["name"] in _HERRAMIENTAS_DE_RECETA:
                recetas = tools.recetas_que_calzan(f"{llamada['args'].get('producto', '')} {llamada['args'].get('variante', '')}".strip())
                if len(recetas) == 1:
                    _chat_ultima_receta[chat_id] = recetas[0]
                return


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    texto = update.message.text

    if menu.PATRON_MENU.fullmatch(texto):
        await _enviar_menu(context.bot, chat_id)
        return

    if chat_id in _chat_calculo:
        await _continuar_calculo(update, chat_id, texto)
        return

    if chat_id in _chat_masa:
        await _continuar_masa(update, chat_id, texto)
        return

    if chat_id in _chat_cotizacion:
        await _continuar_cotizacion(update, chat_id, texto)
        return

    if chat_id in _chat_factura:
        await _continuar_factura(update, chat_id, texto)
        return

    if chat_id in _chat_asociar:
        await _continuar_asociar(update, chat_id, texto)
        return

    if chat_id in _chat_sync_recetas:
        await _continuar_sync_recetas(update, chat_id, texto)
        return

    if chat_id in _chat_sincronizacion:
        await _continuar_sincronizacion(update, chat_id, texto)
        return

    if _PATRON_SINCRONIZAR_RECETAS.search(texto):
        await _iniciar_sync_recetas(update, chat_id)
        return

    if _PATRON_SINCRONIZAR.search(texto):
        await _iniciar_sincronizacion(update, chat_id)
        return

    if chat_id in _chat_clientes and await _continuar_clientes(update, chat_id, texto):
        return

    if chat_id in _chat_ver_cotizaciones:
        # solo un numero (o cancelar) continua; cualquier otra cosa sale del
        # historial y se atiende como mensaje normal
        if re.fullmatch(r"\s*(n[°º.]?\s*)?\d+\s*", texto, re.IGNORECASE) or _PATRON_CANCELAR_FLUJO.match(texto):
            await _reenviar_cotizacion(update, chat_id, texto)
            return
        _chat_ver_cotizaciones.discard(chat_id)

    if _PATRON_VER_COTIZACIONES.search(texto):
        await _mostrar_cotizaciones(update, chat_id)
        return

    if chat_id in _chat_gestion_mayorista:
        await _continuar_gestion_mayorista(update, chat_id, texto)
        return

    if chat_id in _chat_importacion:
        await _continuar_importacion(update, chat_id, texto)
        return

    # con un numero es casi seguro un cambio de precio ("sube el alfajor de la
    # lista mayorista a 2000"), eso lo resuelve el agente
    consulta_clientes = _PATRON_VER_CLIENTES.search(texto)
    if consulta_clientes:
        busqueda = consulta_clientes.group("busqueda")
        await _consultar_clientes(update, chat_id, "" if _PATRON_RELLENO_CLIENTES.match(busqueda) else busqueda)
        return

    ficha_nombre = _PATRON_FICHA_NOMBRE.search(texto)
    if ficha_nombre:
        encontrados = mayorista.consultar_clientes(ficha_nombre.group("busqueda"))
        if encontrados:
            await _mostrar_opciones_clientes(update, chat_id, encontrados)
            return

    if _PATRON_AGREGAR_MAYORISTA.search(texto):
        await _iniciar_gestion_mayorista(update, chat_id, "agregar")
        return

    if _PATRON_QUITAR_MAYORISTA.search(texto):
        await _iniciar_gestion_mayorista(update, chat_id, "quitar")
        return

    if not _PATRON_FACTURA_PRODUCTO.search(texto):
        if _PATRON_ASOCIAR_FACTURA.search(texto):
            await _iniciar_asociar(update, chat_id)
            return
        if _PATRON_ADJUNTAR_FACTURA.search(texto):
            await _iniciar_factura(update, chat_id)
            return

    if _PATRON_LISTA_MAYORISTA.search(texto) and not re.search(r"\d", texto):
        await _enviar_pdf(update, mayorista.generar_pdf_lista())
        return

    if _PATRON_COTIZACION.search(texto):
        await _iniciar_cotizacion(update, chat_id)
        return

    url_match = _PATRON_URL.search(texto)
    if url_match:
        url = url_match.group(0)
        metadata = recipe_import.extraer_de_url(url if url.lower().startswith("http") else f"https://{url}")
        await _iniciar_importacion(update, chat_id, metadata.texto_crudo, metadata)
        return

    prefijo_match = _PREFIJO_RECETA.match(texto)
    if prefijo_match:
        texto_receta = prefijo_match.group(1)
        metadata = recipe_import.RawExtraction(texto_crudo=texto_receta, fuente_tipo="texto_pegado")
        await _iniciar_importacion(update, chat_id, texto_receta, metadata)
        return

    if await _atender_lotes(update, chat_id, texto):
        return

    ultima_lista = _chat_ultima_lista.get(chat_id, {})
    pregunta = _expandir_respuesta_numerica(texto, ultima_lista)

    graph = _get_graph()
    messages = _chat_messages.setdefault(chat_id, [])
    messages.append(("human", pregunta))

    resultado = graph.invoke({"messages": messages})
    _chat_messages[chat_id] = _recortar_historial(resultado["messages"])
    _recordar_receta_del_agente(chat_id, resultado["messages"])
    respuesta = resultado["messages"][-1].content

    nueva_lista = _extraer_lista_numerada(respuesta)
    if nueva_lista:
        _chat_ultima_lista[chat_id] = nueva_lista

    await update.message.reply_text(respuesta)


def construir_aplicacion(token: str) -> Application:
    app = Application.builder().bot(_BotConBotones(token=token)).post_init(_al_iniciar).build()
    app.add_handler(TypeHandler(Update, verificar_acceso), group=-1)
    app.add_handler(CallbackQueryHandler(pulsar_boton))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_comando))
    app.add_handler(CommandHandler("cotizacion", cotizacion))
    app.add_handler(CommandHandler("listamayorista", lista_mayorista))
    app.add_handler(CommandHandler("agregarmayorista", agregar_mayorista))
    app.add_handler(CommandHandler("quitarmayorista", quitar_mayorista))
    app.add_handler(CommandHandler("cotizaciones", cotizaciones))
    app.add_handler(CommandHandler("clientes", clientes))
    app.add_handler(CommandHandler("sincronizarclientes", sincronizar_clientes))
    app.add_handler(CommandHandler("sincronizarrecetas", sincronizar_recetas))
    app.add_handler(CommandHandler("avisos", avisos))
    app.add_handler(CommandHandler("factura", factura))
    app.add_handler(CommandHandler("asociarfactura", asociar_factura))
    app.add_handler(CommandHandler("subircotizaciones", subir_cotizaciones))
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_documento))
    app.add_handler(MessageHandler(filters.PHOTO, recibir_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    return app


def main() -> None:
    sync_server.start_background()
    construir_aplicacion(os.environ["TELEGRAM_BOT_TOKEN"]).run_polling()


if __name__ == "__main__":
    main()
