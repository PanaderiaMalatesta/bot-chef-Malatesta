"""Servidor HTTP interno minimo para que el planificador-malatesta pueda
empujar actualizaciones de precios de insumos sin pasar por Telegram.

Corre en un hilo de fondo junto al polling de Telegram, en el mismo
proceso/servicio. Sin dominio publico -- solo alcanzable por red privada
de Railway (mismo proyecto) o localhost. Deshabilitado por defecto: si no
hay SYNC_SECRET configurado, no abre ningun puerto.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import tools

logger = logging.getLogger(__name__)

SYNC_SECRET = os.environ.get("SYNC_SECRET")
SYNC_PORT = int(os.environ.get("SYNC_PORT", "8090"))


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        logger.info("sync_server: " + format, *args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _autorizado(self) -> bool:
        return bool(SYNC_SECRET) and self.headers.get("X-Sync-Secret") == SYNC_SECRET

    def do_POST(self):  # noqa: N802
        if not self._autorizado():
            self._send_json(401, {"error": "unauthorized"})
            return

        largo = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return

        if self.path == "/sync/precio-insumo":
            insumo = body.get("insumo")
            nuevo_precio = body.get("nuevo_precio")
            if not insumo or nuevo_precio is None:
                self._send_json(400, {"error": "faltan campos insumo/nuevo_precio"})
                return
            try:
                mensaje = tools.crear_o_actualizar_insumo(insumo, float(nuevo_precio), body.get("unidad", "kg"))
            except Exception as exc:  # noqa: BLE001
                self._send_json(500, {"error": str(exc)})
                return
            self._send_json(200, {"mensaje": mensaje})
            return

        if self.path == "/sync/producto":
            producto = body.get("producto")
            variante = body.get("variante", "")
            lineas = body.get("lineas")
            if not producto or not lineas:
                self._send_json(400, {"error": "faltan campos producto/lineas"})
                return
            try:
                mensaje = tools.reemplazar_receta_completa(
                    producto, variante, lineas,
                    categoria=body.get("categoria"),
                    precio_venta=body.get("precio_venta"),
                    tiempo_fabricacion_min=body.get("tiempo_fabricacion_min"),
                )
            except Exception as exc:  # noqa: BLE001
                self._send_json(500, {"error": str(exc)})
                return
            self._send_json(200, {"mensaje": mensaje})
            return

        if self.path == "/sync/producto-eliminar":
            producto = body.get("producto")
            variante = body.get("variante", "")
            if not producto:
                self._send_json(400, {"error": "falta campo producto"})
                return
            try:
                mensaje = tools.eliminar_producto(producto, variante, confirmado=True)
            except Exception as exc:  # noqa: BLE001
                self._send_json(500, {"error": str(exc)})
                return
            self._send_json(200, {"mensaje": mensaje})
            return

        self._send_json(404, {"error": "not found"})


def start_background() -> None:
    """Arranca el servidor en un hilo daemon. No-op si falta SYNC_SECRET.

    Si falla el bind del puerto (o cualquier otro error), se registra pero
    NUNCA se propaga -- este servidor es secundario y no debe tumbar el
    bot de Telegram si algo sale mal.
    """
    if not SYNC_SECRET:
        logger.warning("SYNC_SECRET no configurado -- servidor de sincronizacion deshabilitado")
        return
    try:
        server = ThreadingHTTPServer(("0.0.0.0", SYNC_PORT), _Handler)
        hilo = threading.Thread(target=server.serve_forever, daemon=True)
        hilo.start()
        logger.info("Servidor de sincronizacion escuchando en puerto %s", SYNC_PORT)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo iniciar el servidor de sincronizacion, el bot sigue funcionando igual")
