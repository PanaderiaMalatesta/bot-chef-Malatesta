"""Sincroniza recetas e insumos del bot desde una planilla de Google Sheets.

Igual que con los clientes: se descarga, se compara y, tras confirmar en el chat,
la planilla manda. La diferencia es lo que falta en ella: una receta importada por
Telegram todavia no esta en la planilla y no debe perderse, asi que solo se elimina
lo que estuvo en la sincronizacion anterior y ahora ya no esta.

La planilla usa la cantidad del lote y su rendimiento, como se trabaja en cocina; el
bot guarda la cantidad por unidad. La preparacion (recetas.md) no pasa por aqui, ni
las masas: son variables y siguen como estan en el bot.
"""
from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from . import mayorista, planilla_clientes, tools
from .paths import DATA_DIR
from .planilla_clientes import ErrorPlanilla

ID_PLANILLA = "1vADXH22aZ_RZrr2YFOLtouMGia0e0BCLfW7PzdxZGAs"
_PRODUCTOS_FUERA_DE_PLANILLA = {"masaquebrada"}
BASE_PATH = DATA_DIR / "planilla_recetas_base.json"
_UNIDADES_INSUMO = {"kg", "L", "unidad", "porcion"}
_COLUMNAS_RECETA = {"producto": "producto", "variante": "variante", "componente": "componente", "insumo": "insumo",
                    "cantidad del lote": "lote", "unidad": "unidad", "rinde": "rinde"}
_COLUMNAS_INSUMO = {"insumo": "insumo", "precio": "precio", "unidad": "unidad"}
MAX_TEXTO_TELEGRAM = 3800


@dataclass
class Comparacion:
    recetas: dict[tuple, list[dict]]
    insumos: dict[str, dict]
    nuevas: list[tuple] = field(default_factory=list)
    cambiadas: dict[tuple, list[str]] = field(default_factory=dict)
    eliminadas: list[tuple] = field(default_factory=list)
    solo_bot: list[tuple] = field(default_factory=list)
    filas_vacias: int = 0
    insumos_nuevos: list[str] = field(default_factory=list)
    precios: list[str] = field(default_factory=list)
    insumos_eliminados: list[str] = field(default_factory=list)
    insumos_solo_bot: list[str] = field(default_factory=list)
    sin_precio: int = 0
    avisos: list[str] = field(default_factory=list)

    @property
    def hay_cambios(self) -> bool:
        return bool(self.nuevas or self.cambiadas or self.eliminadas or self.filas_vacias or self.insumos_nuevos
                    or self.precios or self.insumos_eliminados)

    @property
    def hay_aplicables(self) -> bool:
        """Lo que se aplica sin autorizacion: todo menos las eliminaciones."""
        return bool(self.nuevas or self.cambiadas or self.filas_vacias or self.insumos_nuevos or self.precios)


def _clave(producto: str, variante: str) -> tuple[str, str]:
    return tools._normalizar(producto), tools._normalizar(variante)


def _limpiar(valor) -> str:
    return " ".join(str(valor).split())


def _numero(valor) -> float | None:
    """La planilla entrega numeros, pero una celda con formato de texto trae "390,5"."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    texto = str(valor).strip().replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return None
    return numero if math.isfinite(numero) else None


def _nombre(producto: str, variante: str) -> str:
    return f"{tools._legible(producto)} {tools._legible(variante)}".strip()


def _tabla(filas: list[list], columnas: dict[str, str], pestana: str) -> list[tuple[int, dict]]:
    if not filas:
        raise ErrorPlanilla(f"La pestaña {pestana} está vacía. No cambié nada.")
    encabezados = {mayorista._normalizar(str(c)).strip(): i for i, c in enumerate(filas[0])}
    faltan = [c for c in columnas if c not in encabezados]
    if faltan:
        raise ErrorPlanilla(f"A la pestaña {pestana} le faltan columnas ({', '.join(faltan)}). No cambié nada.")
    salida = []
    for n, fila in enumerate(filas[1:], start=2):
        datos = {campo: fila[encabezados[col]] if encabezados[col] < len(fila) else ""
                 for col, campo in columnas.items()}
        if any(_limpiar(v) for v in datos.values()):
            salida.append((n, datos))
    return salida


def interpretar(filas_recetas: list[list], filas_insumos: list[list]) -> tuple[dict, dict]:
    """Valida ambas pestañas completas: un dato malo detiene todo, porque un error
    aqui cambia los costos sin que nadie lo note."""
    insumos: dict[str, dict] = {}
    for n, datos in _tabla(filas_insumos, _COLUMNAS_INSUMO, "Insumos"):
        nombre, unidad = _limpiar(datos["insumo"]), _limpiar(datos["unidad"])
        precio = _numero(datos["precio"])
        if not nombre:
            raise ErrorPlanilla(f"Insumos, fila {n}: falta el nombre del insumo. No cambié nada.")
        if nombre.lower() in insumos:
            raise ErrorPlanilla(f"Insumos, fila {n}: {nombre} está repetido. No cambié nada.")
        if precio is None or precio < 0:
            raise ErrorPlanilla(f"Insumos, fila {n}: el precio de {nombre} no es válido. No cambié nada.")
        if unidad not in _UNIDADES_INSUMO:
            raise ErrorPlanilla(f"Insumos, fila {n}: la unidad de {nombre} debe ser kg, L, unidad o porcion. "
                                "No cambié nada.")
        insumos[nombre.lower()] = {"insumo": nombre, "precio": precio, "unidad": unidad}
    if not insumos:
        raise ErrorPlanilla("La pestaña Insumos no tiene datos. No cambié nada.")

    recetas: dict[tuple, list[dict]] = {}
    for n, datos in _tabla(filas_recetas, _COLUMNAS_RECETA, "Ingredientes"):
        producto, variante = _limpiar(datos["producto"]), _limpiar(datos["variante"])
        insumo, unidad = _limpiar(datos["insumo"]), _limpiar(datos["unidad"])
        lote, rinde = _numero(datos["lote"]), _numero(datos["rinde"])
        if not producto:
            raise ErrorPlanilla(f"Ingredientes, fila {n}: falta el producto. No cambié nada.")
        if insumo.lower() not in insumos:
            raise ErrorPlanilla(f"Ingredientes, fila {n}: el insumo \"{insumo}\" no está en la pestaña Insumos. "
                                "No cambié nada.")
        if unidad not in tools._FACTOR_A_UNIDAD_INSUMO:
            raise ErrorPlanilla(f"Ingredientes, fila {n}: la unidad \"{unidad}\" no es válida (usa g, mL, kg, L, "
                                "unidad o porcion). No cambié nada.")
        if lote is None or lote < 0:
            raise ErrorPlanilla(f"Ingredientes, fila {n}: la cantidad de {insumo} no es válida. No cambié nada.")
        if rinde is None or rinde <= 0:
            raise ErrorPlanilla(f"Ingredientes, fila {n}: el rinde debe ser mayor que cero. No cambié nada.")
        recetas.setdefault(_clave(producto, variante), []).append(
            {"producto": producto, "variante": variante, "componente": _limpiar(datos["componente"]),
             "insumo": insumos[insumo.lower()]["insumo"], "lote": lote, "unidad": unidad, "rinde": rinde})
    if not recetas:
        raise ErrorPlanilla("La pestaña Ingredientes no tiene datos. No cambié nada.")
    return recetas, insumos


def _cargar_base() -> dict:
    return json.loads(BASE_PATH.read_text(encoding="utf-8")) if BASE_PATH.exists() else {"recetas": [], "insumos": []}


def registrar_base(c: Comparacion, pendientes: bool = False) -> None:
    """`pendientes` conserva lo que espera autorizacion para eliminarse: si saliera
    de la base, pasaria a parecer una receta importada y no se pediria mas."""
    recetas = set(c.recetas) | (set(c.eliminadas) if pendientes else set())
    insumos = set(c.insumos) | ({n.lower() for n in c.insumos_eliminados} if pendientes else set())
    BASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASE_PATH.write_text(json.dumps({"recetas": sorted(list(k) for k in recetas), "insumos": sorted(insumos)},
                                    ensure_ascii=False), encoding="utf-8")


def _recetas_bot() -> tuple[dict[tuple, list[dict]], int]:
    recetas: dict[tuple, list[dict]] = {}
    vacias = 0
    for f in tools._load_ingredientes().fillna("").to_dict("records"):
        if not _limpiar(f["insumo"]):
            vacias += 1
            continue
        rinde = float(f["rendimiento_lote"])
        recetas.setdefault(_clave(f["producto"], f["variante"]), []).append(
            {"producto": _limpiar(f["producto"]), "variante": _limpiar(f["variante"]),
             "componente": _limpiar(f["componente"]), "insumo": _limpiar(f["insumo"]),
             "lote": float(f["cantidad"]) * rinde, "unidad": _limpiar(f["unidad"]), "rinde": rinde})
    return recetas, vacias


def _misma_cantidad(a: float, b: float) -> bool:
    # el bot guarda por unidad y al multiplicar por el rinde quedan decimales de arrastre
    return math.isclose(a, b, rel_tol=1e-3, abs_tol=0.005)


def _orden(fila: dict) -> tuple:
    return tools._normalizar(fila["componente"]), tools._normalizar(fila["insumo"]), fila["unidad"], fila["lote"]


def _cant(fila: dict) -> str:
    return f"{fila['lote']:g} {fila['unidad']}"


def _diferencias(actual: list[dict], nueva: list[dict]) -> list[str]:
    """Lineas distintas de una receta. Vacio si son iguales."""
    def por_clave(filas):
        grupos: dict[tuple, list[dict]] = {}
        for f in sorted(filas, key=_orden):
            grupos.setdefault((tools._normalizar(f["componente"]), tools._normalizar(f["insumo"])), []).append(f)
        return grupos

    antes, despues = por_clave(actual), por_clave(nueva)
    lineas = []
    for clave in sorted(set(antes) | set(despues)):
        a, d = antes.get(clave, []), despues.get(clave, [])
        iguales = len(a) == len(d) and all(
            x["unidad"] == y["unidad"] and _misma_cantidad(x["lote"], y["lote"]) and _misma_cantidad(x["rinde"], y["rinde"])
            for x, y in zip(a, d))
        if iguales:
            continue
        muestra = (d or a)[0]
        lugar = f" ({muestra['componente']})" if muestra["componente"] else ""
        if not a:
            lineas.append(f"  agrega {muestra['insumo']}{lugar}: {', '.join(_cant(f) for f in d)}")
        elif not d:
            lineas.append(f"  quita {muestra['insumo']}{lugar}")
        else:
            rinde = f" (rinde {a[0]['rinde']:g} → {d[0]['rinde']:g})" if not _misma_cantidad(a[0]["rinde"], d[0]["rinde"]) else ""
            lineas.append(f"  {muestra['insumo']}{lugar}: {', '.join(_cant(f) for f in a)} → "
                          f"{', '.join(_cant(f) for f in d)}{rinde}")
    return lineas


def comparar(filas_recetas: list[list], filas_insumos: list[list]) -> Comparacion:
    recetas, insumos = interpretar(filas_recetas, filas_insumos)
    bot, vacias = _recetas_bot()
    base = _cargar_base()
    base_recetas = {tuple(k) for k in base["recetas"]}
    c = Comparacion(recetas=recetas, insumos=insumos, filas_vacias=vacias)
    for clave, filas in recetas.items():
        if clave not in bot:
            c.nuevas.append(clave)
        else:
            lineas = _diferencias(bot[clave], filas)
            if lineas:
                c.cambiadas[clave] = lineas
    fuera_de_planilla = []
    for clave in bot:
        if clave in recetas:
            continue
        if clave[0] in _PRODUCTOS_FUERA_DE_PLANILLA:
            fuera_de_planilla.append(clave)
        else:
            (c.eliminadas if clave in base_recetas else c.solo_bot).append(clave)

    precios = {str(f["insumo"]).lower(): f for f in tools._load_precios_insumos().fillna("").to_dict("records")}
    for clave, insumo in insumos.items():
        actual = precios.get(clave)
        if actual is None:
            c.insumos_nuevos.append(insumo["insumo"])
        elif not math.isclose(float(actual["precio"]), insumo["precio"], abs_tol=0.005) or actual["unidad"] != insumo["unidad"]:
            c.precios.append(f"  {insumo['insumo']}: ${float(actual['precio']):g}/{actual['unidad']} → "
                             f"${insumo['precio']:g}/{insumo['unidad']}")
    # un insumo que sigue en uso en una receta que se mantiene no se puede sacar
    en_uso = {f["insumo"].lower() for k in [*c.solo_bot, *fuera_de_planilla] for f in bot[k]}
    for clave, actual in precios.items():
        if clave not in insumos:
            eliminable = clave in base["insumos"] and clave not in en_uso
            (c.insumos_eliminados if eliminable else c.insumos_solo_bot).append(str(actual["insumo"]))
    c.sin_precio = sum(1 for i in insumos.values() if i["precio"] == 0)
    for filas in recetas.values():
        for f in filas:
            esperada = tools._FACTOR_A_UNIDAD_INSUMO[f["unidad"]][0]
            if esperada != insumos[f["insumo"].lower()]["unidad"]:
                c.avisos.append(f"  {_nombre(f['producto'], f['variante'])}: {f['insumo']} va en {f['unidad']}, "
                                f"pero su precio está por {insumos[f['insumo'].lower()]['unidad']}")
    return c


def descargar() -> tuple[list[list], list[list]]:
    return (planilla_clientes.leer_hoja(ID_PLANILLA, "Ingredientes!A:Z", numeros=True),
            planilla_clientes.leer_hoja(ID_PLANILLA, "Insumos!A:Z", numeros=True))


def comparacion_texto(c: Comparacion) -> str:
    def seccion(titulo, lineas):
        return ["", titulo] + lineas if lineas else []

    def nombres(claves, origen):
        return [f"- {_nombre(origen[k][0]['producto'], origen[k][0]['variante'])}" for k in claves]

    bot = _recetas_bot()[0]
    lineas = [f"Comparé la planilla con el bot:\n{len(c.nuevas)} recetas nuevas, {len(c.cambiadas)} con cambios y "
              f"{len(c.eliminadas)} para eliminar.\n{len(c.precios)} precios o unidades con cambios, "
              f"{len(c.insumos_nuevos)} insumos nuevos y {len(c.insumos_eliminados)} para eliminar."]
    lineas += seccion("Cambios de precio:", c.precios)
    lineas += seccion("Insumos nuevos:", [f"- {n}" for n in c.insumos_nuevos])
    lineas += seccion("Insumos que se eliminan:", [f"- {n}" for n in c.insumos_eliminados])
    lineas += seccion("Recetas nuevas:", nombres(c.nuevas, c.recetas))
    cambios = []
    for clave, detalle in c.cambiadas.items():
        cambios.append(f"- {_nombre(c.recetas[clave][0]['producto'], c.recetas[clave][0]['variante'])}")
        cambios += detalle
    lineas += seccion("Recetas con cambios:", cambios)
    lineas += seccion("Recetas que se eliminan:", nombres(c.eliminadas, bot))
    if c.filas_vacias:
        lineas += ["", f"Se eliminan {c.filas_vacias} filas vacías del bot."]
    lineas += seccion("Recetas que están solo en el bot (se mantienen; agrégalas a la planilla):", nombres(c.solo_bot, bot))
    lineas += seccion("Insumos que están solo en el bot (se mantienen):", [f"- {n}" for n in c.insumos_solo_bot])
    lineas += seccion("Revisa estas unidades:", c.avisos)
    if c.sin_precio:
        lineas += ["", f"Ojo: {c.sin_precio} insumos siguen con precio $0, y sus recetas salen con un costo más bajo que el real."]
    if not c.hay_cambios:
        lineas += ["", "No hay nada que reemplazar."]
        return "\n".join(lineas)[:MAX_TEXTO_TELEGRAM]
    pie = '\n\n¿Reemplazo los datos del bot? Responde "sí" o "cancelar".'
    texto = "\n".join(lineas)
    if len(texto) > MAX_TEXTO_TELEGRAM - len(pie):
        texto = texto[:MAX_TEXTO_TELEGRAM - len(pie) - 30] + "\n... (la lista sigue)"
    return texto + pie


def _escribir(df: pd.DataFrame, ruta) -> None:
    temporal = ruta.with_suffix(".tmp")
    df.to_csv(temporal, index=False)
    temporal.replace(ruta)


def _respaldar(marca: str) -> None:
    for ruta in (tools.INGREDIENTES_PATH, tools.PRECIOS_INSUMOS_PATH, tools.CATALOGO_PATH):
        if ruta.exists():
            shutil.copy2(ruta, ruta.with_name(f"{ruta.stem}.bak_{marca}{ruta.suffix}"))


def reemplazar(c: Comparacion, con_eliminaciones: bool = True) -> str:
    """Aplica solo lo mostrado, con respaldo previo. Una receta sin cambios no se
    reescribe, para no arrastrar decimales por convertir ida y vuelta."""
    _respaldar(f"{datetime.now():%Y%m%d_%H%M%S}")
    recetas_eliminadas = c.eliminadas if con_eliminaciones else []
    insumos_eliminados = c.insumos_eliminados if con_eliminaciones else []

    precios = tools._load_precios_insumos()
    eliminados = {n.lower() for n in insumos_eliminados}
    precios = precios[~precios["insumo"].astype(str).str.lower().isin(eliminados)]
    existentes = set(precios["insumo"].astype(str).str.lower())
    for clave, insumo in c.insumos.items():
        if clave in existentes:
            mascara = precios["insumo"].astype(str).str.lower() == clave
            if not math.isclose(float(precios.loc[mascara, "precio"].iloc[0]), insumo["precio"], abs_tol=0.005):
                precios.loc[mascara, "precio"] = insumo["precio"]
            precios.loc[mascara, "unidad"] = insumo["unidad"]
    agregar = [i for k, i in c.insumos.items() if k not in existentes]
    if agregar:
        precios = pd.concat([precios, pd.DataFrame(agregar)], ignore_index=True)
    _escribir(precios, tools.PRECIOS_INSUMOS_PATH)

    ingredientes = tools._load_ingredientes()
    claves = ingredientes.apply(lambda f: _clave(f["producto"], f["variante"]), axis=1)
    fuera = set(c.nuevas) | set(c.cambiadas) | set(recetas_eliminadas)
    conservar = ~claves.isin(fuera) & ingredientes["insumo"].fillna("").astype(str).str.strip().ne("")
    nuevas_filas = [{"producto": f["producto"], "variante": f["variante"], "componente": f["componente"],
                     "insumo": f["insumo"], "cantidad": f["lote"] / f["rinde"], "unidad": f["unidad"],
                     "rendimiento_lote": f["rinde"]}
                    for clave in [*c.nuevas, *c.cambiadas] for f in c.recetas[clave]]
    resultado = pd.concat([ingredientes[conservar], pd.DataFrame(nuevas_filas, columns=ingredientes.columns)],
                          ignore_index=True)
    _escribir(resultado, tools.INGREDIENTES_PATH)

    if recetas_eliminadas:
        catalogo = tools._load_catalogo()
        claves_catalogo = catalogo.apply(lambda f: _clave(f["producto"], f["variante"]), axis=1)
        _escribir(catalogo[~claves_catalogo.isin(set(recetas_eliminadas))], tools.CATALOGO_PATH)
    for clave in c.nuevas:
        fila = c.recetas[clave][0]
        tools.actualizar_info_producto(fila["producto"], fila["variante"])

    registrar_base(c, pendientes=not con_eliminaciones)
    return (f"Listo: {len(c.nuevas)} recetas nuevas, {len(c.cambiadas)} actualizadas y {len(recetas_eliminadas)} eliminadas; "
            f"{len(c.precios)} precios actualizados. Dejé un respaldo de los datos anteriores.")
