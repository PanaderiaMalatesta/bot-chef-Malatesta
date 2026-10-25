"""Controles de coherencia de una receta importada, antes de guardarla.

El esquema Pydantic de recipe_standardize ya asegura la FORMA de lo que
extrae el LLM (campos, tipos, None cuando falta un dato). Esto revisa si los
valores TIENEN SENTIDO: que el numero que dio el LLM este de verdad en el
texto fuente, que las proporciones sean de panaderia razonables, que no
haya cantidades absurdas, y que el costo por unidad no quede fuera de
escala respecto del resto del catalogo.

Nada de esto bloquea ni corrige nada: solo devuelve advertencias en texto
para mostrarlas en el resumen final, justo antes de que Raul confirme. Igual
que tools.py, es Python puro y determinista (sin LLM).
"""
from __future__ import annotations

import math
import re

from . import recipe_standardize as rs
from . import tools as t

# Rangos maximos razonables en % panadero (sobre el peso de la harina). Solo
# insumos donde un valor alto casi siempre es un error de lectura (ej. kg
# leido como g, o cucharada leida como taza) y no una receta "distinta".
_MAXIMO_PCT_PANADERO = {
    "sal": (4.0, "1,8–2,5%"),
    "flor_de_sal": (4.0, "1,8–2,5%"),
    "levadura_fresca": (8.0, "2–5%"),
    "polvos_hornear": (6.0, "1–5%"),
    "bicarbonato": (3.0, "0,5–2%"),
}

# Por encima de esto, un solo ingrediente de una receta importada (casera o
# de redes sociales) es casi seguro una unidad mal leida.
_MAXIMO_G_O_ML_POR_INGREDIENTE = 20000
_MAXIMO_UNIDADES_POR_INGREDIENTE = 500

# Insumos que valen $0 a proposito en precios_insumos.csv (no es un precio olvidado).
_GRATIS_A_PROPOSITO = {"agua"}

_FRACCIONES_UNICODE ={"½": 1 / 2, "¼": 1 / 4, "¾": 3 / 4, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 1 / 8}
_NUMEROS_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "media": 0.5, "medio": 0.5,
}


def revisar(estado: dict, costeo: dict) -> list[str]:
    """Devuelve la lista de advertencias para la receta en curso. `costeo` es
    el resultado de recipe_pipeline.costear (se pasa para no recalcularlo)."""
    receta = estado["receta"]
    advertencias: list[str] = []
    advertencias += _revisar_valores_absurdos(receta)
    advertencias += _revisar_cantidades_literales(receta)
    advertencias += _revisar_porcentajes_panaderos(receta)
    advertencias += _revisar_costos(receta, costeo)
    return advertencias


# --------------------------------------------------------------------------
# Valores absurdos
# --------------------------------------------------------------------------

def _revisar_valores_absurdos(receta: rs.RecetaEstandarizada) -> list[str]:
    advertencias = []
    if not receta.ingredientes:
        advertencias.append("La receta quedó sin ingredientes: probablemente la fuente no se leyó bien.")
    if receta.rendimiento is not None and receta.rendimiento <= 0:
        advertencias.append(f"El rendimiento es {receta.rendimiento:g}: tiene que ser mayor que cero.")

    vistos: dict[str, int] = {}
    for ing in receta.ingredientes:
        if ing.cantidad_lote is not None:
            if ing.cantidad_lote <= 0:
                advertencias.append(f"\"{ing.texto_original}\" quedó con cantidad {ing.cantidad_lote:g}.")
            elif ing.unidad_estandar in ("g", "mL") and ing.cantidad_lote > _MAXIMO_G_O_ML_POR_INGREDIENTE:
                advertencias.append(
                    f"\"{ing.texto_original}\" quedó en {ing.cantidad_lote / 1000:g} {'kg' if ing.unidad_estandar == 'g' else 'L'} "
                    "para un solo lote: ¿se leyó kg donde decía g?"
                )
            elif ing.unidad_estandar == "unidad" and ing.cantidad_lote > _MAXIMO_UNIDADES_POR_INGREDIENTE:
                advertencias.append(f"\"{ing.texto_original}\" quedó en {ing.cantidad_lote:g} unidades: parece demasiado.")
        if ing.insumo_resuelto:
            vistos[ing.insumo_resuelto] = vistos.get(ing.insumo_resuelto, 0) + 1

    for insumo, veces in vistos.items():
        if veces > 1:
            advertencias.append(
                f"{insumo} aparece {veces} veces: ¿se repitió por error o va en distintas partes de la receta? "
                "Si es repetido, la cantidad se sumaría de más."
            )
    return advertencias


# --------------------------------------------------------------------------
# Cantidad del LLM vs. texto fuente
# --------------------------------------------------------------------------

def _numeros_en_texto(texto: str) -> set[float]:
    """Todos los valores numericos que aparecen escritos en `texto`, en las
    formas en que se escriben en recetas: 175, 1,5, 1.000, 3/4, 1 1/2, ½,
    "dos", "una y media". Para separadores ambiguos ("1.000", "1,5") agrega
    las dos lecturas posibles -- aca interesa no dar falsos positivos."""
    texto = texto.lower()
    valores: set[float] = set()

    for m in re.finditer(r"(\d+)?\s*([½¼¾⅓⅔⅛])", texto):
        fraccion = _FRACCIONES_UNICODE[m.group(2)]
        valores.add(fraccion)
        if m.group(1):
            valores.add(int(m.group(1)) + fraccion)

    for m in re.finditer(r"(?:(\d+)\s+)?(\d+)\s*/\s*(\d+)", texto):
        if int(m.group(3)):
            fraccion = int(m.group(2)) / int(m.group(3))
            valores.add(fraccion)
            if m.group(1):
                valores.add(int(m.group(1)) + fraccion)

    for m in re.finditer(r"\d+(?:[.,]\d+)*", texto):
        s = m.group(0)
        for lectura in (s.replace(".", "").replace(",", "."), s.replace(",", "")):
            try:
                valores.add(float(lectura))
            except ValueError:
                pass

    for m in re.finditer(r"\b([a-z]+)(\s+y\s+medi[ao])?\b", texto):
        if m.group(1) in _NUMEROS_PALABRA:
            base = _NUMEROS_PALABRA[m.group(1)]
            valores.add(base + 0.5 if m.group(2) else base)
    return valores


def _revisar_cantidades_literales(receta: rs.RecetaEstandarizada) -> list[str]:
    advertencias = []
    for ing in receta.ingredientes:
        # Si Raul ya escribio la cantidad a mano, la del LLM ya no importa.
        if ing.cantidad_original is None or ing.confirmado_por_usuario:
            continue
        valores = _numeros_en_texto(ing.texto_original)
        if not any(math.isclose(ing.cantidad_original, v, rel_tol=0.02, abs_tol=0.01) for v in valores):
            advertencias.append(
                f"La cantidad {ing.cantidad_original:g} {ing.unidad_original or ''} de \"{ing.texto_original}\" "
                "no aparece así en el texto de la fuente: puede que la IA la haya inventado o calculado."
            )
    return advertencias


# --------------------------------------------------------------------------
# Proporciones de panaderia
# --------------------------------------------------------------------------

def _revisar_porcentajes_panaderos(receta: rs.RecetaEstandarizada) -> list[str]:
    porcentajes = rs.porcentajes_panaderos(receta)
    if not porcentajes:
        return []
    advertencias = []
    for insumo, pct in porcentajes.items():
        if insumo in _MAXIMO_PCT_PANADERO:
            maximo, normal = _MAXIMO_PCT_PANADERO[insumo]
            if pct > maximo:
                advertencias.append(
                    f"{insumo} es {_pct(pct)} de la harina (lo normal es {normal}): "
                    "revisa si la cantidad o la unidad se leyó bien."
                )
    return advertencias


def _pct(valor: float) -> str:
    return f"{valor:g}%".replace(".", ",")


# --------------------------------------------------------------------------
# Costos
# --------------------------------------------------------------------------

def _revisar_costos(receta: rs.RecetaEstandarizada, costeo: dict) -> list[str]:
    advertencias = []
    try:
        precios = t._load_precios_insumos()
        sin_precio = set(precios.loc[precios["precio"] <= 0, "insumo"].str.lower()) - _GRATIS_A_PROPOSITO
        en_cero = sorted({insumo for insumo, *_ in costeo["detalle"] if insumo.lower() in sin_precio})
        if en_cero:
            advertencias.append(
                f"{', '.join(en_cero)} {'tiene' if len(en_cero) == 1 else 'tienen'} precio $0 en el catálogo: "
                "el costo va a salir más bajo de lo real hasta que le pongas precio."
            )

        unitario = costeo.get("costo_unitario")
        rango = _rango_costos_catalogo()
        if unitario and rango:
            (minimo, nombre_min), (maximo, nombre_max) = rango
            if unitario > 2 * maximo:
                advertencias.append(
                    f"El costo por unidad (${_miles(unitario)}) es más del doble del producto más caro del catálogo "
                    f"(${_miles(maximo)}, {nombre_max}): revisa el rendimiento o alguna cantidad."
                )
            elif unitario < minimo / 2:
                advertencias.append(
                    f"El costo por unidad (${_miles(unitario)}) es menos de la mitad del producto más barato del catálogo "
                    f"(${_miles(minimo)}, {nombre_min}): revisa el rendimiento o alguna cantidad."
                )
    except Exception:  # noqa: BLE001
        # Un control es ayuda, no requisito: si falla (CSV raro, etc.) no
        # debe impedir mostrar el resumen ni guardar la receta.
        pass
    return advertencias


def _rango_costos_catalogo() -> tuple[tuple[float, str], tuple[float, str]] | None:
    """(minimo, nombre) y (maximo, nombre) del costo unitario de los productos
    del catalogo que tienen costo calculable. Lee cada CSV una sola vez en vez
    de llamar a t.costo_unitario_producto por producto."""
    catalogo = t._load_catalogo()
    ingredientes = t._load_ingredientes()
    precios = t._load_precios_insumos()

    costos: dict[tuple[str, str], float] = {}
    for fila in ingredientes.itertuples():
        try:
            costo = t._costo_ingrediente(fila, precios)
        except (ValueError, KeyError, AttributeError):
            # Filas incompletas del CSV (ej. insumo vacio): no cuentan para el rango.
            continue
        clave = (fila.producto, fila.variante)
        costos[clave] = costos.get(clave, 0.0) + costo
    if "costo_fijo" in catalogo.columns:
        for fila in catalogo.itertuples():
            if isinstance(fila.costo_fijo, (int, float)) and not math.isnan(fila.costo_fijo):
                costos[(fila.producto, fila.variante)] = float(fila.costo_fijo)

    validos = [(costo, f"{t._legible(p)} {t._legible(v)}".strip()) for (p, v), costo in costos.items() if costo > 0]
    if not validos:
        return None
    return min(validos), max(validos)


def _miles(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")
