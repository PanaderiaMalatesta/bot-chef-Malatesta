"""Orquesta el flujo completo de importar una receta por Telegram: desde el
texto/URL/imagen crudos hasta guardarla en el catalogo de costeo.

El estado de una importacion en curso (mientras se le preguntan precios de
insumos nuevos, unidades ambiguas, rendimiento, y finalmente la confirmacion)
vive en un dict por chat -- mismo patron que _chat_ultima_lista en
telegram_bot.py, para que el proximo mensaje del usuario continue el flujo
en vez de perderlo.

Todo el guardado reusa las herramientas ya existentes de tools.py
(crear_o_actualizar_insumo, reemplazar_receta_completa) -- este modulo NUNCA
escribe un CSV directamente.
"""
from __future__ import annotations

import re
import unicodedata

from . import ingest
from . import recipe_import
from . import recipe_standardize as rs
from . import tools as t

RECETAS_IMPORTADAS_PATH = ingest.DATA_DIR / "recetas_importadas.md"

# Palabras de afirmacion/relleno que Raul usa para decir "sí, guarda con el
# nombre sugerido" sin repetirlo (ver pregunta "producto" en aplicar_respuesta).
_PALABRAS_AFIRMATIVAS_NOMBRE = re.compile(
    r"\b(si|sí|dale|ok|correcto|esa|ese|esta|está|estan|están|bien|misma|mismo|"
    r"usa|la|el|referencia|sugerida|sugerencia)\b",
    re.IGNORECASE,
)


def slug_insumo(nombre: str) -> str:
    texto = unicodedata.normalize("NFKD", nombre)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    return texto.strip("_") or "insumo_nuevo"


def _buscar_insumo_mencionado(texto: str) -> str | None:
    """Busca si alguna PALABRA del texto (4+ letras, para evitar falsos
    positivos con palabras cortas comunes) coincide exactamente con el
    nombre normalizado de un insumo que YA existe en el catalogo."""
    precios = t._load_precios_insumos()
    palabras = {t._normalizar(p) for p in re.split(r"\s+", texto) if len(p) >= 4}
    for insumo in precios["insumo"]:
        if t._normalizar(insumo) in palabras:
            return insumo
    return None


def _resolver_sinonimos_pendientes(receta: "rs.RecetaEstandarizada") -> None:
    """Para ingredientes que quedaron sin insumo resuelto (no matchean por
    texto a nada del catalogo), pregunta al LLM si son sinonimos de algo que
    YA existe (ej. 'fecula de maiz' == 'maicena') y, si encuentra un
    candidato, los marca como ambiguos -- reusa la pregunta de confirmacion
    "¿es lo mismo que X?" que ya existe para casos ambiguos, en vez de
    asumir directamente que es un insumo nuevo."""
    pendientes = [
        ing for ing in receta.ingredientes
        if not ing.insumo_resuelto and not ing.ambiguo and ing.cantidad_lote is not None and ing.nombre_original
    ]
    if not pendientes:
        return
    precios = t._load_precios_insumos()
    resultados = rs.resolver_sinonimos([ing.nombre_original for ing in pendientes], list(precios["insumo"]))
    for ing in pendientes:
        candidato = resultados.get(ing.nombre_original)
        if candidato and candidato in set(precios["insumo"]):
            ing.ambiguo = True
            ing.candidatos_ambiguos = [candidato]


def iniciar_importacion(texto_crudo: str, metadata: recipe_import.RawExtraction) -> dict:
    """Corre extraccion LLM + estandarizacion Python y arma el estado inicial
    de una importacion. No guarda nada todavia."""
    contexto = ""
    if metadata.titulo:
        contexto += f"Título de la fuente: {metadata.titulo}\n"
    if metadata.autor:
        contexto += f"Autor/fuente: {metadata.autor}\n"

    receta_extraida = rs.estructurar_desde_texto(texto_crudo, contexto)
    receta_estandarizada = rs.estandarizar(receta_extraida)
    _resolver_sinonimos_pendientes(receta_estandarizada)

    return {
        "receta": receta_estandarizada,
        "metadata": metadata,
        "insumos_nuevos": {},  # clave -> (precio, unidad)
        "producto": None,
        "variante": None,
        "categoria": None,
        "precio_venta": None,
        "preguntando": None,
    }


_UNIDAD_PRECIO_TXT = r"(kilos?|kg|gramos?|gr?|litros?|lt?|mililitros?|ml|unidad(?:es)?)"

# Dos formas en que la gente realmente escribe un precio (probadas contra
# casos reales de produccion): "$5.000 el kg" (precio primero) y
# "20 g cuestan 1000" (cantidad primero, con verbo). La version anterior
# (un solo regex laxo que agarraba el primer numero+unidad de la frase, sin
# exigir "cuesta"/"$") interpretaba mal frases como "20 g cuestan 1000"
# -- tomaba "20"+"g" como si fueran el precio, ignorando el "1000" real, y
# daba una cifra silenciosamente inventada. Ahora, si el texto no calza con
# ninguno de estos dos patrones explicitos, se pide que lo reformule en vez
# de adivinar.
_PATRON_PRECIO_UNIDAD_PRIMERO = re.compile(
    r"\$?\s*([\d.,]+)\s*(?:por|el|la|cada|/)\s*" + _UNIDAD_PRECIO_TXT, re.IGNORECASE,
)
_PATRON_CANTIDAD_CUESTA_PRECIO = re.compile(
    # "cuest\w*" en vez de "cuestan?" para tolerar typos comunes de conjugacion
    # (ej. "20 g cuestas 1000" en vez de "cuestan") sin dejar de exigir un
    # verbo de costo explicito -- eso es lo que evita que se confunda un
    # numero cualquiera de la frase con el precio.
    r"([\d.,]+)\s*" + _UNIDAD_PRECIO_TXT + r"\s*(?:cuest\w*|vale[n]?|sale[n]?|est[aá]n?)\s*\$?\s*([\d.,]+)",
    re.IGNORECASE,
)


def _normalizar_unidad_precio(unidad_txt: str) -> tuple[str, float] | tuple[None, None]:
    """(unidad canonica de cotizacion, factor para pasar un precio "por esa
    unidad chica" a precio "por kg/L")."""
    u = unidad_txt.lower()
    if u.startswith("kilo") or u == "kg":
        return "kg", 1
    if u in ("g", "gr", "gramo", "gramos"):
        return "kg", 1000
    if u in ("ml", "mililitro", "mililitros"):
        return "L", 1000
    if u.startswith("litro") or u in ("l", "lt"):
        return "L", 1
    if u.startswith("unidad"):
        return "unidad", 1
    return None, None


def _num_precio(texto: str) -> float | None:
    """Precios en este sistema son siempre pesos chilenos enteros (nunca se
    vio un decimal en toda la sesion) -- el punto SIEMPRE es separador de
    miles aca (ej. "5.000" = 5000), nunca un decimal. Tratarlo como decimal
    (bug real encontrado en produccion: "$5.000 el kg" se leyo como $5) daria
    un precio 1000x mas bajo que el real."""
    try:
        return float(re.sub(r"[.,]", "", texto))
    except ValueError:
        return None


def _num_cantidad(texto: str) -> float | None:
    """Cantidades (kg/L/unidades de una compra) SI pueden tener un decimal
    real (ej. "0,5 kg"), a diferencia de los precios."""
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return None


def _parsear_precio(texto: str) -> tuple[float, str] | tuple[None, None]:
    m = _PATRON_CANTIDAD_CUESTA_PRECIO.search(texto)
    if m:
        cantidad_txt, unidad_txt, precio_txt = m.groups()
        cantidad, precio_total = _num_cantidad(cantidad_txt), _num_precio(precio_txt)
        unidad_final, factor = _normalizar_unidad_precio(unidad_txt)
        if unidad_final and cantidad and precio_total is not None:
            return precio_total / cantidad * factor, unidad_final

    m = _PATRON_PRECIO_UNIDAD_PRIMERO.search(texto)
    if m:
        precio_txt, unidad_txt = m.groups()
        precio = _num_precio(precio_txt)
        unidad_final, factor = _normalizar_unidad_precio(unidad_txt)
        if unidad_final and precio is not None:
            return precio * factor, unidad_final

    return None, None


def _unidad_de_cotizacion(insumo_resuelto: str | None, estado: dict) -> str | None:
    """Unidad en que ESE insumo esta cotizado (kg/L/unidad), buscando primero
    en precios_insumos.csv y si no en los insumos nuevos ya informados en
    esta misma importacion. None si todavia no se sabe (insumo nuevo sin
    precio dado aun)."""
    if not insumo_resuelto:
        return None
    if insumo_resuelto in estado["insumos_nuevos"]:
        return estado["insumos_nuevos"][insumo_resuelto][1]
    precios = t._load_precios_insumos()
    fila = precios.loc[precios["insumo"].str.lower() == insumo_resuelto.lower()]
    return fila["unidad"].iloc[0] if not fila.empty else None


def _unidades_compatibles(unidad_estandar: str, unidad_cotizacion: str) -> bool:
    return (
        (unidad_estandar == "g" and unidad_cotizacion == "kg")
        or (unidad_estandar == "mL" and unidad_cotizacion == "L")
        or (unidad_estandar == "unidad" and unidad_cotizacion == "unidad")
    )


def siguiente_pregunta(estado: dict) -> str | None:
    """Devuelve la proxima pregunta pendiente, o None si ya se puede mostrar
    el resumen final para confirmar."""
    receta = estado["receta"]

    for i, ing in enumerate(receta.ingredientes):
        if ing.ambiguo:
            opciones = "\n".join(f"  {j + 1}. {c}" for j, c in enumerate(ing.candidatos_ambiguos))
            estado["preguntando"] = ("ambiguo", i)
            return (
                f"\"{ing.texto_original}\" podría ser alguno de estos insumos que ya existen "
                f"en el catálogo:\n{opciones}\n  {len(ing.candidatos_ambiguos) + 1}. Es un insumo "
                "nuevo, distinto a todos estos\n¿Cuál número es?"
            )
        if ing.insumo_resuelto is None and ing.cantidad_lote is not None:
            estado["preguntando"] = ("nuevo_insumo", i)
            return f"\"{ing.texto_original}\" no está en el catálogo de insumos. ¿Cuánto cuesta? (ej. \"$5.000 el kg\")"
        if ing.unidad_estandar is None:
            estado["preguntando"] = ("unidad", i)
            return f"No pude determinar la cantidad/unidad de \"{ing.texto_original}\". Mándala como \"cantidad unidad\" (ej. \"200 g\")."
        unidad_ref = _unidad_de_cotizacion(ing.insumo_resuelto, estado)
        if unidad_ref and not _unidades_compatibles(ing.unidad_estandar, unidad_ref):
            estado["preguntando"] = ("peso_real", i)
            return (
                f"Tengo \"{ing.texto_original}\" como {ing.cantidad_lote:g} {ing.unidad_estandar}, pero "
                f"{ing.insumo_resuelto} se cotiza por {unidad_ref} -- son unidades distintas (volumen vs. "
                "peso) y no quiero adivinar la densidad. ¿Cuál es el peso real en gramos?"
            )

    if receta.rendimiento is None:
        estado["preguntando"] = ("rendimiento", None)
        return "¿Cuánto rinde esta receta? (ej. \"24 muffins\", \"1 torta\", \"12 porciones\")"

    if estado["producto"] is None:
        estado["preguntando"] = ("producto", None)
        sugerido = receta.original.nombre or "esta receta"
        return f"¿Con qué nombre guardo esta receta en el catálogo? (sugerencia: \"{sugerido}\")"

    estado["preguntando"] = ("confirmacion", None)
    return None


def aplicar_respuesta(estado: dict, texto: str) -> str | None:
    """Aplica la respuesta del usuario a la pregunta pendiente actual.
    Devuelve un mensaje de error para reintentar (sin avanzar el estado), o
    None si se aplicó bien."""
    tipo, idx = estado["preguntando"]
    receta = estado["receta"]

    if tipo == "ambiguo":
        ing = receta.ingredientes[idx]
        m = re.search(r"(\d+)", texto)
        if not m:
            return f"Sobre \"{ing.texto_original}\": responde con el número de la opción."
        n = int(m.group(1))
        if 1 <= n <= len(ing.candidatos_ambiguos):
            ing.insumo_resuelto = ing.candidatos_ambiguos[n - 1]
        elif n == len(ing.candidatos_ambiguos) + 1:
            ing.insumo_resuelto = None
        else:
            return f"Sobre \"{ing.texto_original}\": ese número no está en la lista, prueba de nuevo."
        ing.ambiguo = False
        # La primera conversion (en estandarizar()) se hizo sin saber todavia
        # cual insumo era -- reintentarla ahora puede encontrar una
        # equivalencia de panaderia (taza->gramos) que antes no estaba
        # disponible por no conocer el insumo resuelto.
        if ing.insumo_resuelto and ing.cantidad_original is not None and ing.unidad_original:
            ing.cantidad_lote, ing.unidad_estandar = rs._convertir_a_g_o_ml(
                ing.insumo_resuelto, ing.cantidad_original, ing.unidad_original, receta.conversiones_notas,
            )
        return None

    if tipo == "nuevo_insumo":
        ing = receta.ingredientes[idx]
        # A veces "no encontrado" fue un falso negativo del matcher (ej. el
        # insumo real se llama distinto a como lo escribio la fuente) y
        # Raul contesta redirigiendo a uno que YA existe (ej. "reemplaza eso
        # por maicena que ya esta en el catalogo") en vez de dar un precio.
        # Si el texto menciona por su nombre un insumo que ya existe, usar
        # ESE -- crear uno nuevo ahi hubiera duplicado el insumo con un
        # precio inventado (paso en produccion: "15 gr de maicena" se leyo
        # como precio $15.000/kg en vez de reconocer 'maicena').
        if re.search(r"reemplaza|usa|ya\s+est[aá]|ya\s+exist|es\s+lo\s+mismo|cat[aá]logo", texto, re.IGNORECASE):
            insumo_existente = _buscar_insumo_mencionado(texto)
            if insumo_existente:
                ing.insumo_resuelto = insumo_existente
                receta.conversiones_notas.append(
                    f"\"{ing.texto_original}\": Raúl indicó usar el insumo existente '{insumo_existente}' en vez de crear uno nuevo."
                )
                return None

        precio, unidad = _parsear_precio(texto)
        if precio is None:
            # Un numero "pelado" sin unidad (ej. "1 peso", "$1") es ambiguo en
            # general ($/kg? $/L?) salvo que el ingrediente YA se sepa que se
            # cuenta por unidad (ej. gotas) -- ahi si es seguro asumir que el
            # precio tambien es por unidad, sin necesidad de que Raul lo
            # aclare (no hay otra unidad posible para algo que se cuenta).
            m_pelado = re.match(r"^\s*(?:ponle|pon|dale|digamos)?\s*\$?\s*([\d.,]+)\s*(?:pesos?)?\s*\.?\s*$", texto, re.IGNORECASE)
            if m_pelado and ing.unidad_estandar == "unidad":
                precio = _num_precio(m_pelado.group(1))
                unidad = "unidad"
            if precio is None:
                return (
                    f"Sobre \"{ing.texto_original}\": no entendí el precio. Mándalo como \"$5.000 el kg\" o "
                    "\"20 g cuestan 1000\" (si ya existe con otro nombre en el catálogo, dime cuál)."
                )
        clave = slug_insumo(ing.nombre_original)
        estado["insumos_nuevos"][clave] = (precio, unidad)
        ing.insumo_resuelto = clave
        return None

    if tipo == "unidad":
        ing = receta.ingredientes[idx]
        m = re.search(r"([\d.,]+)\s*([a-zA-Záéíóú]+)", texto)
        if not m:
            # El usuario puede estar aclarando la UNIDAD sin repetir el numero
            # (ej. "gotas tambien es una unidad, guardalo asi") -- si nombra
            # algo contable equivalente a "unidad", reusar el numero que ya
            # estaba en el texto original de la fuente en vez de pedirlo de
            # nuevo (ya lo tenemos, no hace falta que el usuario lo retipee).
            if re.search(r"unidad|gota|pizca|hoja|diente|rama", texto, re.IGNORECASE):
                m_original = re.search(r"([\d.,]+)", ing.texto_original)
                if m_original:
                    cantidad = float(m_original.group(1).replace(",", "."))
                    ing.cantidad_lote = cantidad
                    ing.unidad_estandar = "unidad"
                    receta.conversiones_notas.append(
                        f"\"{ing.texto_original}\": Raúl aclaró que se mide por unidad -> {cantidad:g} unidad (cantidad tomada del texto original)."
                    )
                    return None
            return f"Sobre \"{ing.texto_original}\": mándala como \"cantidad unidad\", ej. \"200 g\" o \"2 unidades\"."
        cantidad = float(m.group(1).replace(",", "."))
        cantidad_conv, unidad_conv = rs._convertir_a_g_o_ml(ing.insumo_resuelto, cantidad, m.group(2), receta.conversiones_notas)
        if cantidad_conv is None:
            return f"Sobre \"{ing.texto_original}\": no reconocí esa unidad -- prueba con g, kg, mL, L o unidad."
        ing.cantidad_lote = cantidad_conv
        ing.unidad_estandar = unidad_conv
        return None

    if tipo == "peso_real":
        ing = receta.ingredientes[idx]
        m = re.search(r"([\d.,]+)", texto)
        if not m:
            return f"Sobre \"{ing.texto_original}\": dime el peso en gramos, ej. \"4 g\" o solo \"4\"."
        ing.cantidad_lote = float(m.group(1).replace(",", "."))
        ing.unidad_estandar = "g"
        receta.conversiones_notas.append(f"{ing.insumo_resuelto}: peso real confirmado por Raúl -> {ing.cantidad_lote:g} g (reemplaza la conversión de volumen de arriba).")
        return None

    if tipo == "rendimiento":
        m = re.search(r"([\d.,]+)", texto)
        if not m:
            return "Dime solo el número, ej. \"24\"."
        receta.rendimiento = float(m.group(1).replace(",", "."))
        resto = texto[m.end():].strip()
        receta.rendimiento_unidad = resto or receta.rendimiento_unidad or "unidades"
        return None

    if tipo == "producto":
        nombre = texto.strip()
        sugerido = receta.original.nombre
        # Raul puede confirmar el nombre sugerido con cualquier variante de
        # "sí, esa"/"dale"/"está bien ese"/"usa la referencia" en vez de
        # reescribirlo -- en vez de una lista fija de frases (que ya fallo
        # dos veces en produccion: "usa la referencia" y "esta bien ese"
        # quedaron guardados como nombre LITERAL), se sacan las palabras de
        # afirmacion/relleno conocidas y si no queda nada mas, es un "sí".
        resto = _PALABRAS_AFIRMATIVAS_NOMBRE.sub("", nombre)
        resto = re.sub(r"[.,!¡¿?\s]+", "", resto)
        if sugerido and not resto:
            estado["producto"] = sugerido
            estado["variante"] = ""
            return None
        if not nombre:
            return "Dime el nombre con el que guardo la receta."
        estado["producto"] = nombre
        estado["variante"] = ""
        return None

    return None


def costear(estado: dict) -> dict:
    """Calcula costo por ingrediente/total/unitario con los precios ya
    conocidos (existentes + los nuevos recien informados). No toca ningun
    CSV, solo lee.

    Importante: solo costea cuando la unidad ya convertida (g/mL/unidad) es
    dimensionalmente compatible con la unidad en que ESE insumo esta cotizado
    en precios_insumos.csv (kg/L/unidad). Un ingrediente medido en cucharadas
    sin equivalencia de peso conocida queda en mL (ver
    recipe_standardize._convertir_a_g_o_ml) -- si el insumo se cotiza por kg,
    tratar esos mL como si fueran gramos daria un costo inventado (asumiria
    densidad 1, que no esta garantizado). En ese caso el ingrediente queda
    fuera del total y se lista en `sin_costear` para que Raul confirme la
    cantidad real en vez de mostrar una cifra falsa."""
    receta = estado["receta"]
    precios = t._load_precios_insumos()
    precios_extra = estado["insumos_nuevos"]  # clave -> (precio, unidad)

    detalle = []
    sin_costear = []
    costo_total = 0.0
    for ing in receta.ingredientes:
        if not ing.insumo_resuelto or ing.cantidad_lote is None or not ing.unidad_estandar:
            continue
        fila_precio = precios.loc[precios["insumo"].str.lower() == ing.insumo_resuelto.lower()]
        if not fila_precio.empty:
            precio_ref = fila_precio["precio"].iloc[0]
        elif ing.insumo_resuelto in precios_extra:
            precio_ref = precios_extra[ing.insumo_resuelto][0]
        else:
            continue

        unidad_ref = _unidad_de_cotizacion(ing.insumo_resuelto, estado)
        if not unidad_ref or not _unidades_compatibles(ing.unidad_estandar, unidad_ref):
            # No deberia pasar (siguiente_pregunta ya obliga a resolver esto
            # antes de llegar aca) -- se deja como red de seguridad para no
            # costear con una unidad incompatible bajo ninguna circunstancia.
            sin_costear.append(
                f"{ing.insumo_resuelto}: tengo {ing.cantidad_lote:g} {ing.unidad_estandar}, pero ese insumo "
                f"se cotiza por {unidad_ref or '??'} -- no puedo costearlo con confianza, confirma la cantidad real."
            )
            continue

        factor = 0.001 if ing.unidad_estandar in ("g", "mL") else 1.0
        costo = ing.cantidad_lote * factor * precio_ref
        costo_total += costo
        detalle.append((ing.insumo_resuelto, ing.cantidad_lote, ing.unidad_estandar, costo))

    rendimiento = receta.rendimiento or 1
    costo_unitario = costo_total / rendimiento if rendimiento else None
    return {
        "detalle": detalle, "costo_total": costo_total, "costo_unitario": costo_unitario,
        "rendimiento": rendimiento, "sin_costear": sin_costear,
    }


def formatear_resumen(estado: dict) -> str:
    receta = estado["receta"]
    original = receta.original
    costeo = costear(estado)

    partes = [f"📋 Ficha técnica propuesta: {estado['producto']}"]

    partes.append("\n— INFORMACIÓN ORIGINAL —")
    if original.nombre:
        partes.append(f"Nombre en la fuente: {original.nombre}")
    if estado["metadata"].url:
        partes.append(f"Fuente: {estado['metadata'].url}")
    if estado["metadata"].autor:
        partes.append(f"Autor: {estado['metadata'].autor}")
    partes.append("Ingredientes (tal cual la fuente):")
    for ing in receta.ingredientes:
        partes.append(f"  - {ing.texto_original}")
    if original.pasos:
        partes.append("Procedimiento (tal cual la fuente):")
        for i, paso in enumerate(original.pasos, 1):
            partes.append(f"  {i}. {paso}")
    if original.tiempo_preparacion_min:
        partes.append(f"Tiempo de preparación: {original.tiempo_preparacion_min:g} min")
    if original.tiempo_coccion_min:
        partes.append(f"Tiempo de cocción: {original.tiempo_coccion_min:g} min")
    if original.temperatura:
        partes.append(f"Temperatura: {original.temperatura}")

    if receta.conversiones_notas:
        partes.append("\n— INTERPRETACIÓN (conversiones aplicadas) —")
        for nota in receta.conversiones_notas:
            partes.append(f"  - {nota}")

    partes.append("\n— PROPUESTA ESTANDARIZADA —")
    partes.append(f"Rinde: {receta.rendimiento:g} {receta.rendimiento_unidad or ''}")
    for ing in receta.ingredientes:
        if ing.insumo_resuelto and ing.cantidad_lote is not None:
            partes.append(f"  - {ing.insumo_resuelto}: {ing.cantidad_lote:g} {ing.unidad_estandar} (lote completo)")

    partes.append("\n— COSTEO —")
    for insumo, cantidad, unidad, costo in costeo["detalle"]:
        partes.append(f"  - {insumo}: {cantidad:g}{unidad} = ${costo:,.0f}".replace(",", "."))
    partes.append(f"Costo total del lote: ${costeo['costo_total']:,.0f}".replace(",", "."))
    if costeo["costo_unitario"] is not None:
        partes.append(f"Costo por unidad: ${costeo['costo_unitario']:,.0f}".replace(",", "."))
    if costeo["sin_costear"]:
        partes.append("Sin costear todavía (unidad incompatible con la del insumo, no calculado para no inventar):")
        for linea in costeo["sin_costear"]:
            partes.append(f"  - {linea}")

    if estado["metadata"].advertencias:
        partes.append("\n⚠️ Advertencias de la extracción:")
        for adv in estado["metadata"].advertencias:
            partes.append(f"  - {adv}")

    partes.append("\n¿Guardo esta receta en el catálogo? Responde \"sí\" para confirmar, o \"no\" para descartarla.")
    return "\n".join(partes)


def guardar(estado: dict) -> str:
    """Escribe la receta confirmada usando las mismas herramientas de
    tools.py que ya usa el resto del bot (crear_o_actualizar_insumo,
    reemplazar_receta_completa), agrega la version narrativa al recetario
    importado, y actualiza el indice de busqueda en caliente."""
    receta = estado["receta"]

    for clave, (precio, unidad) in estado["insumos_nuevos"].items():
        t.crear_o_actualizar_insumo(clave, precio, unidad)

    rendimiento = receta.rendimiento or 1
    lineas = [
        {"insumo": ing.insumo_resuelto, "cantidad": ing.cantidad_lote / rendimiento, "unidad": ing.unidad_estandar}
        for ing in receta.ingredientes
        if ing.insumo_resuelto and ing.cantidad_lote is not None and ing.unidad_estandar
        # red de seguridad: nunca guardar un ingrediente cuya unidad no sea
        # compatible con la del insumo (ver costear/_unidades_compatibles) --
        # no deberia pasar porque siguiente_pregunta ya lo exige antes de
        # llegar a confirmar, pero si pasara, es mejor omitir la fila que
        # dejar un costo mal calculado permanente en el catalogo.
        and _unidades_compatibles(ing.unidad_estandar, _unidad_de_cotizacion(ing.insumo_resuelto, estado) or "")
    ]
    mensaje = t.reemplazar_receta_completa(
        estado["producto"], estado["variante"] or "", lineas,
        categoria=estado.get("categoria"), precio_venta=estado.get("precio_venta"),
    )

    _apendizar_recetario(estado)
    _actualizar_indice(estado)
    return mensaje


def _texto_narrativo(estado: dict) -> str:
    receta = estado["receta"]
    original = receta.original
    partes = [f"### {estado['producto']} {estado['variante']} — rinde {receta.rendimiento:g} {receta.rendimiento_unidad or ''}".rstrip()]
    if estado["metadata"].url:
        partes.append(f"Fuente: {estado['metadata'].url}")
    partes.append("Ingredientes: " + "; ".join(
        f"{ing.cantidad_lote:g}{ing.unidad_estandar} de {ing.insumo_resuelto}"
        for ing in receta.ingredientes if ing.insumo_resuelto and ing.cantidad_lote is not None
    ))
    if original.pasos:
        partes.append("Procedimiento: " + " ".join(original.pasos))
    if original.tiempo_coccion_min and original.temperatura:
        partes.append(f"Horneado a {original.temperatura} por {original.tiempo_coccion_min:g} minutos.")
    if original.observaciones:
        partes.append(f"Observaciones: {original.observaciones}")
    return "\n".join(partes)


def _apendizar_recetario(estado: dict) -> None:
    texto = _texto_narrativo(estado)
    with open(RECETAS_IMPORTADAS_PATH, "a", encoding="utf-8") as f:
        f.write("\n\n" + texto + "\n")


def _actualizar_indice(estado: dict) -> None:
    try:
        vectorstore = ingest.load_index()
        vectorstore.add_texts([_texto_narrativo(estado)])
        vectorstore.save_local(str(ingest.INDEX_DIR))
    except Exception:  # noqa: BLE001
        # El indice de busqueda es secundario -- la receta ya quedo guardada
        # en los CSV/recetario, un fallo aca no debe perderla.
        pass
