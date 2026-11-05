"""Calcular una masa con botones: las preguntas que hace el agente, pero en Python.

Igual que la cotizacion, los numeros no pasan por el LLM: las cuentas son las de
calc_masa. Los botones solo sugieren valores frecuentes; ningun dato se asume, cada uno
lo elige o lo escribe quien calcula.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from . import calc_masa

MIN_PESO_G = 50
MAX_PESO_G = 500000

_METODOS = {"directo": "Directo", "poolish": "Poolish", "biga": "Biga", "masa madre": "Masa madre",
            "biga hecha": "Biga ya hecha"}
_ALIAS_METODO = {"biga ya hecha": "biga hecha", "masamadre": "masa madre", "prefermento": "poolish"}
_TIPO_PREFERMENTO = {"directo": "", "poolish": "poolish", "biga": "biga", "masa madre": "masa_madre"}
_PREFERMENTO = {"poolish": "el poolish", "biga": "la biga", "masa madre": "la masa madre"}

_NUMERO = r"(\d+(?:[.,]\d+)*)"
_PATRON_PESO = re.compile(rf"\s*{_NUMERO}\s*(kg|kilos?|g|gr|grs|gramos?)?\s*\.?\s*", re.IGNORECASE)
_PATRON_PORCENTAJE = re.compile(rf"\s*{_NUMERO}\s*(%|por\s*ciento)?\s*\.?\s*", re.IGNORECASE)
_PATRON_MILES = re.compile(r"[1-9]\d{0,2}(?:\.\d{3})+")
_PATRON_SIN = re.compile(r"\s*(no|0|sin\b.*)\s*\.?\s*", re.IGNORECASE)
_PATRON_ATRAS = re.compile(r"\s*(atr[aá]s|volver)\s*\.?\s*", re.IGNORECASE)
_PATRON_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")


def _numero(crudo: str) -> float | None:
    """1,8 y 1.8 son lo mismo, pero 5.000 son cinco mil."""
    if _PATRON_MILES.fullmatch(crudo):
        return float(crudo.replace(".", ""))
    try:
        return float(crudo.replace(",", "."))
    except ValueError:
        return None


def _leer_gramos(texto: str) -> float | None:
    coincide = _PATRON_PESO.fullmatch(texto)
    valor = _numero(coincide.group(1)) if coincide else None
    if valor is None:
        return None
    return valor * 1000 if (coincide.group(2) or "").lower().startswith("k") else valor


def _leer_porcentaje(texto: str) -> float | None:
    coincide = _PATRON_PORCENTAJE.fullmatch(texto)
    return _numero(coincide.group(1)) if coincide else None


def _entre(leer: Callable, desde: float, hasta: float) -> Callable:
    """Un 5 como peso de masa es un error de tipeo: se pregunta de nuevo, no se calcula."""
    def leer_con_limites(texto: str) -> float | None:
        valor = leer(texto)
        return valor if valor is not None and desde <= valor <= hasta else None
    return leer_con_limites


def _o_sin(leer: Callable) -> Callable:
    return lambda texto: 0.0 if _PATRON_SIN.fullmatch(texto) else leer(texto)


def _leer_tipo_levadura(texto: str) -> str | None:
    return "fresca" if re.search(r"\bfresc", texto, re.IGNORECASE) else "seca" if re.search(r"\bsec", texto, re.IGNORECASE) else None


_leer_peso = _entre(_leer_gramos, MIN_PESO_G, MAX_PESO_G)
_leer_pct_harina = _entre(_leer_porcentaje, 1, 100)


def _leer_tamano(texto: str) -> tuple[str, float] | None:
    """La masa final en gramos, o el % de la harina total que aporta la biga."""
    coincide = _PATRON_PORCENTAJE.fullmatch(texto)
    if coincide and coincide.group(2):
        valor = _leer_pct_harina(texto)
        return ("%", valor) if valor is not None else None
    valor = _leer_peso(texto)
    return ("g", valor) if valor is not None else None


def _gramos(*valores: int) -> tuple[tuple[str, str], ...]:
    return tuple((f"{v:,} g".replace(",", "."), str(v)) for v in valores)


def _porcentajes(*valores: str) -> tuple[tuple[str, str], ...]:
    return tuple((f"{v}%", v) for v in valores)


@dataclass(frozen=True)
class _Dato:
    pregunta: str
    ayuda: str
    leer: Callable
    rapidas: tuple[tuple[str, str], ...] = ()


_AYUDA_PESO = 'Escribe los gramos, por ejemplo 5000, o "5 kg".'
_DATOS = {
    "peso": _Dato("¿Cuánta masa final quieres hacer? Elige o escribe los gramos.", _AYUDA_PESO, _leer_peso,
                  _gramos(1000, 2000, 5000, 10000)),
    "peso_biga": _Dato("¿Cuánto pesa la biga ya hecha? Elige o escribe los gramos.", _AYUDA_PESO, _leer_peso,
                       _gramos(500, 1000, 1500, 2000)),
    "biga_hidratacion": _Dato("¿Con qué hidratación se hizo la biga? Elige o escribe el %.",
                              "Escribe un % entre 20 y 200, por ejemplo 50.", _entre(_leer_porcentaje, 20, 200),
                              _porcentajes("45", "50", "55")),
    "hidratacion": _Dato("¿Qué hidratación quieres para la masa? Elige o escribe el %.",
                         "Escribe un % entre 20 y 200, por ejemplo 65.", _entre(_leer_porcentaje, 20, 200),
                         _porcentajes("60", "65", "70", "75")),
    "pref_pct": _Dato("¿Qué % de la harina total va en {pref}? Elige o escribe el %.",
                      "Escribe un % entre 1 y 100, por ejemplo 30.", _leer_pct_harina),
    "pref_hidratacion": _Dato("¿Con qué hidratación va {pref}? Elige o escribe el %.",
                              "Escribe un % entre 20 y 200, por ejemplo 100.", _entre(_leer_porcentaje, 20, 200)),
    "sal": _Dato("¿Qué % de sal, sobre la harina? Elige o escribe el %.",
                 "Escribe un % mayor que 0 y hasta 10, por ejemplo 2.", _entre(_leer_porcentaje, 0.01, 10),
                 _porcentajes("1,8", "2", "2,2")),
    "tipo_levadura": _Dato("¿La levadura es fresca o seca?", "Responde fresca o seca.", _leer_tipo_levadura,
                           (("Fresca", "fresca"), ("Seca", "seca"))),
    "levadura": _Dato("¿Qué % de levadura total, sobre la harina? Elige o escribe el %.",
                      "Escribe un % mayor que 0 y hasta 30, por ejemplo 1,5.", _entre(_leer_porcentaje, 0.01, 30)),
    "levadura_pref": _Dato("¿Qué % de levadura lleva {pref}, sobre su propia harina? Elige o escribe el %.",
                           "Escribe un % entre 0 y 30, por ejemplo 0,5.", _entre(_leer_porcentaje, 0, 30),
                           _porcentajes("0,1", "0,5", "1")),
    "aceite": _Dato("¿Lleva aceite? Elige o escribe el %, sobre la harina.",
                    'Escribe un % entre 0 y 50, por ejemplo 3, o "sin aceite".', _o_sin(_entre(_leer_porcentaje, 0, 50)),
                    (("Sin aceite", "sin aceite"), *_porcentajes("2", "3", "5"))),
    "tamano": _Dato("¿Cuánta masa final quieres? Escribe los gramos (ej. 4000), o elige qué % de la harina total "
                    "aporta la biga.",
                    'Escribe los gramos, por ejemplo 4000 o "4 kg", o un porcentaje como 30%.', _leer_tamano,
                    (("30%", "30%"), ("40%", "40%"), ("50%", "50%"))),
    "bollo": _Dato("¿La divides en bollos? Elige o escribe cuánto pesa cada uno.",
                   'Escribe los gramos de cada bollo, por ejemplo 250, o "sin bollos".',
                   _o_sin(_entre(_leer_gramos, 10, 5000)), (("Sin bollos", "sin bollos"), *_gramos(200, 250, 280))),
}

_RAPIDAS_PREFERMENTO = {
    "pref_pct": {"poolish": _porcentajes("20", "30", "40", "50"), "biga": _porcentajes("20", "30", "40", "50"),
                 "masa madre": _porcentajes("10", "15", "20", "30")},
    "pref_hidratacion": {"poolish": _porcentajes("100"), "biga": _porcentajes("45", "50", "55"),
                         "masa madre": _porcentajes("50", "60", "100")},
}
_RAPIDAS_LEVADURA = {"fresca": _porcentajes("1", "1,5", "2", "3"), "seca": _porcentajes("0,3", "0,5", "1", "1,5")}

_CON_PREFERMENTO = ("peso", "hidratacion", "pref_pct", "pref_hidratacion", "sal")
_PASOS = {
    "directo": ("peso", "hidratacion", "sal", "tipo_levadura", "levadura", "aceite"),
    "poolish": (*_CON_PREFERMENTO, "tipo_levadura", "levadura", "levadura_pref", "aceite"),
    # la levadura de la biga la fija calc_masa: fermentacion larga
    "biga": (*_CON_PREFERMENTO, "tipo_levadura", "levadura", "aceite"),
    # la masa madre no lleva levadura comercial
    "masa madre": (*_CON_PREFERMENTO, "aceite"),
    "biga hecha": ("peso_biga", "biga_hidratacion", "hidratacion", "sal", "tipo_levadura", "levadura", "aceite", "tamano",
                   "bollo"),
}


def iniciar() -> dict:
    return {"preguntando": "metodo", "metodo": None, "datos": {}, "problema": ""}


def _siguiente(estado: dict) -> str | None:
    return next((p for p in _PASOS[estado["metodo"]] if p not in estado["datos"]), None)


def _cifra(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def _dato_en_texto(estado: dict, paso: str) -> str:
    valor = estado["datos"][paso]
    pref = _PREFERMENTO.get(estado["metodo"], "")
    de_pref = f"de {pref}".replace("de el ", "del ")
    if paso == "tipo_levadura":
        return f"levadura {valor}"
    if paso == "tamano":
        return f"masa final {_cifra(valor[1])} g" if valor[0] == "g" else f"la biga aporta {_cifra(valor[1])}% de la harina"
    if paso == "aceite" and not valor:
        return "sin aceite"
    if paso == "bollo" and not valor:
        return "sin bollos"
    plantillas = {"peso": "masa final {} g", "peso_biga": "biga {} g", "biga_hidratacion": "hidratación de la biga {}%",
                  "hidratacion": "hidratación {}%", "pref_pct": f"{pref} con el {{}}% de la harina",
                  "pref_hidratacion": f"hidratación {de_pref} {{}}%", "sal": "sal {}%", "levadura": "levadura total {}%",
                  "levadura_pref": f"levadura {de_pref} {{}}%", "aceite": "aceite {}%", "bollo": "bollos de {} g"}
    return plantillas[paso].format(_cifra(valor))


def _resumen(estado: dict) -> str:
    datos = [_dato_en_texto(estado, p) for p in _PASOS[estado["metodo"]] if p in estado["datos"]]
    return " · ".join([_METODOS[estado["metodo"]], *datos])


def siguiente_pregunta(estado: dict) -> str:
    paso = estado["preguntando"]
    if paso == "metodo":
        return ("¿Qué método quieres usar?\n\n"
                "Biga ya hecha es para cuando la biga ya está pesada y solo falta calcular lo que se agrega.")
    if paso == "ajustar":
        return f"{estado['problema']}\n\n¿Qué dato quieres cambiar?"
    pregunta = _DATOS[paso].pregunta.format(pref=_PREFERMENTO.get(estado["metodo"], ""))
    return f"{_resumen(estado)}\n\n{pregunta}"


def opciones(estado: dict) -> list[tuple[str, str]]:
    """Los botones de la pregunta actual: (lo que dice, lo que responde)."""
    paso = estado["preguntando"]
    if paso == "metodo":
        return [(nombre, clave) for clave, nombre in _METODOS.items()]
    if paso == "ajustar":
        return [(_dato_en_texto(estado, p).capitalize(), p) for p in _PASOS[estado["metodo"]]]
    if paso in _RAPIDAS_PREFERMENTO:
        return list(_RAPIDAS_PREFERMENTO[paso][estado["metodo"]])
    if paso == "levadura":
        return list(_RAPIDAS_LEVADURA[estado["datos"]["tipo_levadura"]])
    return list(_DATOS[paso].rapidas)


def puede_volver(estado: dict) -> bool:
    return estado["preguntando"] not in ("metodo", "ajustar")


def _volver(estado: dict) -> None:
    pasos = _PASOS[estado["metodo"]]
    i = pasos.index(estado["preguntando"])
    if i == 0:
        estado.update(preguntando="metodo", metodo=None, datos={})
        return
    estado["datos"].pop(pasos[i - 1], None)
    estado["preguntando"] = pasos[i - 1]


def aplicar_respuesta(estado: dict, texto: str) -> str | None:
    """Guarda la respuesta del paso actual y avanza. Devuelve un mensaje de error (y no
    avanza) si la respuesta no sirve. Sin mas que preguntar, "preguntando" queda en None."""
    paso = estado["preguntando"]
    if paso == "metodo":
        clave = texto.strip().lower()
        clave = _ALIAS_METODO.get(clave, clave)
        if clave not in _METODOS:
            return "Elige un método con los botones, o escribe directo, poolish, biga, masa madre o biga hecha."
        estado["metodo"] = clave
    elif paso == "ajustar":
        if texto not in estado["datos"]:
            return "Elige con un botón qué dato quieres cambiar."
        del estado["datos"][texto]
    elif _PATRON_ATRAS.fullmatch(texto):
        _volver(estado)
        return None
    else:
        valor = _DATOS[paso].leer(texto)
        if valor is None:
            return _DATOS[paso].ayuda
        estado["datos"][paso] = valor
    estado["preguntando"] = _siguiente(estado)
    return None


def _con_coma(texto: str) -> str:
    return _PATRON_DECIMAL.sub(",", texto)


def _calcular_masa(estado: dict) -> str:
    d = estado["datos"]
    if estado["metodo"] == "biga hecha":
        unidad, tamano = d["tamano"]
        return calc_masa.calcular_masa_desde_biga(
            d["peso_biga"], d["biga_hidratacion"], d["hidratacion"], d["sal"], d["levadura"], d["tipo_levadura"], d["aceite"],
            porcentaje_biga_pct=tamano if unidad == "%" else 0.0, peso_final_g=tamano if unidad == "g" else 0.0,
            peso_bollo_g=d["bollo"],
        )
    return calc_masa.calcular_masa_pan(
        d["peso"], d["hidratacion"], d["sal"], d.get("levadura", 0.0), d.get("pref_pct", 0.0), d.get("pref_hidratacion", 0.0),
        d.get("levadura_pref", 0.0), 0.0, _TIPO_PREFERMENTO[estado["metodo"]], d.get("tipo_levadura", ""), d["aceite"],
    )


def calcular(estado: dict) -> str | None:
    """El resultado, o None si esos numeros no dan una masa: queda preguntando qué dato cambiar."""
    resultado = _con_coma(_calcular_masa(estado))
    if resultado.startswith(calc_masa.PROBLEMA):
        estado.update(preguntando="ajustar", problema=resultado)
        return None
    return f"{_resumen(estado)}\n\n{resultado}"
