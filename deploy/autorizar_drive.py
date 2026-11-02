"""Autoriza al bot a guardar archivos en el Drive de la panaderia.

Se corre una sola vez en el computador, con el JSON del cliente OAuth de Google
("App de escritorio"). Abre el navegador, y el token resultante queda en el
portapapeles para pegarlo en Railway: no se imprime para que no quede en pantalla.

    python deploy/autorizar_drive.py ruta/al/cliente_oauth.json
"""
from __future__ import annotations

import http.server
import json
import secrets
import subprocess
import sys
import urllib.parse
import webbrowser

import requests

ALCANCE = "https://www.googleapis.com/auth/drive.file"
CUENTA = "oficialmalatesta@gmail.com"


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as archivo:
        datos = json.load(archivo)["installed"]
    respuesta: dict[str, str] = {}

    class Receptor(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            respuesta.update(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Listo, ya puedes cerrar esta ventana.".encode())

        def log_message(self, *args):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Receptor)
    redireccion = f"http://127.0.0.1:{servidor.server_port}/"
    estado = secrets.token_urlsafe(16)
    webbrowser.open(datos["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": datos["client_id"], "redirect_uri": redireccion, "response_type": "code", "scope": ALCANCE,
        "access_type": "offline", "prompt": "consent", "login_hint": CUENTA, "state": estado}))
    print("Autoriza en el navegador con", CUENTA)
    servidor.handle_request()

    if respuesta.get("state") != estado or "code" not in respuesta:
        sys.exit("No se completó la autorización.")
    token = requests.post(datos["token_uri"], timeout=30, data={
        "code": respuesta["code"], "client_id": datos["client_id"], "client_secret": datos["client_secret"],
        "redirect_uri": redireccion, "grant_type": "authorization_code"}).json()
    if "refresh_token" not in token:
        sys.exit("Google no entregó el token. Vuelve a intentarlo.")
    subprocess.run("clip", input=token["refresh_token"].encode("utf-16-le"), check=True)
    print("Listo: el token quedó copiado. Pégalo en Railway como GOOGLE_OAUTH_REFRESH_TOKEN.")


if __name__ == "__main__":
    main()
