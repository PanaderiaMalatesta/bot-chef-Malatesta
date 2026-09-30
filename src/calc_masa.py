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


def calcular_masa_pan(
    peso_final_g: float,
    hidratacion_pct: float,
    sal_pct: float,
    levadura_pct: float = 0.0,
    porcentaje_prefermento_pct: float = 0.0,
    hidratacion_prefermento_pct: float = 0.0,
    levadura_prefermento_pct: float = 0.0,
    sal_prefermento_pct: float = 0.0,
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
    en 0 (sin levadura comercial agregada)."""
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

    if min(harina, agua, levadura, sal) < -0.05:
        return (
            "Con esos números el cálculo da una cantidad negativa de harina, agua, "
            "levadura o sal fuera del prefermento -- revisa que el % de prefermento "
            "no sea muy alto, o que su hidratación no sea muy distinta a la de la "
            "masa final."
        )

    lineas = [f"Para {Pf:g} g de masa final al {hidratacion_pct:g}% de hidratación:"]
    lineas.append(f"  - Harina: {max(harina, 0):.1f} g")
    lineas.append(f"  - Agua: {max(agua, 0):.1f} g")
    if levadura_pct or levadura_prefermento_pct:
        lineas.append(f"  - Levadura: {max(levadura, 0):.1f} g")
    if sal_pct or sal_prefermento_pct:
        lineas.append(f"  - Sal: {max(sal, 0):.1f} g")

    if Pi:
        harina_pref = Pi / (1 + hi)
        agua_pref = Pi - harina_pref
        levadura_pref = harina_pref * plp
        sal_pref = harina_pref * psp
        lineas.append(
            f"\nPrefermento/masa madre a usar: {Pi:.1f} g "
            f"({porcentaje_prefermento_pct:g}% de la harina total, al {hidratacion_prefermento_pct:g}% de hidratación)"
        )
        detalle = f"  Contiene: {harina_pref:.1f} g harina + {agua_pref:.1f} g agua"
        if levadura_pref:
            detalle += f" + {levadura_pref:.2f} g levadura"
        if sal_pref:
            detalle += f" + {sal_pref:.2f} g sal"
        lineas.append(detalle)
        lineas.append("  (la harina/agua/levadura/sal de arriba son lo que se agrega ADEMÁS del prefermento)")

    return "\n".join(lineas)
