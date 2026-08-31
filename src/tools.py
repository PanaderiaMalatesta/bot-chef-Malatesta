"""Herramientas deterministicas de costeo e inventario para el agente Malatesta.

Toda la matematica (escalado, sumas, food cost) se hace en Python con los CSV
de datos -- el LLM nunca calcula numeros, solo interpreta la pregunta y llama
a estas funciones. Esto evita que el agente "invente" cifras.

El costo de cada producto se calcula EN VIVO a partir de sus insumos
(recetas_ingredientes.csv x precios_insumos.csv), asi que si se actualiza el
precio de un insumo, todos los productos que lo usan quedan recosteados
automaticamente sin tocar ningun otro archivo.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import re
import unicodedata
from pathlib import Path

import pandas as pd

from .paths import DATA_DIR

INGREDIENTES_PATH = DATA_DIR / "recetas_ingredientes.csv"
PRECIOS_INSUMOS_PATH = DATA_DIR / "precios_insumos.csv"
CATALOGO_PATH = DATA_DIR / "catalogo_precios.csv"
PRODUCCION_PATH = DATA_DIR / "produccion_diaria.csv"

# Factor para convertir la unidad de la receta a la unidad en que esta
# cotizado el insumo (que siempre es kg, L, unidad o porcion).
_FACTOR_A_UNIDAD_INSUMO = {
    "g": ("kg", 0.001),
    "mL": ("L", 0.001),
    "kg": ("kg", 1),
    "L": ("L", 1),
    "unidad": ("unidad", 1),
    "porcion": ("porcion", 1),
}

BENCHMARK_FOOD_COST = {
    "Facturas": (0, 20),
    "Medialuna_Tradicional": (20, 28),
    "Medialuna_Clasica": (24, 30),
    "Medialuna_Especial": (30, 42),
    "Medialuna_Premium": (30, 42),
    "Sandwich": (35, 40),
    "Muffin": (25, 30),
    "Cafe": (25, 35),
}


_STOPWORDS = {"de", "la", "el", "los", "las", "del", "y", "a", "en", "una", "un", "con", "sin"}


def _normalizar(texto: str) -> str:
    """Minusculas, sin tildes y sin espacios/guiones bajos, para poder comparar
    'vainilla de Tahití' contra 'vainilla_tahiti' sin que importen mayusculas,
    acentos o espaciado."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().replace(" ", "").replace("_", "")


def _legible(texto: str) -> str:
    """Convierte identificadores en CamelCase o con guion bajo (ej. 'MurbeNuez',
    'MasaQuebrada_Base') a texto separado por espacios, solo para mostrarlo al
    usuario."""
    texto = texto.replace("_", " ")
    texto = re.sub(r"(?<!^)(?=[A-Z])", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _buscar_filas(catalogo: pd.DataFrame, texto: str) -> pd.DataFrame:
    """Filas cuyo producto+variante+categoria contienen TODAS las palabras de
    `texto` (sin importar mayusculas/espaciado/orden). Tolera que el llamador no
    separe bien producto y variante (ej. pasar "Masa Quebrada Sablee" entero)."""
    palabras = [p for p in re.split(r"\s+", texto.strip().lower()) if p]

    def _coincide(fila) -> bool:
        campo = _normalizar(f"{fila.producto} {fila.variante} {fila.categoria}")
        return all(_normalizar(palabra) in campo for palabra in palabras)

    return catalogo[catalogo.apply(_coincide, axis=1)]


def _alternativas_fuzzy(catalogo: pd.DataFrame, texto: str, minimo: float = 0.35, tope: int = 5) -> list:
    """Filas mas parecidas a `texto` por similitud de texto, para cuando la
    busqueda por palabras no encuentra nada (ej. errores de tipeo)."""
    texto_norm = _normalizar(texto)
    puntajes = [
        (
            difflib.SequenceMatcher(None, texto_norm, _normalizar(f"{fila.producto} {fila.variante}")).ratio(),
            fila,
        )
        for fila in catalogo.itertuples()
    ]
    puntajes.sort(key=lambda par: par[0], reverse=True)
    return [fila for puntaje, fila in puntajes[:tope] if puntaje > minimo]


def _read_csv_flexible(path: Path) -> pd.DataFrame:
    """Lee un CSV detectando automaticamente si el delimitador es ',' o ';'.

    Excel en configuracion regional de Chile guarda "CSV separado por comas"
    usando ';' como delimitador real, asi que hay que tolerar ambos casos
    para que editar los datos en Excel no rompa la lectura.
    """
    return pd.read_csv(path, sep=None, engine="python")


def _load_precios_insumos() -> pd.DataFrame:
    return _read_csv_flexible(PRECIOS_INSUMOS_PATH)


def _load_ingredientes() -> pd.DataFrame:
    df = _read_csv_flexible(INGREDIENTES_PATH)
    df["variante"] = df["variante"].fillna("")
    return df


def _load_catalogo() -> pd.DataFrame:
    df = _read_csv_flexible(CATALOGO_PATH)
    df["variante"] = df["variante"].fillna("")
    return df


def _load_produccion() -> pd.DataFrame:
    return _read_csv_flexible(PRODUCCION_PATH)


def _costo_ingrediente(fila, precios: pd.DataFrame) -> float:
    match = precios[precios["insumo"].str.lower() == fila.insumo.lower()]
    if match.empty:
        raise ValueError(f"Insumo '{fila.insumo}' no tiene precio registrado en precios_insumos.csv")
    unidad_insumo_esperada, factor = _FACTOR_A_UNIDAD_INSUMO[fila.unidad]
    precio_por_unidad = match.iloc[0]["precio"]
    return fila.cantidad * factor * precio_por_unidad


def _costeo_por_componente(producto: str, variante: str) -> dict[str, float]:
    """Devuelve el costo de cada componente (Masa, Relleno, ...) para una variante, calculado en vivo."""
    ingredientes = _load_ingredientes()
    precios = _load_precios_insumos()
    filas = ingredientes[
        (ingredientes["producto"].apply(_normalizar) == _normalizar(producto))
        & (ingredientes["variante"].apply(_normalizar) == _normalizar(variante))
    ]
    costos: dict[str, float] = {}
    for fila in filas.itertuples():
        costo = _costo_ingrediente(fila, precios)
        costos[fila.componente] = costos.get(fila.componente, 0.0) + costo
    return costos


def _info_catalogo(producto: str, variante: str) -> pd.Series | None:
    catalogo = _load_catalogo()
    fila = catalogo[
        (catalogo["producto"].apply(_normalizar) == _normalizar(producto))
        & (catalogo["variante"].apply(_normalizar) == _normalizar(variante))
    ]
    if not fila.empty:
        return fila.iloc[0]

    # Coincidencia exacta por clave fallo (ej. el LLM no separo bien
    # producto/variante, como pasar "Masa Quebrada Sablee" completo en el
    # campo producto). Antes de caer a la busqueda por palabras (que es
    # ambigua cuando una variante es substring de otra, ej. "Sablee" vs
    # "SableeCacao" -- "sablee" normalizado es substring literal de
    # "sableecacao"), probar una coincidencia EXACTA contra el nombre
    # completo legible reconstruido (producto+variante), que no sufre ese
    # falso positivo porque compara el string completo, no palabra por
    # palabra.
    texto_combinado = _normalizar(f"{producto} {variante}")
    for fila_c in catalogo.itertuples():
        nombre_completo = _normalizar(f"{_legible(fila_c.producto)} {_legible(fila_c.variante)}")
        if nombre_completo == texto_combinado:
            return catalogo.loc[fila_c.Index]

    # Tampoco hubo match exacto por nombre completo. Probar de nuevo
    # buscando todas las palabras de ambos campos en conjunto.
    filas = _buscar_filas(catalogo, f"{producto} {variante}")
    return filas.iloc[0] if len(filas) == 1 else None


def _resolver_producto_variante(producto: str, variante: str) -> tuple[str, str]:
    """Devuelve el (producto, variante) CANONICOS del catalogo si logra
    resolverlos (via _info_catalogo, que tolera texto mal separado como
    "Masa Quebrada Sablee" completo en `producto`), o los valores originales
    sin tocar si no existe todavia (ej. al crear un producto nuevo con
    agregar_ingrediente_receta). Usar esto ANTES de tocar
    recetas_ingredientes.csv directamente en las funciones de editar receta,
    para no operar sobre un producto/variante mal separado por el LLM."""
    info = _info_catalogo(producto, variante)
    if info is None:
        return producto, variante
    return info["producto"], info["variante"]


def costo_unitario_producto(producto: str, variante: str) -> float:
    """Costo unitario total de un producto/variante, calculado en vivo desde insumos.

    Si el producto tiene `costo_fijo` en el catalogo (ej. recetas sin desglose de
    insumos, como el Muffin), se usa ese valor en vez de calcular desde ingredientes.
    """
    info = _info_catalogo(producto, variante)
    if info is not None and pd.notna(info.get("costo_fijo")):
        return float(info["costo_fijo"])
    return sum(_costeo_por_componente(producto, variante).values())


def listar_precios_insumos(filtro: str | None = None) -> str:
    """Lista el precio vigente de las materias primas. Si se da `filtro`, solo
    muestra los insumos cuyo nombre lo contenga (busqueda parcial, sin distinguir mayusculas)."""
    precios = _load_precios_insumos()
    if filtro:
        precios = precios[precios["insumo"].str.contains(filtro, case=False)]
    if precios.empty:
        return f"No encontré insumos que coincidan con '{filtro}'."
    lineas = [f"- {fila.insumo}: ${fila.precio:.0f}/{fila.unidad}" for fila in precios.itertuples()]
    return "\n".join(lineas)


def actualizar_precio_insumo(insumo: str, nuevo_precio: float) -> str:
    """Actualiza el precio de un insumo (materia prima). Todos los productos que lo usan
    quedan recosteados automaticamente la próxima vez que se consulten."""
    precios = _load_precios_insumos()
    mask = precios["insumo"].str.lower() == insumo.lower()
    if not mask.any():
        disponibles = sorted(precios["insumo"].unique())
        return f"No encontré el insumo '{insumo}'. Insumos disponibles: {', '.join(disponibles)}."

    precio_anterior = precios.loc[mask, "precio"].iloc[0]
    precios.loc[mask, "precio"] = nuevo_precio
    precios.to_csv(PRECIOS_INSUMOS_PATH, index=False)

    nombre_real = precios.loc[mask, "insumo"].iloc[0]
    return f"Precio de {nombre_real} actualizado: ${precio_anterior:.0f} -> ${nuevo_precio:.0f}."


def _filas_receta(ingredientes: pd.DataFrame, producto: str, variante: str, componente: str | None = None) -> pd.DataFrame:
    """Filas de recetas_ingredientes.csv para un producto/variante (y opcionalmente
    componente), por igualdad normalizada exacta."""
    mask = (
        (ingredientes["producto"].apply(_normalizar) == _normalizar(producto))
        & (ingredientes["variante"].apply(_normalizar) == _normalizar(variante))
    )
    if componente:
        mask &= ingredientes["componente"].apply(_normalizar) == _normalizar(componente)
    return ingredientes[mask]


def _resolver_insumo_en_filas(filas: pd.DataFrame, texto_insumo: str) -> pd.DataFrame:
    """Encuentra, dentro de `filas` (ya acotadas a una receta), cuales coinciden
    con `texto_insumo`. Tolera texto libre (ej. 'vainilla de Tahiti' encuentra
    'vainilla_tahiti', ignorando la palabra de relleno 'de') y errores de tipeo
    via similitud, para no exigir el nombre exacto del insumo."""
    palabras = [p for p in re.split(r"\s+", texto_insumo.strip().lower()) if p and _normalizar(p) not in _STOPWORDS]
    if palabras:

        def _coincide(fila) -> bool:
            campo = _normalizar(fila.insumo)
            return all(_normalizar(palabra) in campo for palabra in palabras)

        candidatas = filas[filas.apply(_coincide, axis=1)]
        if not candidatas.empty:
            return candidatas

    if filas.empty:
        return filas
    texto_norm = _normalizar(texto_insumo)
    puntajes = [
        (difflib.SequenceMatcher(None, texto_norm, _normalizar(fila.insumo)).ratio(), idx)
        for idx, fila in filas.iterrows()
    ]
    puntajes.sort(key=lambda par: par[0], reverse=True)
    mejor = puntajes[0][0]
    if mejor < 0.4:
        return filas.iloc[0:0]
    mejores_idx = [idx for puntaje, idx in puntajes if puntaje >= mejor - 0.05]
    return filas.loc[mejores_idx]


def _convertir_unidad(cantidad: float, unidad_origen: str, unidad_destino: str) -> float:
    """Convierte una cantidad entre unidades compatibles (g<->kg, mL<->L, o la
    misma unidad exacta para unidad/porcion)."""
    if unidad_origen not in _FACTOR_A_UNIDAD_INSUMO:
        raise ValueError(f"Unidad '{unidad_origen}' no valida.")
    if unidad_destino not in _FACTOR_A_UNIDAD_INSUMO:
        raise ValueError(f"Unidad '{unidad_destino}' no valida.")
    base_origen, factor_origen = _FACTOR_A_UNIDAD_INSUMO[unidad_origen]
    base_destino, factor_destino = _FACTOR_A_UNIDAD_INSUMO[unidad_destino]
    if base_origen != base_destino:
        raise ValueError(f"'{unidad_origen}' y '{unidad_destino}' no son unidades compatibles.")
    return cantidad * factor_origen / factor_destino


def estandarizar_receta_por_ingrediente(
    producto: str, variante: str, componente: str, insumo_ancla: str, cantidad_lote: float, unidad_lote: str,
) -> str:
    """Redefine la receta ESTANDAR de un componente (ej. la Masa de la Medialuna
    Tradicional) a partir de la cantidad real que se usa de UN insumo ancla en
    el lote completo que se mezcla en cocina (ej. "el pastón usa 4,8 kg de
    harina"). El sistema ya sabe cuantas unidades rinde ese lote (quedo
    guardado la primera vez que se costeo la receta), calcula el factor de
    cambio respecto a lo que hay guardado, y reescala PROPORCIONALMENTE todos
    los demas insumos de ese mismo componente -- no hace falta tocarlos uno
    por uno."""
    if unidad_lote not in _FACTOR_A_UNIDAD_INSUMO:
        return f"Unidad '{unidad_lote}' no valida. Usa una de: {', '.join(_FACTOR_A_UNIDAD_INSUMO)}."

    producto, variante = _resolver_producto_variante(producto, variante)
    ingredientes = _load_ingredientes()
    filas_componente = _filas_receta(ingredientes, producto, variante, componente)
    if filas_componente.empty:
        return f"No encontré el componente '{componente}' de {_legible(producto)} {_legible(variante)}."

    candidatas = _resolver_insumo_en_filas(filas_componente, insumo_ancla)
    if candidatas.empty:
        disponibles = ", ".join(filas_componente["insumo"].unique())
        return f"No encontré nada parecido a '{insumo_ancla}' en {_legible(producto)} {_legible(variante)} ({componente}). Insumos ahí: {disponibles}."
    if len(candidatas) > 1:
        opciones = ", ".join(candidatas["insumo"].unique())
        return f"Hay varias coincidencias para '{insumo_ancla}': {opciones}. Especifica cual."

    fila_ancla = candidatas.iloc[0]
    rendimiento_lote = filas_componente["rendimiento_lote"].iloc[0] if "rendimiento_lote" in filas_componente.columns else 1

    try:
        cantidad_lote_en_unidad_ancla = _convertir_unidad(cantidad_lote, unidad_lote, fila_ancla.unidad)
    except ValueError as e:
        return str(e)

    nueva_cantidad_por_unidad = cantidad_lote_en_unidad_ancla / rendimiento_lote
    if fila_ancla.cantidad == 0:
        return f"No puedo calcular el factor de cambio: {fila_ancla.insumo} está guardado en 0 actualmente."
    factor = nueva_cantidad_por_unidad / fila_ancla.cantidad

    lineas = [
        f"Estandarizando {_legible(producto)} {_legible(variante)} ({componente}) "
        f"con {fila_ancla.insumo} = {cantidad_lote:g}{unidad_lote} para un lote que rinde {rendimiento_lote:g}:"
    ]
    for fila in filas_componente.itertuples():
        nueva_cantidad = fila.cantidad * factor
        ingredientes.loc[fila.Index, "cantidad"] = nueva_cantidad
        lineas.append(f"  - {fila.insumo}: {fila.cantidad:g}{fila.unidad} -> {nueva_cantidad:g}{fila.unidad}")

    ingredientes.to_csv(INGREDIENTES_PATH, index=False)
    lineas.append(f"Factor aplicado: {factor:.4f}")
    return "\n".join(lineas)


def _asegurar_en_catalogo(producto: str, variante: str) -> None:
    """Si el producto/variante no existe en catalogo_precios.csv, lo agrega sin
    precio de venta (queda como receta sin clasificar hasta que se le asigne
    categoria/precio), para que quede visible en buscar_receta/listar_variantes."""
    catalogo = _load_catalogo()
    if _info_catalogo(producto, variante) is not None:
        return
    nueva_fila = pd.DataFrame([{
        "producto": producto, "variante": variante, "categoria": "SinClasificar",
        "precio_venta": None, "costo_fijo": None, "tiempo_fabricacion_min": None,
    }])
    catalogo = pd.concat([catalogo, nueva_fila], ignore_index=True)
    catalogo.to_csv(CATALOGO_PATH, index=False)


def actualizar_info_producto(
    producto: str, variante: str, categoria: str | None = None,
    precio_venta: float | None = None, tiempo_fabricacion_min: float | None = None,
) -> str:
    """Actualiza (o crea si no existe) la categoria, precio de venta y/o tiempo
    de fabricacion de un producto/variante en catalogo_precios.csv. Los
    argumentos en None no se tocan."""
    _asegurar_en_catalogo(producto, variante)
    producto, variante = _resolver_producto_variante(producto, variante)
    catalogo = _load_catalogo()
    mask = (
        (catalogo["producto"].apply(_normalizar) == _normalizar(producto))
        & (catalogo["variante"].apply(_normalizar) == _normalizar(variante))
    )
    if categoria is not None:
        catalogo.loc[mask, "categoria"] = categoria
    if precio_venta is not None:
        catalogo.loc[mask, "precio_venta"] = precio_venta
    if "tiempo_fabricacion_min" not in catalogo.columns:
        catalogo["tiempo_fabricacion_min"] = None
    if tiempo_fabricacion_min is not None:
        catalogo.loc[mask, "tiempo_fabricacion_min"] = tiempo_fabricacion_min
    catalogo.to_csv(CATALOGO_PATH, index=False)
    return f"{_legible(producto)} {_legible(variante)} actualizado en el catálogo."


def reemplazar_receta_completa(
    producto: str, variante: str, lineas: list[dict],
    categoria: str | None = None, precio_venta: float | None = None,
    tiempo_fabricacion_min: float | None = None,
) -> str:
    """Reemplaza TODA la receta de un producto/variante de una sola vez: borra
    los insumos que tuviera antes y carga `lineas` (cada una con componente,
    insumo, cantidad -- ya en cantidad POR UNIDAD, no por lote -- y unidad).
    Pensado para sincronizacion automatizada (ej. desde el planificador web),
    no para el chat -- no pide confirmacion porque no hay un humano
    respondiendo en el momento."""
    ingredientes = _load_ingredientes()
    filas_previas = _filas_receta(ingredientes, producto, variante)
    if not filas_previas.empty:
        ingredientes = ingredientes.drop(filas_previas.index)

    nuevas = pd.DataFrame([{
        "producto": producto, "variante": variante,
        "componente": linea.get("componente", "Receta"),
        "insumo": linea["insumo"], "cantidad": linea["cantidad"],
        "unidad": linea["unidad"], "rendimiento_lote": 1,
    } for linea in lineas])
    ingredientes = pd.concat([ingredientes, nuevas], ignore_index=True)
    ingredientes.to_csv(INGREDIENTES_PATH, index=False)

    actualizar_info_producto(producto, variante, categoria, precio_venta, tiempo_fabricacion_min)
    return f"Receta de {_legible(producto)} {_legible(variante)} reemplazada con {len(lineas)} insumos."


def agregar_ingrediente_receta(producto: str, variante: str, componente: str, insumo: str, cantidad_lote: float, unidad: str) -> str:
    """Agrega un insumo nuevo a una receta (producto/variante/componente, ej. 'Masa',
    'Relleno'). `cantidad_lote` es la cantidad para el LOTE ESTANDAR completo que
    se mezcla en cocina (ej. "0,1 L de esencia de vainilla" para todo el pastón),
    NO por unidad individual -- si el componente ya existe, se usa su
    rendimiento_lote ya conocido para convertir y guardarlo correctamente por
    unidad. Si el producto/variante/componente no existía, se crea con
    rendimiento_lote=1 (cantidad_lote = por unidad, sin lote definido todavía).
    `unidad` debe ser g, mL, kg, L, unidad o porcion."""
    if unidad not in _FACTOR_A_UNIDAD_INSUMO:
        return f"Unidad '{unidad}' no valida. Usa una de: {', '.join(_FACTOR_A_UNIDAD_INSUMO)}."

    producto, variante = _resolver_producto_variante(producto, variante)
    ingredientes = _load_ingredientes()
    filas_receta = _filas_receta(ingredientes, producto, variante, componente)
    # Solo bloquear duplicados EXACTOS (sin el fallback difuso) -- lo difuso es
    # correcto para encontrar algo que ya existe al editar/eliminar, pero aca
    # produciria falsos positivos y bloquearia insumos nuevos legitimos.
    ya_existe = filas_receta["insumo"].apply(_normalizar).eq(_normalizar(insumo)).any()
    if ya_existe:
        return (
            f"{insumo} ya existe en {_legible(producto)} {_legible(variante)} ({componente}). "
            "Usa editar_ingrediente_receta si quieres cambiar la cantidad."
        )

    # Si el componente ya existe, heredar su rendimiento_lote para que quede
    # consistente con el resto de los insumos de esa misma masa/relleno/etc.
    rendimiento_lote = 1
    if not filas_receta.empty and "rendimiento_lote" in filas_receta.columns:
        rendimiento_lote = filas_receta["rendimiento_lote"].iloc[0]

    cantidad_por_unidad = cantidad_lote / rendimiento_lote

    nueva_fila = pd.DataFrame([{
        "producto": producto, "variante": variante, "componente": componente,
        "insumo": insumo, "cantidad": cantidad_por_unidad, "unidad": unidad,
        "rendimiento_lote": rendimiento_lote,
    }])
    ingredientes = pd.concat([ingredientes, nueva_fila], ignore_index=True)
    ingredientes.to_csv(INGREDIENTES_PATH, index=False)
    _asegurar_en_catalogo(producto, variante)

    return (
        f"Agregado: {_legible(producto)} {_legible(variante)} ahora incluye {insumo} "
        f"{cantidad_lote:g}{unidad} en el lote de {componente} (rinde {rendimiento_lote:g})."
    )


def eliminar_ingrediente_receta(
    producto: str, variante: str, insumo: str, componente: str | None = None, confirmado: bool = False,
) -> str:
    """Elimina un insumo de una receta. Tolera texto libre y errores de tipeo en
    `insumo` (busca la coincidencia mas parecida dentro de esa receta). Si el
    insumo aparece en mas de un componente, hay que especificar `componente`.

    SIEMPRE requiere confirmacion: la primera llamada (confirmado=False, el
    default) NO elimina nada, solo devuelve una pregunta de confirmacion con el
    insumo exacto que se borraria. Solo se elimina de verdad cuando se vuelve a
    llamar con confirmado=True (despues de que el usuario diga que si)."""
    producto, variante = _resolver_producto_variante(producto, variante)
    ingredientes = _load_ingredientes()
    filas_receta = _filas_receta(ingredientes, producto, variante, componente)
    if filas_receta.empty:
        return f"No encontré la receta {_legible(producto)} {_legible(variante)}."

    candidatas = _resolver_insumo_en_filas(filas_receta, insumo)
    if candidatas.empty:
        disponibles = ", ".join(filas_receta["insumo"].unique())
        return f"No encontré nada parecido a '{insumo}' en {_legible(producto)} {_legible(variante)}. Insumos en esa receta: {disponibles}."
    if len(candidatas) > 1:
        opciones = ", ".join(f"{f.insumo} ({f.componente})" for f in candidatas.itertuples())
        return f"Hay varias coincidencias para '{insumo}': {opciones}. Especifica cual (y el componente si hace falta)."

    fila = candidatas.iloc[0]
    rendimiento_lote = getattr(fila, "rendimiento_lote", 1)
    cantidad_lote = fila.cantidad * rendimiento_lote
    if not confirmado:
        return (
            f"¿Confirmas eliminar {fila.insumo} ({cantidad_lote:g}{fila.unidad} en el lote) de "
            f"{_legible(producto)} {_legible(variante)} ({fila.componente})? Responde que sí para confirmar."
        )

    ingredientes = ingredientes.drop(candidatas.index)
    ingredientes.to_csv(INGREDIENTES_PATH, index=False)
    return f"Eliminado: {fila.insumo} de {_legible(producto)} {_legible(variante)} ({fila.componente})."


def eliminar_producto(producto: str, variante: str, confirmado: bool = False) -> str:
    """Elimina un producto/variante COMPLETO del catálogo (y todos los insumos
    asociados en recetas_ingredientes.csv). Distinto de
    eliminar_ingrediente_receta, que solo borra un insumo dentro de una
    receta -- esta función borra la receta entera.

    SIEMPRE requiere confirmación: la primera llamada (confirmado=False, el
    default) NO elimina nada, solo devuelve una pregunta de confirmación.
    Solo se elimina de verdad cuando se vuelve a llamar con confirmado=True
    (después de que el usuario diga que sí)."""
    catalogo = _load_catalogo()
    info = _info_catalogo(producto, variante)
    if info is None:
        return _mensaje_no_encontrado(catalogo, producto, variante)
    producto, variante = info["producto"], info["variante"]

    ingredientes = _load_ingredientes()
    filas_ingredientes = _filas_receta(ingredientes, producto, variante)

    if not confirmado:
        detalle = f" (incluye {len(filas_ingredientes)} insumos registrados)" if not filas_ingredientes.empty else ""
        return (
            f"¿Confirmas eliminar POR COMPLETO {_legible(producto)} {_legible(variante)} del catálogo{detalle}? "
            "Esto no se puede deshacer. Responde que sí para confirmar."
        )

    mask_catalogo = (
        (catalogo["producto"].apply(_normalizar) == _normalizar(producto))
        & (catalogo["variante"].apply(_normalizar) == _normalizar(variante))
    )
    catalogo = catalogo[~mask_catalogo]
    catalogo.to_csv(CATALOGO_PATH, index=False)

    if not filas_ingredientes.empty:
        ingredientes = ingredientes.drop(filas_ingredientes.index)
        ingredientes.to_csv(INGREDIENTES_PATH, index=False)

    return f"Eliminado: {_legible(producto)} {_legible(variante)} y sus {len(filas_ingredientes)} insumos asociados."


def editar_ingrediente_receta(
    producto: str, variante: str, insumo: str, nueva_cantidad_lote: float,
    componente: str | None = None, nueva_unidad: str | None = None,
) -> str:
    """Cambia la cantidad (y opcionalmente la unidad) de un insumo ya presente en
    una receta. `nueva_cantidad_lote` es la cantidad para el LOTE ESTANDAR
    completo (ej. "0,1 L" para todo el pastón), NO por unidad individual -- se
    convierte automáticamente usando el rendimiento_lote ya conocido de esa
    receta. Si el insumo aparece en mas de un componente, especifica cual."""
    if nueva_unidad is not None and nueva_unidad not in _FACTOR_A_UNIDAD_INSUMO:
        return f"Unidad '{nueva_unidad}' no valida. Usa una de: {', '.join(_FACTOR_A_UNIDAD_INSUMO)}."

    producto, variante = _resolver_producto_variante(producto, variante)
    ingredientes = _load_ingredientes()
    filas_receta = _filas_receta(ingredientes, producto, variante, componente)
    if filas_receta.empty:
        return f"No encontré la receta {_legible(producto)} {_legible(variante)}."

    candidatas = _resolver_insumo_en_filas(filas_receta, insumo)
    if candidatas.empty:
        disponibles = ", ".join(filas_receta["insumo"].unique())
        return f"No encontré nada parecido a '{insumo}' en {_legible(producto)} {_legible(variante)}. Insumos en esa receta: {disponibles}."
    if len(candidatas) > 1:
        opciones = ", ".join(f"{f.insumo} ({f.componente})" for f in candidatas.itertuples())
        return f"Hay varias coincidencias para '{insumo}': {opciones}. Especifica cual (y el componente si hace falta)."

    fila = candidatas.iloc[0]
    rendimiento_lote = getattr(fila, "rendimiento_lote", 1)
    cantidad_lote_anterior = fila.cantidad * rendimiento_lote
    unidad_anterior = fila.unidad
    nueva_cantidad_por_unidad = nueva_cantidad_lote / rendimiento_lote

    ingredientes.loc[candidatas.index, "cantidad"] = nueva_cantidad_por_unidad
    if nueva_unidad is not None:
        ingredientes.loc[candidatas.index, "unidad"] = nueva_unidad
    ingredientes.to_csv(INGREDIENTES_PATH, index=False)

    unidad_final = nueva_unidad or unidad_anterior
    return (
        f"{fila.insumo} en {_legible(producto)} {_legible(variante)} (lote) actualizado: "
        f"{cantidad_lote_anterior:g}{unidad_anterior} -> {nueva_cantidad_lote:g}{unidad_final}."
    )


def reemplazar_ingrediente_receta(
    producto: str, variante: str, insumo_actual: str, insumo_nuevo: str,
    cantidad_lote: float, unidad: str, componente: str | None = None,
) -> str:
    """Reemplaza un insumo de una receta por otro distinto (ej. cambiar margarina
    por mantequilla), en el mismo componente. `cantidad_lote` es la cantidad
    para el LOTE ESTANDAR completo (no por unidad individual) -- se convierte
    con el rendimiento_lote ya conocido de esa receta."""
    if unidad not in _FACTOR_A_UNIDAD_INSUMO:
        return f"Unidad '{unidad}' no valida. Usa una de: {', '.join(_FACTOR_A_UNIDAD_INSUMO)}."

    producto, variante = _resolver_producto_variante(producto, variante)
    ingredientes = _load_ingredientes()
    filas_receta = _filas_receta(ingredientes, producto, variante, componente)
    if filas_receta.empty:
        return f"No encontré la receta {_legible(producto)} {_legible(variante)}."

    candidatas = _resolver_insumo_en_filas(filas_receta, insumo_actual)
    if candidatas.empty:
        disponibles = ", ".join(filas_receta["insumo"].unique())
        return f"No encontré nada parecido a '{insumo_actual}' en {_legible(producto)} {_legible(variante)}. Insumos en esa receta: {disponibles}."
    if len(candidatas) > 1:
        opciones = ", ".join(f"{f.insumo} ({f.componente})" for f in candidatas.itertuples())
        return f"Hay varias coincidencias para '{insumo_actual}': {opciones}. Especifica cual (y el componente si hace falta)."

    fila = candidatas.iloc[0]
    rendimiento_lote = getattr(fila, "rendimiento_lote", 1)
    insumo_real = fila.insumo
    cantidad_por_unidad = cantidad_lote / rendimiento_lote

    ingredientes.loc[candidatas.index, "insumo"] = insumo_nuevo
    ingredientes.loc[candidatas.index, "cantidad"] = cantidad_por_unidad
    ingredientes.loc[candidatas.index, "unidad"] = unidad
    ingredientes.to_csv(INGREDIENTES_PATH, index=False)

    return (
        f"Reemplazado en {_legible(producto)} {_legible(variante)}: "
        f"{insumo_real} -> {insumo_nuevo} ({cantidad_lote:g}{unidad} en el lote)."
    )


_TERMINOS_SIN_FILTRO = {"todo", "todos", "toda", "todas", ""}


def listar_variantes(termino: str) -> str:
    """Lista los nombres de producto/variante que coincidan con `termino` (busca en
    producto, variante y categoria, sin distinguir mayusculas ni espaciado, palabra
    por palabra). Uso pensado para cuando el usuario pide algo de forma generica
    (ej. "una receta de masa quebrada" o "masa sablee") y hay que preguntarle cual
    variante especifica quiere, en vez de mostrar todo el detalle de costeo de
    una vez. Si `termino` es "todo"/"todos"/vacio (el usuario pidio TODAS las
    recetas sin filtrar por categoria), devuelve el catalogo completo sin filtrar."""
    catalogo = _load_catalogo()
    if _normalizar(termino) in _TERMINOS_SIN_FILTRO:
        return "\n".join(
            f"{i}. {_legible(fila.producto)} {_legible(fila.variante)}"
            for i, fila in enumerate(catalogo.itertuples(), start=1)
        )
    filas = _buscar_filas(catalogo, termino)
    if not filas.empty:
        return "\n".join(
            f"{i}. {_legible(fila.producto)} {_legible(fila.variante)}"
            for i, fila in enumerate(filas.itertuples(), start=1)
        )

    # Sin coincidencia exacta/por palabra (ej. errores de tipeo): buscar las
    # alternativas mas parecidas por similitud de texto en vez de fallar.
    mejores = _alternativas_fuzzy(catalogo, termino)
    if not mejores:
        return f"No encontré nada que se parezca a '{termino}'."
    lineas = [f"No encontré una coincidencia exacta con '{termino}'. ¿Quisiste decir alguna de estas?"]
    lineas += [f"{i}. {_legible(fila.producto)} {_legible(fila.variante)}" for i, fila in enumerate(mejores, start=1)]
    return "\n".join(lineas)


def buscar_receta(producto: str) -> str:
    """Devuelve el desglose de componentes y costo unitario de un producto (todas sus
    variantes que coincidan). Acepta texto descriptivo libre (ej. 'masa quebrada
    sablee', 'medialuna'), no hace falta el nombre exacto del producto."""
    catalogo = _load_catalogo()
    filas = _buscar_filas(catalogo, producto)
    if filas.empty:
        mejores = _alternativas_fuzzy(catalogo, producto)
        if mejores:
            opciones = ", ".join(f"{_legible(f.producto)} {_legible(f.variante)}" for f in mejores)
            return f"No encontré '{producto}' exacto. ¿Quisiste decir alguna de estas?: {opciones}"
        disponibles = sorted(catalogo["producto"].unique())
        return f"No encontré '{producto}' en el catálogo. Productos disponibles: {', '.join(disponibles)}."

    lineas = []
    for fila in filas.itertuples():
        if pd.notna(fila.costo_fijo):
            costo_unitario = float(fila.costo_fijo)
            detalle = "costo fijo (sin desglose de insumos)"
        else:
            componentes = _costeo_por_componente(fila.producto, fila.variante)
            costo_unitario = sum(componentes.values())
            detalle = ", ".join(f"{c}: ${v:.0f}" for c, v in componentes.items())
        tiene_precio = pd.notna(fila.precio_venta)
        food_cost = costo_unitario / fila.precio_venta * 100 if tiene_precio else None
        fc_txt = f"{food_cost:.1f}%" if food_cost is not None else "s/precio"
        precio_txt = f"${fila.precio_venta:.0f}" if tiene_precio else "sin precio definido"
        lineas.append(
            f"- {_legible(fila.producto)} {_legible(fila.variante)} [{_legible(fila.categoria)}]: "
            f"costo unitario ${costo_unitario:.0f} ({detalle}) | precio venta {precio_txt} | food cost {fc_txt}"
        )
    return "\n".join(lineas)


def _mensaje_no_encontrado(catalogo: pd.DataFrame, producto: str, variante: str) -> str:
    candidatas = _buscar_filas(catalogo, f"{producto} {variante}")
    if len(candidatas) > 1:
        opciones = ", ".join(f"{_legible(f.producto)} {_legible(f.variante)}" for f in candidatas.itertuples())
        return f"Encontré varias coincidencias para '{producto} {variante}', ¿cuál de estas es?: {opciones}"
    mejores = _alternativas_fuzzy(catalogo, f"{producto} {variante}")
    if mejores:
        opciones = ", ".join(f"{_legible(f.producto)} {_legible(f.variante)}" for f in mejores)
        return f"No encontré '{producto} {variante}' exacto. ¿Quisiste decir alguna de estas?: {opciones}"
    return f"No encontré el producto '{producto}' {variante}."


def _formatear_cantidad(total: float, unidad: str) -> str:
    if unidad == "g" and total >= 1000:
        return f"{total / 1000:.2f} kg"
    if unidad == "mL" and total >= 1000:
        return f"{total / 1000:.2f} L"
    return f"{total:.2f} {unidad}"


def receta_estandar(producto: str, variante: str) -> str:
    """Muestra la receta en las cantidades del LOTE ESTANDAR que realmente se
    mezcla en cocina para cada componente (ej. la Masa de la Medialuna
    Tradicional en su lote real de 4,8 kg de harina, no en gramos por unidad).
    Usa el rendimiento_lote guardado por receta. Esta es la forma natural de
    responder cuando el usuario pide "la receta" de un producto sin especificar
    una cantidad distinta a fabricar."""
    catalogo = _load_catalogo()
    info = _info_catalogo(producto, variante)
    if info is None:
        return _mensaje_no_encontrado(catalogo, producto, variante)
    producto, variante = info["producto"], info["variante"]

    ingredientes = _load_ingredientes()
    filas = ingredientes[
        (ingredientes["producto"].apply(_normalizar) == _normalizar(producto))
        & (ingredientes["variante"].apply(_normalizar) == _normalizar(variante))
    ]
    if filas.empty:
        return f"{_legible(producto)} {_legible(variante)} no tiene un desglose de insumos registrado (es costo fijo, sin receta detallada)."

    lineas = [f"Receta estándar de {_legible(producto)} {_legible(variante)}:"]
    for componente, grupo in filas.groupby("componente", sort=False):
        rendimiento_lote = grupo["rendimiento_lote"].iloc[0] if "rendimiento_lote" in grupo.columns else 1
        etiqueta_rinde = f" (lote rinde {rendimiento_lote:g})" if rendimiento_lote != 1 else " (por unidad)"
        lineas.append(f"  {componente}{etiqueta_rinde}:")
        for fila in grupo.itertuples():
            cantidad_lote = fila.cantidad * rendimiento_lote
            lineas.append(f"    - {fila.insumo}: {_formatear_cantidad(cantidad_lote, fila.unidad)}")

    tiempo = info.get("tiempo_fabricacion_min") if "tiempo_fabricacion_min" in info else None
    if pd.notna(tiempo):
        lineas.append(f"  Tiempo de fabricación: {float(tiempo):g} min/unidad")

    return "\n".join(lineas)


def escalar_ingredientes(producto: str, variante: str, cantidad: float) -> str:
    """Devuelve la lista de insumos y cantidades reales (gramos/kg/L/unidades) que
    hay que pesar/usar para fabricar `cantidad` de un producto/variante -- para
    saber QUÉ COMPRAR O PESAR, a diferencia de escalar_receta que da el COSTO."""
    catalogo = _load_catalogo()
    info = _info_catalogo(producto, variante)
    if info is None:
        return _mensaje_no_encontrado(catalogo, producto, variante)
    producto, variante = info["producto"], info["variante"]

    ingredientes = _load_ingredientes()
    filas = ingredientes[
        (ingredientes["producto"].apply(_normalizar) == _normalizar(producto))
        & (ingredientes["variante"].apply(_normalizar) == _normalizar(variante))
    ]
    if filas.empty:
        return f"{_legible(producto)} {_legible(variante)} no tiene un desglose de insumos registrado (es costo fijo, sin receta detallada)."

    acumulado: dict[tuple[str, str], float] = {}
    for fila in filas.itertuples():
        clave = (fila.insumo, fila.unidad)
        acumulado[clave] = acumulado.get(clave, 0.0) + fila.cantidad * cantidad

    lineas = [f"Para {cantidad:g} de {_legible(producto)} {_legible(variante)} necesitas:"]
    lineas += [f"  - {insumo}: {_formatear_cantidad(total, unidad)}" for (insumo, unidad), total in acumulado.items()]
    return "\n".join(lineas)


def escalar_receta(producto: str, variante: str, cantidad: float, food_cost_objetivo: float | None = None) -> str:
    """Escala el costo de un producto/variante para una cantidad objetivo de unidades.

    Si food_cost_objetivo (0-100) se entrega, calcula el precio de venta sugerido
    para lograr ese food cost. Si no, usa el precio de venta ya vigente del catalogo
    (si existe) y muestra el food cost real resultante.
    """
    info = _info_catalogo(producto, variante)
    if info is None:
        return _mensaje_no_encontrado(_load_catalogo(), producto, variante)

    producto, variante = info["producto"], info["variante"]
    costo_unitario = costo_unitario_producto(producto, variante)
    precio_unitario_actual = info["precio_venta"]
    tiene_precio = pd.notna(precio_unitario_actual)
    categoria = info["categoria"]

    costo_total = costo_unitario * cantidad

    resultado = [
        f"{_legible(producto)} {_legible(variante)} x{cantidad:g} unidades:",
        f"  Costo unitario: ${costo_unitario:.0f} -> Costo total: ${costo_total:.0f}",
    ]

    if food_cost_objetivo is not None:
        precio_sugerido_unitario = costo_unitario / (food_cost_objetivo / 100)
        precio_sugerido_total = precio_sugerido_unitario * cantidad
        resultado.append(
            f"  Precio de venta sugerido para food cost {food_cost_objetivo:.0f}%: "
            f"${precio_sugerido_unitario:.0f}/u -> ${precio_sugerido_total:.0f} total"
        )
    elif not tiene_precio:
        resultado.append("  Este producto todavía no tiene precio de venta definido en el catálogo.")
    else:
        ingreso_total = precio_unitario_actual * cantidad
        food_cost_real = costo_unitario / precio_unitario_actual * 100
        ganancia_total = ingreso_total - costo_total
        rango = BENCHMARK_FOOD_COST.get(categoria)
        rango_txt = f" (rango sano de referencia: {rango[0]}-{rango[1]}%)" if rango else ""
        resultado.append(
            f"  Precio de venta actual: ${precio_unitario_actual:.0f}/u -> Ingreso total: ${ingreso_total:.0f}"
        )
        resultado.append(
            f"  Food cost real: {food_cost_real:.1f}%{rango_txt} | Ganancia total: ${ganancia_total:.0f}"
        )

    return "\n".join(resultado)


def registrar_produccion(fecha: str, producto: str, variante: str, cantidad: float) -> str:
    """Registra la produccion del dia (unidades hechas) y calcula el costo/ingreso derivado.

    fecha en formato YYYY-MM-DD. El consumo de materia prima se deriva automaticamente
    del costeo de la receta -- no hace falta anotar insumo por insumo.
    """
    try:
        _dt.date.fromisoformat(fecha)
    except ValueError:
        return "Fecha invalida, usa formato YYYY-MM-DD."

    info = _info_catalogo(producto, variante)
    if info is None:
        return f"No encontré la receta de {producto} {variante}, no se registró producción."
    producto, variante = info["producto"], info["variante"]
    if pd.isna(info["precio_venta"]):
        return f"{producto} {variante} todavía no tiene precio de venta definido, no se puede registrar producción."

    costo_unitario = costo_unitario_producto(producto, variante)
    precio_unitario = info["precio_venta"]
    costo_total = costo_unitario * cantidad
    ingreso_total = precio_unitario * cantidad
    ganancia_total = ingreso_total - costo_total

    nueva_fila = pd.DataFrame([{
        "fecha": fecha,
        "producto": producto,
        "variante": variante,
        "cantidad": cantidad,
        "costo_unitario": costo_unitario,
        "precio_venta_unitario": precio_unitario,
        "costo_total": costo_total,
        "ingreso_total": ingreso_total,
        "ganancia_total": ganancia_total,
    }])

    produccion = _load_produccion()
    produccion = pd.concat([produccion, nueva_fila], ignore_index=True)
    produccion.to_csv(PRODUCCION_PATH, index=False)

    return (
        f"Registrado: {fecha} - {producto} {variante} x{cantidad:g}u. "
        f"Costo insumos: ${costo_total:.0f} | Ingreso: ${ingreso_total:.0f} | Ganancia: ${ganancia_total:.0f}"
    )


def costo_diario(fecha: str) -> str:
    """Suma el costo de produccion, ingreso y ganancia de un dia, desglosado por producto."""
    produccion = _load_produccion()
    del_dia = produccion[produccion["fecha"] == fecha]
    if del_dia.empty:
        return f"No hay producción registrada para {fecha}."

    lineas = [f"Producción del {fecha}:"]
    for (producto, variante), grupo in del_dia.groupby(["producto", "variante"]):
        lineas.append(
            f"  - {producto} {variante}: {grupo['cantidad'].sum():g}u | "
            f"costo ${grupo['costo_total'].sum():.0f} | ingreso ${grupo['ingreso_total'].sum():.0f}"
        )

    costo_total = del_dia["costo_total"].sum()
    ingreso_total = del_dia["ingreso_total"].sum()
    ganancia_total = del_dia["ganancia_total"].sum()
    lineas.append(
        f"TOTAL {fecha}: costo insumos ${costo_total:.0f} | ingreso ${ingreso_total:.0f} | ganancia ${ganancia_total:.0f}"
    )
    return "\n".join(lineas)
