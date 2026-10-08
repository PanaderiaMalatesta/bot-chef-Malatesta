"""Calculadora de masa de pan por porcentaje de panadero (baker's percentages).

Formulas tomadas tal cual de calcmasa.com (calc_H/calc_lev/calc_sal/calc_Pi
en su JS), verificadas contra la calculadora real: el metodo directo
reproduce exacto los valores de su UI (625 g harina / 375 g agua / 9.4 g
levadura / 11.3 g sal para 1000 g de masa al 60% hidratacion, 1.5%
levadura, 1.8% sal), y el metodo con prefermento se verifico corriendo las
mismas funciones en Node.js con sus valores por defecto.

Una sola formula sirve para los 3 metodos de la calculadora original
(directo, prefermento con levadura, masa madre natural) -- la diferencia
entre ellos es solo que metodo directo tiene porcentaje_prefermento_pct=0, y
masa madre natural tipicamente tiene levadura_prefermento_pct=0 (la masa
madre no lleva levadura comercial, fermenta con su propia flora silvestre).
"""
from __future__ import annotations

# Biga de fermentacion larga (16 a 24 h a 16-18 °C): 0,3% de levadura SECA
# sobre la harina de la biga (fresca = seca x 3 -> 0,9%). Poca levadura a
# proposito: busca maxima complejidad de sabor sin agotar el prefermento.
BIGA_LEVADURA_SECA_PCT = 0.3
FACTOR_FRESCA_SECA = 3


def levadura_biga_pct(tipo_levadura: str) -> float:
    """% de levadura de la biga (sobre su harina) segun el tipo de levadura."""
    fresca = (tipo_levadura or "").strip().lower().startswith("fresc")
    return BIGA_LEVADURA_SECA_PCT * (FACTOR_FRESCA_SECA if fresca else 1)


def _datos_faltantes(tipo_prefermento, porcentaje_pct, hidratacion_pref_pct, levadura_pct, tipo_levadura) -> list[str]:
    tipo = (tipo_prefermento or "").strip().lower().replace(" ", "_")
    masa_madre = tipo in ("masa_madre", "masamadre")
    usa_pref = bool(porcentaje_pct) or tipo in ("biga", "poolish", "prefermento") or masa_madre
    nombre = {"biga": "la biga", "poolish": "el poolish"}.get(tipo, "la masa madre" if masa_madre else "el prefermento")
    faltan = []
    if usa_pref and not porcentaje_pct:
        faltan.append(f"qué % de la harina total va en {nombre}")
    if usa_pref and not hidratacion_pref_pct:
        faltan.append(f"la hidratación de {nombre}" + (" (la biga suele ir entre 45% y 55%)" if tipo == "biga" else ""))
    if not masa_madre and not levadura_pct:
        faltan.append("el % de levadura total sobre la harina")
    if not masa_madre and not (tipo_levadura or "").strip():
        faltan.append("si la levadura es fresca o seca")
    return faltan


def calcular_masa_pan(
    peso_final_g: float,
    hidratacion_pct: float,
    sal_pct: float,
    levadura_pct: float = 0.0,
    porcentaje_prefermento_pct: float = 0.0,
    hidratacion_prefermento_pct: float = 0.0,
    levadura_prefermento_pct: float = 0.0,
    sal_prefermento_pct: float = 0.0,
    tipo_prefermento: str = "",
    tipo_levadura: str = "",
    aceite_pct: float = 0.0,
) -> str:
    """Calcula harina/agua/levadura/sal (en gramos) para una masa de pan.
    sal_pct es obligatorio (sin default a proposito) para que quien llama
    esta funcion SIEMPRE lo pida explicitamente, nunca lo asuma en 0 -- la
    sal aplica a los 3 metodos por igual, a diferencia de la levadura.

    Metodo directo: dejar porcentaje_prefermento_pct=0 (default).
    Metodo con prefermento o masa madre: dar porcentaje_prefermento_pct (qué
    % de la harina TOTAL de la masa final viene del prefermento/masa madre,
    ej. 16) e hidratacion_prefermento_pct (la hidratación de ESE
    prefermento/masa madre, no la de la masa final -- una masa madre típica
    es 100). Los porcentajes de levadura/sal DEL prefermento
    (levadura_prefermento_pct, sal_prefermento_pct) son sobre la HARINA del
    prefermento, no sobre su peso total -- para masa madre natural dejarlos
    en 0 (sin levadura comercial agregada).

    Si tipo_prefermento es 'biga', la levadura de la biga NO se toma de
    levadura_prefermento_pct: se fija en la dosis de fermentacion larga
    (0,3% seca / 0,9% fresca segun tipo_levadura).

    aceite_pct es opcional (tipico en masa de pizza): % sobre la harina
    total, se agrega todo en la masa final.

    Si faltan datos obligatorios para el metodo elegido, NO calcula: devuelve
    un mensaje "FALTAN DATOS" con lo que hay que preguntarle al usuario --
    el modelo a veces se salta preguntas y llama con ceros, y eso daba
    cantidades negativas sin explicar por que."""
    faltan = _datos_faltantes(
        tipo_prefermento, porcentaje_prefermento_pct, hidratacion_prefermento_pct,
        levadura_pct, tipo_levadura,
    )
    if faltan:
        return (
            "FALTAN DATOS: no calcules todavía. Pregúntale al usuario, una cosa a la vez:" + chr(10)
            + chr(10).join(f"- {f}" for f in faltan)
        )
    es_biga = (tipo_prefermento or "").strip().lower() == "biga" and porcentaje_prefermento_pct
    if es_biga:
        levadura_prefermento_pct = levadura_biga_pct(tipo_levadura)
        # la biga ya aporta levadura: el % total no puede ser menor que eso
        aporte_biga = porcentaje_prefermento_pct * levadura_prefermento_pct / 100
        if levadura_pct + 1e-9 < aporte_biga:
            return (
                f"Con la biga al {porcentaje_prefermento_pct:g}% de la harina, la biga ya lleva "
                f"{aporte_biga:.2f}% de levadura sobre la harina total "
                f"({levadura_prefermento_pct:g}% de su propia harina). El % de levadura total "
                f"que pidió ({levadura_pct:g}%) es menor que eso, así que no queda levadura "
                "para la masa final. Pregúntale si quiere subir el % de levadura total o "
                "dejar la masa final sin levadura adicional (usar exactamente ese aporte)."
            )
    tl = (tipo_levadura or "").strip().lower()
    nombre_levadura = "Levadura fresca" if tl.startswith("fresc") else "Levadura seca" if tl.startswith("sec") else "Levadura"

    Pf = peso_final_g
    hf = hidratacion_pct / 100
    plev = levadura_pct / 100
    psal = sal_pct / 100
    php = porcentaje_prefermento_pct / 100
    hi = (hidratacion_prefermento_pct / 100) if php else 0.0
    plp = levadura_prefermento_pct / 100
    psp = sal_prefermento_pct / 100

    # Pi = peso del prefermento/masa madre, derivado del % de harina total
    # que representa (calc_Pi de calcmasa.com).
    Pi = (hi + 1) * (php * Pf) / (hf + 1) if php else 0.0

    harina = ((Pf - Pi) / (1 + hf)) - Pi * (hf - hi) / ((1 + hi) * (1 + hf))
    agua = Pf - Pi - harina
    levadura = (Pf * plev) / (1 + hf) - (Pi * plp) / (1 + hi)
    sal = (Pf * psal) / (1 + hf) - (Pi * psp) / (1 + hi)

    negativos = [n for n, v in (("harina", harina), ("agua", agua), ("levadura", levadura), ("sal", sal)) if v < -0.05]
    if negativos:
        motivo = {
            "agua": "la hidratación del prefermento es mayor que la de la masa final, o el % de prefermento es muy alto",
            "harina": "el % de prefermento es demasiado alto",
            "levadura": "el % de levadura del prefermento supera al % de levadura total",
            "sal": "el % de sal del prefermento supera al % de sal total",
        }
        return (
            "Con esos números queda una cantidad negativa de "
            + ", ".join(negativos)
            + " para la masa final: "
            + "; ".join(motivo[n] for n in negativos)
            + ". Explícaselo al usuario y pregúntale qué valor quiere ajustar."
        )
    harina_total = Pf / (1 + hf)
    aceite = harina_total * aceite_pct / 100

    lineas = [f"Para {Pf:g} g de masa final al {hidratacion_pct:g}% de hidratación:"]
    lineas.append(f"  - Harina: {max(harina, 0):.1f} g")
    lineas.append(f"  - Agua: {max(agua, 0):.1f} g")
    if levadura_pct or levadura_prefermento_pct:
        lineas.append(f"  - {nombre_levadura}: {max(levadura, 0):.1f} g")
    if sal_pct or sal_prefermento_pct:
        lineas.append(f"  - Sal: {max(sal, 0):.1f} g")
    if aceite_pct:
        lineas.append(f"  - Aceite: {aceite:.1f} g ({aceite_pct:g}% de la harina total)")

    if Pi:
        harina_pref = Pi / (1 + hi)
        agua_pref = Pi - harina_pref
        levadura_pref = harina_pref * plp
        sal_pref = harina_pref * psp
        nombre_pref = "Biga" if es_biga else "Prefermento/masa madre"
        lineas.append(
            f"\n{nombre_pref} a usar: {Pi:.1f} g "
            f"({porcentaje_prefermento_pct:g}% de la harina total, al {hidratacion_prefermento_pct:g}% de hidratación)"
        )
        detalle = f"  Contiene: {harina_pref:.1f} g harina + {agua_pref:.1f} g agua"
        if levadura_pref:
            detalle += f" + {levadura_pref:.2f} g {nombre_levadura.lower()} ({levadura_prefermento_pct:g}% de su harina)"
        if sal_pref:
            detalle += f" + {sal_pref:.2f} g sal"
        lineas.append(detalle)
        if es_biga:
            lineas.append("  Fermentación larga: 16 a 24 h a 16-18 °C.")
        lineas.append("  (la harina/agua/levadura/sal de arriba son lo que se agrega ADEMÁS del prefermento)")

    return "\n".join(lineas)


def calcular_masa_desde_biga(
    peso_biga_g: float,
    hidratacion_biga_pct: float,
    hidratacion_pct: float,
    sal_pct: float,
    levadura_pct: float = 0.0,
    tipo_levadura: str = "",
    aceite_pct: float = 0.0,
    porcentaje_biga_pct: float = 0.0,
    peso_final_g: float = 0.0,
    peso_bollo_g: float = 0.0,
) -> str:
    """Calcula la masa completa partiendo de una biga YA HECHA (pesada).

    La biga se asume hecha con la dosis de fermentacion larga (0,3% seca /
    0,9% fresca sobre su harina), asi que su levadura se descuenta del % de
    levadura total. El tamaño de la masa se define con UNO de estos dos:
    porcentaje_biga_pct (qué % de la harina total aporta la biga) o
    peso_final_g (cuánta masa total se quiere). Todos los % son de panadero,
    sobre la harina TOTAL (la de la biga + la que se agrega). peso_bollo_g
    es opcional: divide la masa en bollos (pizza)."""
    faltan = []
    if not peso_biga_g:
        faltan.append("cuánto pesa la biga ya hecha (en gramos)")
    if not hidratacion_biga_pct:
        faltan.append("con qué hidratación se hizo la biga (suele ser entre 45% y 55%)")
    if not hidratacion_pct:
        faltan.append("la hidratación final que quiere para la masa")
    if not sal_pct:
        faltan.append("el % de sal sobre la harina")
    if not levadura_pct:
        faltan.append("el % de levadura total sobre la harina")
    if not (tipo_levadura or "").strip():
        faltan.append("si la levadura es fresca o seca")
    if not porcentaje_biga_pct and not peso_final_g:
        faltan.append("cuánta masa final quiere, o qué % de la harina total debe venir de la biga")
    if faltan:
        return (
            "FALTAN DATOS: no calcules todavía. Pregúntale al usuario, una cosa a la vez:" + chr(10)
            + chr(10).join(f"- {f}" for f in faltan)
        )

    tl = tipo_levadura.strip().lower()
    nombre_lev = "Levadura fresca" if tl.startswith("fresc") else "Levadura seca"
    hb = hidratacion_biga_pct / 100
    harina_biga = peso_biga_g / (1 + hb)
    agua_biga = peso_biga_g - harina_biga
    lev_biga = harina_biga * levadura_biga_pct(tipo_levadura) / 100

    suma_pct = (hidratacion_pct + sal_pct + levadura_pct + aceite_pct) / 100
    if porcentaje_biga_pct:
        harina_total = harina_biga / (porcentaje_biga_pct / 100)
    else:
        harina_total = peso_final_g / (1 + suma_pct)
    pct_biga = harina_biga / harina_total * 100
    if pct_biga > 100:
        return (
            f"La biga sola ya tiene {harina_biga:.0f} g de harina, más que toda la harina "
            f"que necesita una masa de {peso_final_g:g} g. Pregúntale si quiere hacer más masa "
            "o usar solo una parte de la biga."
        )

    agua_total = harina_total * hidratacion_pct / 100
    lev_total = harina_total * levadura_pct / 100
    add = {
        "Harina": harina_total - harina_biga,
        "Agua": agua_total - agua_biga,
        nombre_lev: lev_total - lev_biga,
        "Sal": harina_total * sal_pct / 100,
    }
    if aceite_pct:
        add["Aceite"] = harina_total * aceite_pct / 100
    if add["Agua"] < -0.5:
        return (
            f"La biga ya trae {agua_biga:.0f} g de agua, más de lo que pide una masa al "
            f"{hidratacion_pct:g}% con esa cantidad de harina. Explícaselo y pregúntale si quiere "
            "subir la hidratación final o bajar el % de biga."
        )
    if add[nombre_lev] < -0.05:
        return (
            f"La biga ya aporta {lev_biga:.1f} g de levadura ({lev_biga / harina_total * 100:.2f}% "
            f"sobre la harina total), más que el {levadura_pct:g}% que pidió. Pregúntale si quiere "
            "subir el % de levadura o no agregar levadura en la masa final."
        )

    total = peso_biga_g + sum(max(v, 0) for v in add.values())
    L = [f"Masa completa partiendo de {peso_biga_g:g} g de biga (al {hidratacion_biga_pct:g}% de hidratación):",
         f"La biga aporta el {pct_biga:.0f}% de la harina total ({harina_biga:.0f} g de {harina_total:.0f} g).",
         "", "AGREGAR A LA BIGA:"]
    for k, v in add.items():
        L.append(f"  - {k}: {max(v, 0):.1f} g")
    L += ["", f"PESO FINAL DE LA MASA: {total:.0f} g",
          f"Totales en la masa: harina {harina_total:.0f} g · agua {agua_total:.0f} g "
          f"({hidratacion_pct:g}%) · {nombre_lev.lower()} {lev_total:.1f} g ({levadura_pct:g}%) · "
          f"sal {add['Sal']:.1f} g ({sal_pct:g}%)"
          + (f" · aceite {add['Aceite']:.1f} g ({aceite_pct:g}%)" if aceite_pct else "")]
    if peso_bollo_g:
        n = int(total // peso_bollo_g)
        L.append(f"Rinde {n} bollos de {peso_bollo_g:g} g (sobran {total - n * peso_bollo_g:.0f} g).")
    return chr(10).join(L)
