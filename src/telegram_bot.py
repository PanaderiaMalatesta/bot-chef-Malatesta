"""Bot de Telegram -- interfaz principal del agente interno Malatesta.

Usa long-polling (sin webhook), asi que en OCI no hace falta abrir ningun
puerto: el servidor solo hace conexiones salientes hacia la API de Telegram.
"""
from __future__ import annotations

import logging
import os
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import mayorista, recipe_import, recipe_pipeline, sync_server
from .agent import build_agent

load_dotenv()
logging.basicConfig(level=logging.INFO)

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

_PATRON_URL = re.compile(r"https?://\S+")
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
            mensaje = recipe_pipeline.guardar(estado)
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

_PATRON_COTIZACION = re.compile(
    r"^\s*cotiza|\b(hacer|haz|hazme|necesito|quiero|generar?|crear?|nueva|armar?|arma|preparar?)\b.*\bcotizaci",
    re.IGNORECASE,
)
_PATRON_LISTA_MAYORISTA = re.compile(r"lista\s+(de\s+)?precios?\s+(al\s+por\s+)?mayor|lista\s+mayorist", re.IGNORECASE)


async def _enviar_pdf(update: Update, ruta, caption: str | None = None) -> None:
    with open(ruta, "rb") as archivo:
        await update.message.reply_document(document=archivo, filename=ruta.name, caption=caption)


async def _iniciar_cotizacion(update: Update, chat_id: int) -> None:
    estado = mayorista.iniciar()
    _chat_cotizacion[chat_id] = estado
    await update.message.reply_text(
        'Vamos con la cotización mayorista. Puedes escribir "cancelar" en cualquier momento.\n\n'
        + mayorista.siguiente_pregunta(estado)
    )


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
# cada nivel (mayorista.py muestra el costo unitario como referencia).
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


async def recibir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Agente interno Malatesta. Pregúntame por recetas, costos de "
        "fabricación para un pedido, o el costo de producción del día. "
        "Para venta mayorista: /cotizacion, /listamayorista, /agregarmayorista o /quitarmayorista."
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    texto = update.message.text

    if chat_id in _chat_cotizacion:
        await _continuar_cotizacion(update, chat_id, texto)
        return

    if chat_id in _chat_gestion_mayorista:
        await _continuar_gestion_mayorista(update, chat_id, texto)
        return

    if chat_id in _chat_importacion:
        await _continuar_importacion(update, chat_id, texto)
        return

    # con un numero es casi seguro un cambio de precio ("sube el alfajor de la
    # lista mayorista a 2000"), eso lo resuelve el agente
    if _PATRON_AGREGAR_MAYORISTA.search(texto):
        await _iniciar_gestion_mayorista(update, chat_id, "agregar")
        return

    if _PATRON_QUITAR_MAYORISTA.search(texto):
        await _iniciar_gestion_mayorista(update, chat_id, "quitar")
        return

    if _PATRON_LISTA_MAYORISTA.search(texto) and not re.search(r"\d", texto):
        await _enviar_pdf(update, mayorista.generar_pdf_lista())
        return

    if _PATRON_COTIZACION.search(texto):
        await _iniciar_cotizacion(update, chat_id)
        return

    url_match = _PATRON_URL.search(texto)
    if url_match:
        metadata = recipe_import.extraer_de_url(url_match.group(0))
        await _iniciar_importacion(update, chat_id, metadata.texto_crudo, metadata)
        return

    prefijo_match = _PREFIJO_RECETA.match(texto)
    if prefijo_match:
        texto_receta = prefijo_match.group(1)
        metadata = recipe_import.RawExtraction(texto_crudo=texto_receta, fuente_tipo="texto_pegado")
        await _iniciar_importacion(update, chat_id, texto_receta, metadata)
        return

    ultima_lista = _chat_ultima_lista.get(chat_id, {})
    pregunta = _expandir_respuesta_numerica(texto, ultima_lista)

    graph = _get_graph()
    messages = _chat_messages.setdefault(chat_id, [])
    messages.append(("human", pregunta))

    resultado = graph.invoke({"messages": messages})
    _chat_messages[chat_id] = _recortar_historial(resultado["messages"])
    respuesta = resultado["messages"][-1].content

    nueva_lista = _extraer_lista_numerada(respuesta)
    if nueva_lista:
        _chat_ultima_lista[chat_id] = nueva_lista

    await update.message.reply_text(respuesta)


def main() -> None:
    sync_server.start_background()
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cotizacion", cotizacion))
    app.add_handler(CommandHandler("listamayorista", lista_mayorista))
    app.add_handler(CommandHandler("agregarmayorista", agregar_mayorista))
    app.add_handler(CommandHandler("quitarmayorista", quitar_mayorista))
    app.add_handler(MessageHandler(filters.PHOTO, recibir_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    app.run_polling()


if __name__ == "__main__":
    main()
