"""Resuelve donde viven los datos (CSV/recetario) segun el entorno, y los
mantiene sincronizados entre el repo y el volumen persistente en cada deploy.

En local, DATA_DIR es simplemente la carpeta data/ del repo. En produccion
(Railway), la variable de entorno DATA_DIR apunta a un Volume persistente
(ej. /data) -- necesario porque el contenedor se reconstruye desde el
repo en cada deploy y perderia cualquier cambio hecho por chat (precios,
ingredientes, produccion diaria) si esos archivos vivieran solo en la imagen.

La primera vez que el volumen esta vacio, se "siembra" copiando todos los
datos del repo tal cual.

De ahi en adelante, cada archivo se sincroniza segun si el chat puede
modificarlo o no:
- recetas.md NUNCA se edita por chat (no existe ninguna herramienta para
  eso, solo se toca por git) -- se sincroniza completo del repo en cada
  deploy, para que agregar una receta nueva y hacer push sea suficiente,
  sin tener que entrar por SSH a copiarla a mano al volumen.
- Los CSV de costeo (catalogo_precios.csv, recetas_ingredientes.csv,
  precios_insumos.csv) se mantienen desde la planilla de recetas: el repo solo
  los siembra si el volumen no los tiene. Antes se fusionaban con el repo en
  cada deploy, y eso devolveria lo que se elimino en la planilla.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_data_dir_env = os.environ.get("DATA_DIR")
DATA_DIR = Path(_data_dir_env) if _data_dir_env else REPO_DATA_DIR

# Archivos que nunca se editan por chat -- siempre se sincronizan enteros
# del repo al volumen (el repo manda, sin fusion).
_ARCHIVOS_SIEMPRE_DEL_REPO = ["recetas.md"]

# Archivos que solo se editan por chat: el repo los siembra si el volumen no
# los tiene, y nunca mas los toca. La lista mayorista no se fusiona como los
# CSV de costeo porque ahi quitar un producto por chat es normal, y la fusion
# aditiva lo volveria a agregar desde el repo en el siguiente arranque.
_ARCHIVOS_SOLO_SEMBRAR = ["precios_mayorista.csv", "catalogo_precios.csv", "recetas_ingredientes.csv",
                          "precios_insumos.csv"]


def _sincronizar_data_dir() -> None:
    if DATA_DIR == REPO_DATA_DIR:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not (DATA_DIR / "recetas.md").exists():
        # Volumen vacio: primera siembra completa, copiar todo tal cual.
        for item in REPO_DATA_DIR.iterdir():
            if item.name == "index_recetas":
                continue
            destino = DATA_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, destino, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destino)
        return

    for nombre in _ARCHIVOS_SIEMPRE_DEL_REPO:
        origen = REPO_DATA_DIR / nombre
        if origen.exists():
            shutil.copy2(origen, DATA_DIR / nombre)

    for nombre in _ARCHIVOS_SOLO_SEMBRAR:
        origen = REPO_DATA_DIR / nombre
        if origen.exists() and not (DATA_DIR / nombre).exists():
            shutil.copy2(origen, DATA_DIR / nombre)


_sincronizar_data_dir()
