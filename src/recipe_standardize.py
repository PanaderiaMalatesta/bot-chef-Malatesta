"""Estructuracion (LLM) + estandarizacion (Python) de una receta cruda.

Separa siempre tres niveles, sin mezclarlos (pedido explicito de Raul):
  - INFORMACION ORIGINAL: lo que el LLM extrajo literalmente del texto fuente
    (RecetaExtraida). Cada campo ausente en la fuente queda en None -- el LLM
    usa salida estructurada (Pydantic), no texto libre, precisamente para que
    "no se cuanto rinde" se traduzca en None y no en un numero inventado.
  - INTERPRETACION: conversiones de unidad necesarias para poder trabajar la
    receta (ej. "1 taza" -> mL, o a gramos cuando hay una equivalencia de
    panaderia conocida), siempre listadas explicitamente.
  - PROPUESTA ESTANDARIZADA: ingredientes ya resueltos a insumos canonicos de
    precios_insumos.csv, en cantidad POR UNIDAD, listos para
    tools.reemplazar_receta_completa.

Igual que en tools.py: toda la aritmetica (conversion de unidades,
porcentajes de panaderia, costeo) es Python, nunca el LLM.
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field

import pandas as pd
from dotenv import load_dotenv
from langchain_cohere import ChatCohere
from pydantic import BaseModel, Field

from . import tools as t

load_dotenv()

# --- Nivel 1: INFORMACION ORIGINAL (salida estructurada del LLM) ----------


class IngredienteExtraido(BaseModel):
    texto_original: str = Field(description="El texto EXACTO del ingrediente tal cual aparece en la fuente, ej. '2 tazas de harina sin polvos'.")
    nombre: str = Field(description="Solo el nombre del ingrediente, ej. 'harina sin polvos'.")
    cantidad: float | None = Field(default=None, description="Cantidad numerica si esta explicita en la fuente. None si no se puede determinar.")
    unidad: str | None = Field(default=None, description="Unidad tal cual aparece en la fuente (ej. 'tazas', 'g', 'cdta'). None si no aplica o no esta clara.")


class RecetaExtraida(BaseModel):
    """Todo lo que el LLM pudo leer LITERALMENTE de la fuente. Cualquier dato
    que la fuente no menciona debe quedar en None -- nunca inventar."""

    nombre: str | None = Field(default=None, description="Nombre/titulo de la receta.")
    categoria: str | None = Field(default=None, description="Tipo de preparacion (ej. panaderia, pasteleria, galleta), solo si es evidente.")
    # Requerido (sin default) -- Cohere exige que el schema de salida
    # estructurada tenga al menos un campo requerido en cada objeto, y
    # semanticamente es el campo central de la extraccion (una lista vacia
    # sigue siendo una respuesta valida si la fuente no tiene ingredientes).
    ingredientes: list[IngredienteExtraido] = Field(description="Lista de ingredientes encontrados en la fuente, en el orden en que aparecen.")
    pasos: list[str] = Field(default_factory=list, description="Pasos del procedimiento, en orden, tal cual la fuente.")
    rendimiento: float | None = Field(default=None, description="Cuanto rinde la receta, solo el numero.")
    rendimiento_unidad: str | None = Field(default=None, description="Unidad del rendimiento tal cual la fuente (ej. 'unidades', 'porciones', 'muffins', 'una torta').")
    tiempo_preparacion_min: float | None = Field(default=None, description="Tiempo de preparacion en minutos si esta explicito.")
    tiempo_coccion_min: float | None = Field(default=None, description="Tiempo de coccion/horneado en minutos si esta explicito.")
    temperatura: str | None = Field(default=None, description="Temperatura de horneado/coccion tal cual la fuente (con su unidad, ej. '350F' o '180C').")
    equipamiento: str | None = Field(default=None, description="Equipamiento especial mencionado (ej. 'batidora', 'molde 24cm'), si la fuente lo menciona.")
    observaciones: str | None = Field(default=None, description="Notas, tips o advertencias del autor que valga la pena conservar.")


def estructurar_desde_texto(texto_crudo: str, contexto: str = "") -> RecetaExtraida:
    """Llama al LLM UNA vez para convertir texto crudo (blog/subtitulos/OCR) en
    RecetaExtraida. No hace ningun calculo -- solo lee y estructura lo que
    esta literalmente en el texto."""
    llm = ChatCohere(model="command-a-03-2025", temperature=0, cohere_api_key=os.environ["COHERE_API_KEY"])
    extractor = llm.with_structured_output(RecetaExtraida)
    prompt = (
        "Extraé la receta del siguiente texto. Reglas estrictas:\n"
        "1. NUNCA inventes ni completes un dato que no esté literalmente en el texto -- "
        "si no dice el rendimiento, la temperatura, o la cantidad de un ingrediente, déjalo en None.\n"
        "2. No conviertas unidades ni hagas ningún cálculo -- copia los números y unidades tal "
        "cual aparecen en la fuente, eso se hace en un paso aparte.\n"
        "3. Los ingredientes van en el orden en que aparecen.\n"
        "4. Si UN MISMO ingrediente tiene dos medidas (ej. \"3/4 taza de azúcar (175g)\" o "
        "\"1 cucharada de maicena (15g)\"), SIEMPRE elige la medida en gramos/mililitros/kg/L "
        "para `cantidad`/`unidad` (es la precisa), NUNCA la de taza/cucharada -- pero deja el "
        "texto COMPLETO (con ambas medidas) en `texto_original`. Ejemplo: para "
        "\"3/4 taza de azúcar (175g)\" -> cantidad=175, unidad=\"g\" (no 0.75/\"taza\").\n"
        "5. Si un ingrediente tiene una cantidad de referencia PESE A una salvedad como "
        "\"al gusto\", \"opcional\" o \"o al gusto\" (ej. \"5 gotas de colorante (o al gusto)\"), "
        "IGUAL extrae esa cantidad numérica -- la salvedad significa que se puede ajustar en la "
        "práctica, no que la cantidad de la receta sea desconocida. Ejemplo: "
        "\"5 gotas de colorante rojo comestible (o al gusto)\" -> cantidad=5, unidad=\"gotas\" "
        "(no None).\n\n"
        f"{contexto}\n\nTEXTO FUENTE:\n{texto_crudo[:12000]}"
    )
    return extractor.invoke(prompt)


# --- Nivel 2 y 3: INTERPRETACION + PROPUESTA ESTANDARIZADA (Python puro) ---

# Equivalencias peso<->volumen de referencia de panaderia profesional, SOLO
# para los insumos donde hay un estandar ampliamente aceptado (no es una
# conversion de unidad "pura" -- depende de la densidad del ingrediente, por
# eso se limita a estos pocos casos conocidos en vez de aplicarse a
# cualquier cosa). Gramos por taza (240 mL).
_GRAMOS_POR_TAZA = {
    "harina_0000": 120, "harina_almendras": 96, "azucar": 200, "azucar_flor": 120,
    "azucar_morena": 220, "mantequilla": 227, "cacao_polvo": 85, "leche_polvo": 68,
}
_CDTA_ML = 5.0
_CDA_ML = 15.0
_TAZA_ML = 240.0

_UNIDADES_PESO = {"g", "gramo", "gramos", "kg", "kilo", "kilos", "kilogramo", "kilogramos"}
_UNIDADES_VOLUMEN_ML = {"ml", "mililitro", "mililitros", "cc"}
_UNIDADES_VOLUMEN_L = {"l", "lt", "litro", "litros"}
_UNIDADES_CUCHARA = {"cdta", "cucharadita", "cucharaditas", "cdas", "cucharada", "cucharadas", "cda"}
_UNIDADES_TAZA = {"taza", "tazas", "cup", "cups"}
_UNIDADES_PIEZA = {
    "unidad", "unidades", "u", "pieza", "piezas",
    # "gotas" es una medida real por si sola (ej. colorantes, esencias) -- no
    # tiene sentido pedir su equivalencia en gramos, se cuenta como unidad.
    "gota", "gotas",
}


@dataclass
class IngredienteEstandarizado:
    texto_original: str
    nombre_original: str
    cantidad_lote: float | None
    unidad_estandar: str | None  # g, mL o unidad -- o None si no se pudo determinar
    insumo_resuelto: str | None  # clave canonica en precios_insumos.csv
    ambiguo: bool = False  # hubo mas de un insumo candidato, hay que preguntar cual
    candidatos_ambiguos: list[str] = field(default_factory=list)
    cantidad_original: float | None = None  # tal cual la fuente, para poder reconvertir
    unidad_original: str | None = None  # una vez que se resuelva una ambiguedad (recien
    # ahi se sabe el insumo real y se puede aplicar la equivalencia de panaderia)


@dataclass
class RecetaEstandarizada:
    original: RecetaExtraida
    ingredientes: list[IngredienteEstandarizado]
    conversiones_notas: list[str]
    rendimiento: float | None
    rendimiento_unidad: str | None


def _normalizar_unidad_texto(unidad: str) -> str:
    return re.sub(r"[^a-z]", "", unidad.strip().lower())


def _convertir_a_g_o_ml(nombre_insumo_resuelto: str | None, cantidad: float, unidad_txt: str, notas: list[str]) -> tuple[float | None, str | None]:
    u = _normalizar_unidad_texto(unidad_txt)

    if u in _UNIDADES_PESO:
        factor = 1000 if "kilo" in u or u == "kg" else 1
        return cantidad * factor, "g"

    if u in _UNIDADES_VOLUMEN_ML:
        return cantidad, "mL"
    if u in _UNIDADES_VOLUMEN_L:
        return cantidad * 1000, "mL"

    if u in _UNIDADES_PIEZA:
        return cantidad, "unidad"

    if u in _UNIDADES_CUCHARA:
        ml = cantidad * (_CDTA_ML if "cdta" in u or "cucharadita" in u else _CDA_ML)
        if nombre_insumo_resuelto and nombre_insumo_resuelto in _GRAMOS_POR_TAZA:
            gramos = ml / _TAZA_ML * _GRAMOS_POR_TAZA[nombre_insumo_resuelto]
            notas.append(f"'{cantidad:g} {unidad_txt}' de {nombre_insumo_resuelto} -> {gramos:.1f} g (equivalencia de panadería estándar).")
            return gramos, "g"
        notas.append(f"'{cantidad:g} {unidad_txt}' -> {ml:g} mL (conversión de volumen; no hay equivalencia de peso confiable para este insumo, confirmar cantidad real).")
        return ml, "mL"

    if u in _UNIDADES_TAZA:
        ml = cantidad * _TAZA_ML
        if nombre_insumo_resuelto and nombre_insumo_resuelto in _GRAMOS_POR_TAZA:
            gramos = cantidad * _GRAMOS_POR_TAZA[nombre_insumo_resuelto]
            notas.append(f"'{cantidad:g} {unidad_txt}' de {nombre_insumo_resuelto} -> {gramos:.1f} g (equivalencia de panadería estándar).")
            return gramos, "g"
        notas.append(f"'{cantidad:g} {unidad_txt}' -> {ml:g} mL (conversión de volumen; no hay equivalencia de peso confiable para este insumo, confirmar cantidad real).")
        return ml, "mL"

    notas.append(f"No reconocí la unidad '{unidad_txt}' -- queda sin convertir, hay que confirmarla a mano.")
    return None, None


def resolver_insumo(nombre_libre: str, precios: pd.DataFrame) -> tuple[str | None, bool, list[str]]:
    """Busca `nombre_libre` entre las claves canonicas de precios_insumos.csv.
    Devuelve (insumo_resuelto, ambiguo, candidatos). Reusa el mismo enfoque
    exacto->palabras->fuzzy que tools.py ya usa para producto/variante e
    insumos dentro de una receta, para no reintroducir el bug de substrings
    (ej. 'sablee' matcheando 'sableecacao') que ya causo problemas en agosto."""
    objetivo = t._normalizar(nombre_libre)
    lista_insumos = list(precios["insumo"])

    for insumo in lista_insumos:
        if t._normalizar(insumo) == objetivo:
            return insumo, False, []

    palabras = [p for p in re.split(r"\s+", nombre_libre.strip().lower()) if p and t._normalizar(p) not in t._STOPWORDS]
    candidatos = [ins for ins in lista_insumos if palabras and all(t._normalizar(p) in t._normalizar(ins) for p in palabras)]
    if len(candidatos) == 1:
        return candidatos[0], False, []
    if len(candidatos) > 1:
        return None, True, candidatos

    puntajes = sorted(
        ((difflib.SequenceMatcher(None, objetivo, t._normalizar(ins)).ratio(), ins) for ins in lista_insumos),
        key=lambda par: par[0], reverse=True,
    )
    if puntajes and puntajes[0][0] >= 0.72:
        return puntajes[0][1], False, []
    return None, False, []


class _SinonimoInsumo(BaseModel):
    nombre_buscado: str = Field(description="El nombre del ingrediente tal cual se buscó, copiado exactamente.")
    insumo_equivalente: str | None = Field(
        default=None,
        description="El nombre EXACTO (copiado tal cual) de un insumo de la lista de insumos existentes que es "
        "el MISMO producto (sinónimo, nombre de marca que se volvió genérico, o forma alternativa de decirlo) "
        "-- NO un insumo relacionado o parecido, tiene que ser literalmente lo mismo. None si no hay ninguno.",
    )


class _ResolucionSinonimos(BaseModel):
    resultados: list[_SinonimoInsumo] = Field(description="Un resultado por cada nombre de la lista a resolver, en el mismo orden.")


def resolver_sinonimos(nombres_sin_match: list[str], lista_insumos: list[str]) -> dict[str, str | None]:
    """Para ingredientes que _resolver_insumo no pudo emparejar por texto (ej.
    'fécula de maíz' vs. el insumo existente 'maicena' -- son sinónimos, pero
    no comparten ninguna palabra ni son parecidos como texto), pregunta al
    LLM si alguno es el mismo producto que algo que ya existe en el
    catálogo. A diferencia de resolver_insumo (matching de texto, Python
    puro), esto SI necesita al LLM porque requiere conocimiento del mundo
    (que 'maicena' es una marca de fécula de maíz), no comparación de
    strings. Nunca decide solo -- el resultado se usa para PREGUNTAR
    ('¿es lo mismo que maicena?'), nunca para reemplazar sin confirmar."""
    if not nombres_sin_match:
        return {}
    llm = ChatCohere(model="command-a-03-2025", temperature=0, cohere_api_key=os.environ["COHERE_API_KEY"])
    extractor = llm.with_structured_output(_ResolucionSinonimos)
    prompt = (
        "Para cada ingrediente de la LISTA A, decime si es exactamente EL MISMO producto "
        "(sinónimo, nombre de marca que se volvió genérico, o forma alternativa de decirlo en "
        "español latinoamericano) que alguno de los insumos de la LISTA B. Ejemplos reales: "
        "'fécula de maíz' es lo mismo que 'maicena' (maicena es una marca que se volvió el "
        "nombre genérico); 'azúcar glass'/'azúcar impalpable' es lo mismo que 'azúcar flor'. "
        "Si tenés alguna duda, o el parecido es solo de categoría (ej. dos tipos distintos de "
        "chocolate) y no el MISMO producto, respondé None -- es mejor no encontrar nada que "
        "encontrar algo incorrecto.\n\n"
        f"LISTA A (a resolver): {nombres_sin_match}\n"
        f"LISTA B (insumos existentes): {lista_insumos}"
    )
    resultado = extractor.invoke(prompt)
    return {r.nombre_buscado: r.insumo_equivalente for r in resultado.resultados}


def estandarizar(receta: RecetaExtraida) -> RecetaEstandarizada:
    precios = t._load_precios_insumos()
    notas: list[str] = []
    ingredientes: list[IngredienteEstandarizado] = []

    for ing in receta.ingredientes:
        insumo_resuelto = ambiguo = candidatos = None
        cantidad_convertida = unidad_convertida = None

        if ing.nombre:
            insumo_resuelto, ambiguo, candidatos = resolver_insumo(ing.nombre, precios)

        if ing.cantidad is not None and ing.unidad:
            cantidad_convertida, unidad_convertida = _convertir_a_g_o_ml(insumo_resuelto, ing.cantidad, ing.unidad, notas)
        elif ing.cantidad is not None and not ing.unidad:
            notas.append(f"'{ing.texto_original}' no tiene unidad clara -- hay que confirmarla.")

        ingredientes.append(IngredienteEstandarizado(
            texto_original=ing.texto_original,
            nombre_original=ing.nombre,
            cantidad_lote=cantidad_convertida,
            unidad_estandar=unidad_convertida,
            insumo_resuelto=insumo_resuelto,
            ambiguo=bool(ambiguo),
            candidatos_ambiguos=candidatos or [],
            cantidad_original=ing.cantidad,
            unidad_original=ing.unidad,
        ))

    return RecetaEstandarizada(
        original=receta,
        ingredientes=ingredientes,
        conversiones_notas=notas,
        rendimiento=receta.rendimiento,
        rendimiento_unidad=receta.rendimiento_unidad,
    )


def porcentajes_panaderos(receta: RecetaEstandarizada) -> dict[str, float] | None:
    """% de cada insumo sobre el peso total de harina (solo insumos en gramos
    con insumo resuelto). None si no hay una harina identificable."""
    peso_harina = sum(
        i.cantidad_lote for i in receta.ingredientes
        if i.unidad_estandar == "g" and i.insumo_resuelto and "harina" in i.insumo_resuelto
    )
    if not peso_harina:
        return None
    return {
        i.insumo_resuelto: round(i.cantidad_lote / peso_harina * 100, 1)
        for i in receta.ingredientes
        if i.unidad_estandar == "g" and i.insumo_resuelto and i.cantidad_lote is not None
    }
