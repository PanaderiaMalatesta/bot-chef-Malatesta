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

from . import sync_server
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Agente interno Malatesta. Pregúntame por recetas, costos de "
        "fabricación para un pedido, o el costo de producción del día."
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ultima_lista = _chat_ultima_lista.get(chat_id, {})
    pregunta = _expandir_respuesta_numerica(update.message.text, ultima_lista)

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    app.run_polling()


if __name__ == "__main__":
    main()
