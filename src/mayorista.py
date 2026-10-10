"""Venta mayorista a cafeterias: lista de precios en PDF y cotizaciones
guiadas por Telegram.

Igual que la importacion de recetas, la cotizacion es un flujo de preguntas
en Python (no del LLM): el bot pregunta en orden, valida cada respuesta y
todos los montos se calculan aca, para que el modelo nunca invente precios.

Los precios de data/precios_mayorista.csv son FINALES CON IVA. El neto se
obtiene dividiendo por 1,19. El nivel se define solo por cantidad total de
unidades del pedido: 48 o mas -> nivel B, si no nivel A (minimo 12).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .paths import DATA_DIR

PRECIOS_MAYORISTA_PATH = DATA_DIR / "precios_mayorista.csv"
COTIZACIONES_DIR = DATA_DIR / "cotizaciones"
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"

IVA = 0.19
MINIMO_UNIDADES = 12
UMBRAL_NIVEL_B = 48
VALIDEZ_DIAS = 15

TELEFONO = "+56 9 3132 6999"
PIE = (
    "<b>Panadería Artesanal Malatesta</b> · Vicente Reyes 562, Villarrica<br/>"
    f"Pedidos y consultas: <b>{TELEFONO}</b> (WhatsApp) · oficialmalatesta@gmail.com · malatestachile.cl"
)
CONDICIONES = [
    f"<b>Pedido mínimo:</b> {MINIMO_UNIDADES} unidades por despacho; puedes combinar productos. "
    "Las unidades de todos los productos se suman para definir el nivel.",
    f"<b>Nivel B</b> desde {UMBRAL_NIVEL_B} unidades por despacho.",
    "<b>Facturas</b> siempre surtidas (membrillo, pastelera y manjar).",
    "<b>Pedidos</b> con 48 horas de anticipación.",
    "<b>Pago:</b> contra entrega.",
    "<b>Despacho</b> en Villarrica; otras zonas se coordinan.",
]

CAFE = colors.HexColor("#4A2E1F")
TERRA = colors.HexColor("#B5643C")
CREMA = colors.HexColor("#F6EEE3")
CREMA2 = colors.HexColor("#EFE2D0")
GRIS = colors.HexColor("#6B5B50")

_ST_TITULO = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=20, textColor=CAFE, alignment=TA_CENTER, leading=24)
_ST_SUB = ParagraphStyle("s", fontName="Helvetica", fontSize=10.5, textColor=GRIS, alignment=TA_CENTER, leading=14)
_ST_NORMAL = ParagraphStyle("n", fontName="Helvetica", fontSize=8.8, textColor=CAFE, leading=11.5)
_ST_COND = ParagraphStyle("c", fontName="Helvetica", fontSize=8.8, textColor=CAFE, leading=12.5)
_ST_COND_TIT = ParagraphStyle("ct", parent=_ST_COND, fontName="Helvetica-Bold", textColor=TERRA, fontSize=9.5)
_ST_PIE = ParagraphStyle("f", fontName="Helvetica", fontSize=9, textColor=colors.white, alignment=TA_CENTER, leading=13)
_ST_DERECHA = ParagraphStyle("r", parent=_ST_NORMAL, alignment=TA_RIGHT)

ANCHO_UTIL = 172 * mm


# --- Datos ------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def cargar_precios() -> pd.DataFrame:
    df = pd.read_csv(PRECIOS_MAYORISTA_PATH)
    for columna in ("detalle", "receta_producto", "receta_variante"):
        df[columna] = df[columna].fillna("").astype(str)
    df["precio_a"] = df["precio_a"].astype(int)
    df["precio_b"] = df["precio_b"].astype(int)
    return df


def neto(precio_con_iva: float) -> int:
    return round(precio_con_iva / (1 + IVA))


def fmt(n: float) -> str:
    return "$" + f"{n:,.0f}".replace(",", ".")


def listar_precios_texto() -> str:
    df = cargar_precios()
    lineas = ["Precios mayoristas por unidad, IVA incluido (A: 12-47 u · B: 48+ u):"]
    categoria = None
    for i, fila in enumerate(df.itertuples(), start=1):
        if fila.categoria != categoria:
            categoria = fila.categoria
            lineas.append(f"\n{categoria.upper()}")
        lineas.append(f"{i}. {fila.producto} — A {fmt(fila.precio_a)} · B {fmt(fila.precio_b)}")
    return "\n".join(lineas)


def actualizar_precio(producto: str, nivel: str, precio_con_iva: float) -> str:
    df = cargar_precios()
    nivel = nivel.strip().upper()
    if nivel not in ("A", "B"):
        return "El nivel debe ser A o B."
    coincidencias = [i for i, p in enumerate(df["producto"]) if _normalizar(producto) in _normalizar(p)]
    if len(coincidencias) != 1:
        opciones = ", ".join(df["producto"])
        return f"No encontré un único producto mayorista para '{producto}'. Opciones: {opciones}"
    i = coincidencias[0]
    columna = "precio_a" if nivel == "A" else "precio_b"
    anterior = int(df.at[i, columna])
    df.at[i, columna] = int(round(precio_con_iva))
    df.to_csv(PRECIOS_MAYORISTA_PATH, index=False)
    return (f"{df.at[i, 'producto']} nivel {nivel}: {fmt(anterior)} → {fmt(precio_con_iva)} con IVA "
            f"(neto {fmt(neto(precio_con_iva))}).")


# --- PDF ----------------------------------------------------------------------

def _doc(ruta: Path, titulo: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(str(ruta), pagesize=letter, leftMargin=22 * mm, rightMargin=22 * mm,
                             topMargin=12 * mm, bottomMargin=12 * mm, title=titulo, author="Panadería Artesanal Malatesta")


def _encabezado(titulo: str, subtitulo: str) -> list:
    partes = []
    if LOGO_PATH.exists():
        ancho = 46 * mm
        img = Image(str(LOGO_PATH))
        partes.append(Image(str(LOGO_PATH), width=ancho, height=ancho * img.imageHeight / img.imageWidth))
        partes.append(Spacer(1, 3))
    partes += [Paragraph(titulo, _ST_TITULO), Spacer(1, 2), Paragraph(subtitulo, _ST_SUB), Spacer(1, 8)]
    return partes


def _caja_condiciones(extra: list[str] | None = None) -> Table:
    filas = [[Paragraph("CONDICIONES DE VENTA", _ST_COND_TIT)]]
    filas += [[Paragraph("• " + c, _ST_COND)] for c in CONDICIONES + (extra or [])]
    caja = Table(filas, colWidths=[ANCHO_UTIL])
    caja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CREMA), ("BOX", (0, 0), (-1, -1), 0.6, CREMA2),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
    ]))
    return caja


def _pie() -> Table:
    pie = Table([[Paragraph(PIE, _ST_PIE)]], colWidths=[ANCHO_UTIL])
    pie.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CAFE),
                             ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return pie


def generar_pdf_lista(ruta: Path | None = None) -> Path:
    """Lista de precios mayorista completa (la misma estructura del PDF que
    se reparte a las cafeterias)."""
    df = cargar_precios()
    ruta = ruta or (COTIZACIONES_DIR / "Lista_precios_mayorista_Malatesta.pdf")
    ruta.parent.mkdir(parents=True, exist_ok=True)

    data = [
        ["Producto", f"NIVEL A · {MINIMO_UNIDADES} a {UMBRAL_NIVEL_B - 1} unidades", "",
         f"NIVEL B · {UMBRAL_NIVEL_B} unidades o más", ""],
        ["", "Neto", "Con IVA", "Neto", "Con IVA"],
    ]
    estilo = [
        ("SPAN", (1, 0), (2, 0)), ("SPAN", (3, 0), (4, 0)), ("SPAN", (0, 0), (0, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), CAFE), ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9), ("FONTSIZE", (0, 1), (-1, 1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER", (2, 0), (2, -1), 0.8, TERRA),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]
    r = 2
    categoria, alterna = None, 0
    for fila in df.itertuples():
        if fila.categoria != categoria:
            categoria, alterna = fila.categoria, 0
            data.append([categoria.upper(), "", "", "", ""])
            estilo += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), CREMA2),
                       ("TEXTCOLOR", (0, r), (-1, r), TERRA), ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"),
                       ("FONTSIZE", (0, r), (-1, r), 8.5), ("ALIGN", (0, r), (-1, r), "LEFT")]
            r += 1
        nombre = f"<b>{fila.producto}</b>"
        if fila.detalle:
            nombre += f" <font color='#6B5B50' size='7.5'>({fila.detalle})</font>"
        data.append([Paragraph(nombre, _ST_NORMAL), fmt(neto(fila.precio_a)), fmt(fila.precio_a),
                     fmt(neto(fila.precio_b)), fmt(fila.precio_b)])
        estilo += [("FONTSIZE", (1, r), (-1, r), 9.5), ("TEXTCOLOR", (1, r), (-1, r), CAFE),
                   ("FONTNAME", (2, r), (2, r), "Helvetica-Bold"), ("FONTNAME", (4, r), (4, r), "Helvetica-Bold"),
                   ("LINEBELOW", (0, r), (-1, r), 0.3, CREMA2)]
        if alterna % 2 == 1:
            estilo.append(("BACKGROUND", (0, r), (-1, r), CREMA))
        alterna += 1
        r += 1

    tabla = Table(data, colWidths=[64 * mm, 27 * mm, 27 * mm, 27 * mm, 27 * mm], repeatRows=2)
    tabla.setStyle(TableStyle(estilo))

    historia = _encabezado("Lista de precios mayorista",
                           "Productos artesanales para tu cafetería · Precios por unidad, IVA incluido")
    historia += [
        tabla, Spacer(1, 4),
        Paragraph("<font size='7.5' color='#6B5B50'>Precios finales con IVA incluido. El valor neto se muestra "
                  "como referencia para la factura (IVA 19%).</font>", _ST_NORMAL),
        Spacer(1, 8),
        _caja_condiciones(["<b>Vigencia:</b> precios por unidad, revisables cada 3 meses según el costo de los insumos."]),
        Spacer(1, 8), _pie(),
    ]
    _doc(ruta, "Lista de precios mayorista – Panadería Artesanal Malatesta").build(historia)
    return ruta


# --- Cotizacion: flujo de preguntas -------------------------------------------
#
# El estado es un dict por chat (lo guarda telegram_bot.py). "preguntando" es
# la clave del paso actual; los pasos opcionales aceptan "omitir".

PASOS = ["cliente", "rut", "contacto", "productos", "descuento", "observaciones", "confirmacion"]

PREGUNTAS = {
    "cliente": "¿A qué cafetería o empresa va dirigida la cotización?",
    "rut": "¿RUT y razón social? (responde \"omitir\" si no aplica)",
    "contacto": "¿Nombre y teléfono o correo del contacto? (o \"omitir\")",
    "descuento": "¿Algún descuento adicional para este cliente? Indica el porcentaje (ej. \"5%\") o \"no\".",
    "observaciones": "¿Alguna observación para la cotización? (o \"no\")",
}

_PATRON_OMITIR = re.compile(r"^\s*(omitir|omite|no|ninguna?|nada|sin|-|0)\s*[.!]*\s*$", re.IGNORECASE)
_PATRON_NUM_X_CANT = re.compile(r"^\s*(\d+)\s*[x×*]\s*(\d+)\s*$", re.IGNORECASE)
_PATRON_SI = re.compile(r"^\s*(s[ií]|dale|ok|confirmo|correcto|genera\w*)\b", re.IGNORECASE)
_PATRON_EDITAR_PRODUCTOS = re.compile(r"producto|cambi|modific|correg", re.IGNORECASE)
_PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "y", "con", "u", "unidades", "unidad", "un", "una"}


def iniciar() -> dict:
    return {"preguntando": "cliente", "cliente": "", "rut": "", "contacto": "",
            "items": [], "descuento_pct": 0.0, "observaciones": ""}


def siguiente_pregunta(estado: dict) -> str:
    paso = estado["preguntando"]
    if paso == "productos":
        return ("¿Qué productos van en la cotización? Responde los números de la lista (ej. \"1, 4, 9\") y "
                "después te pregunto las cantidades. También puedes mandar todo junto: \"1x24, 4x12\" "
                "o \"24 facturas, 12 medialunas\".\n\n"
                + listar_precios_texto())
    if paso == "cantidades":
        df = cargar_precios()
        nombres = "\n".join(f"- {df.iloc[i]['producto']}" for i in estado["seleccion"])
        return (f"¿Cuántas unidades por despacho de cada uno?\n{nombres}\n\n"
                "Responde en el mismo orden (ej. \"24, 12, 12\"), o un solo número si es igual para todos.")
    if paso == "confirmacion":
        return formatear_resumen(estado)
    return PREGUNTAS[paso]


def _tokens(texto: str) -> set[str]:
    texto = re.sub(r"medias?\s+lunas?", "medialuna", _normalizar(texto))
    palabras = re.findall(r"[a-z]+", texto)
    # singulariza lo justo para "facturas", "berlines", "medialunas", "alfajores"
    return {re.sub(r"(es|s)$", "", p) if len(p) > 4 else p for p in palabras if p not in _PALABRAS_VACIAS}


def _buscar_producto(texto: str, df: pd.DataFrame) -> tuple[int | None, str | None]:
    buscados = _tokens(texto)
    if not buscados:
        return None, f"No entendí qué producto es \"{texto.strip()}\"."
    puntajes = []
    for fila in df.itertuples():
        # el nombre pesa mas que la categoria: "facturas" calza con la
        # categoria "Facturas y medialunas" pero debe ganar "Factura surtida"
        puntajes.append(2 * len(buscados & _tokens(fila.producto)) + len(buscados & _tokens(fila.categoria)))
    mejor = max(puntajes)
    candidatos = [i for i, p in enumerate(puntajes) if p == mejor]
    if mejor == 0:
        return None, f"No encontré \"{texto.strip()}\" en la lista mayorista."
    if len(candidatos) > 1:
        nombres = ", ".join(f"{i + 1}. {df.iloc[i]['producto']}" for i in candidatos)
        return None, f"\"{texto.strip()}\" puede ser varios productos: {nombres}. Indica cuál con su número."
    return candidatos[0], None


def interpretar_productos(texto: str) -> tuple[list[dict], str | None]:
    df = cargar_precios()
    trozos = [t for t in re.split(r"[,;\n]+|\s+y\s+(?=\d)", texto) if t.strip()]
    cantidades: dict[int, int] = {}
    for trozo in trozos:
        m = _PATRON_NUM_X_CANT.match(trozo)
        if m:
            indice, cantidad = int(m.group(1)) - 1, int(m.group(2))
            if not 0 <= indice < len(df):
                return [], f"El número {indice + 1} no está en la lista (va de 1 a {len(df)})."
        else:
            numeros = re.findall(r"\d+", trozo)
            if len(numeros) != 1:
                return [], (f"No entendí \"{trozo.strip()}\". Usa número x cantidad (ej. \"1x24\") "
                            "o cantidad y nombre (ej. \"24 facturas\").")
            if re.fullmatch(r"\s*\d+\s*", trozo):
                return [], (f"Al producto {numeros[0]} le falta la cantidad (ej. \"{numeros[0]}x12\").")
            cantidad = int(numeros[0])
            indice, error = _buscar_producto(re.sub(r"\d+", " ", trozo), df)
            if error:
                return [], error
        if cantidad <= 0:
            return [], f"La cantidad de \"{trozo.strip()}\" debe ser mayor a cero."
        cantidades[indice] = cantidades.get(indice, 0) + cantidad

    if not cantidades:
        return [], "No encontré productos en tu respuesta."
    return _items_validados(cantidades)


def _items_validados(cantidades: dict[int, int]) -> tuple[list[dict], str | None]:
    total = sum(cantidades.values())
    if total < MINIMO_UNIDADES:
        return [], (f"El pedido suma {total} unidades y el mínimo mayorista es {MINIMO_UNIDADES}. "
                    "Agrega más unidades.")
    return [{"indice": i, "cantidad": c} for i, c in sorted(cantidades.items())], None


# Palabras que acompañan a una seleccion de la lista sin cantidades
# ("el 1, el 4 y el 9 de la lista"): si solo quedan estas, son numeros de la lista.
_PALABRAS_SELECCION = {"el", "la", "los", "las", "y", "e", "de", "del", "lista", "numero", "numeros", "nro",
                       "n", "opcion", "opciones", "producto", "productos", "item", "items", "quiero", "solo"}


def seleccion_sin_cantidades(texto: str) -> list[int] | None:
    """Si la respuesta es solo numeros de la lista (ej. "1, 4, 9"), devuelve
    sus indices (base 0); si trae cantidades o nombres, None."""
    if re.search(r"[x×*]\s*\d", texto, re.IGNORECASE):
        return None
    numeros = re.findall(r"\d+", texto)
    palabras = re.findall(r"[a-z]+", _normalizar(texto))
    if not numeros or any(p not in _PALABRAS_SELECCION for p in palabras):
        return None
    return list(dict.fromkeys(int(n) - 1 for n in numeros))


def calcular(estado: dict) -> dict:
    df = cargar_precios()
    unidades = sum(it["cantidad"] for it in estado["items"])
    nivel = "B" if unidades >= UMBRAL_NIVEL_B else "A"
    columna = "precio_b" if nivel == "B" else "precio_a"
    lineas = []
    for it in estado["items"]:
        fila = df.iloc[it["indice"]]
        # la lista guarda precios con IVA; la cotizacion va en neto por linea
        # y el IVA se agrega una sola vez sobre el total, como en la factura
        precio = neto(int(fila[columna]))
        lineas.append({"producto": fila["producto"], "detalle": fila["detalle"], "cantidad": it["cantidad"],
                       "precio": precio, "subtotal": precio * it["cantidad"]})
    bruto = sum(l["subtotal"] for l in lineas)
    descuento = round(bruto * estado["descuento_pct"] / 100)
    total_neto = bruto - descuento
    iva = round(total_neto * IVA)
    return {"nivel": nivel, "unidades": unidades, "lineas": lineas, "bruto": bruto, "descuento": descuento,
            "neto": total_neto, "iva": iva, "total": total_neto + iva}


def aplicar_respuesta(estado: dict, texto: str) -> str | None:
    """Guarda la respuesta del paso actual y avanza. Devuelve un mensaje de
    error (y no avanza) si la respuesta no sirve."""
    paso = estado["preguntando"]
    texto = texto.strip()
    omitido = bool(_PATRON_OMITIR.match(texto))

    if paso == "cliente":
        if not texto or omitido:
            return "Necesito el nombre de la cafetería o empresa para la cotización."
        estado["cliente"] = texto
    elif paso in ("rut", "contacto", "observaciones"):
        estado[paso] = "" if omitido else texto
    elif paso == "productos":
        seleccion = seleccion_sin_cantidades(texto)
        if seleccion is not None:
            maximo = len(cargar_precios())
            fuera = [i + 1 for i in seleccion if not 0 <= i < maximo]
            if fuera:
                return f"El número {fuera[0]} no está en la lista (va de 1 a {maximo})."
            estado["seleccion"] = seleccion
            estado["preguntando"] = "cantidades"
            return None
        items, error = interpretar_productos(texto)
        if error:
            return error
        estado["items"] = items
    elif paso == "cantidades":
        numeros = [int(n) for n in re.findall(r"\d+", texto.replace(".", ""))]
        seleccion = estado["seleccion"]
        if len(numeros) == 1:
            numeros = numeros * len(seleccion)
        if len(numeros) != len(seleccion) or any(n <= 0 for n in numeros):
            return (f"Necesito {len(seleccion)} cantidades en el mismo orden (ej. "
                    f"\"{', '.join(['24', '12', '12', '6'][:len(seleccion)])}\"), o un solo número si es igual para todos.")
        items, error = _items_validados(dict(zip(seleccion, numeros)))
        if error:
            return error
        estado["items"] = items
        paso = "productos"  # sigue el flujo como si hubiera respondido el paso de productos
    elif paso == "descuento":
        if omitido:
            estado["descuento_pct"] = 0.0
        else:
            m = re.search(r"\d+(?:[.,]\d+)?", texto)
            if not m:
                return "Indica el descuento como porcentaje (ej. \"5%\") o responde \"no\"."
            pct = float(m.group(0).replace(",", "."))
            if not 0 <= pct < 50:
                return "El descuento debe estar entre 0% y 50%."
            estado["descuento_pct"] = pct

    if paso == "productos" and estado.pop("editando_productos", False):
        # vino desde "cambiar productos" en el resumen: no repetir el resto
        estado["preguntando"] = "confirmacion"
        return None
    siguiente = PASOS.index(paso) + 1
    estado["preguntando"] = PASOS[siguiente]
    return None


def volver_a_productos(estado: dict) -> None:
    estado["preguntando"] = "productos"
    estado["editando_productos"] = True


def es_si(texto: str) -> bool:
    return bool(_PATRON_SI.match(texto))


def pide_editar_productos(texto: str) -> bool:
    return bool(_PATRON_EDITAR_PRODUCTOS.search(texto))


def formatear_resumen(estado: dict) -> str:
    c = calcular(estado)
    lineas = [f"Cotización para {estado['cliente']}"]
    if estado["rut"]:
        lineas.append(f"RUT / razón social: {estado['rut']}")
    if estado["contacto"]:
        lineas.append(f"Contacto: {estado['contacto']}")
    lineas.append(f"\nNivel {c['nivel']} ({c['unidades']} unidades por despacho):")
    for l in c["lineas"]:
        lineas.append(f"- {l['cantidad']} × {l['producto']} a {fmt(l['precio'])} neto = {fmt(l['subtotal'])}")
    if c["descuento"]:
        lineas.append(f"Subtotal neto {fmt(c['bruto'])} − descuento {estado['descuento_pct']:g}% "
                      f"({fmt(c['descuento'])})")
    lineas.append(f"Neto {fmt(c['neto'])} + IVA 19% {fmt(c['iva'])} = Total {fmt(c['total'])}")
    if estado["observaciones"]:
        lineas.append(f"Observaciones: {estado['observaciones']}")
    lineas.append('\n¿Genero el PDF? Responde "sí", "cambiar productos" o "cancelar".')
    return "\n".join(lineas)


def _siguiente_numero() -> int:
    COTIZACIONES_DIR.mkdir(parents=True, exist_ok=True)
    contador = COTIZACIONES_DIR / "contador.txt"
    ultimo = int(contador.read_text().strip() or 0) if contador.exists() else 0
    # si el contador se perdiera, se sigue desde el PDF de numero mas alto,
    # para que nunca se repita un numero de cotizacion
    for pdf in COTIZACIONES_DIR.glob("Cotizacion_*.pdf"):
        m = re.match(r"Cotizacion_(\d+)_", pdf.name)
        if m:
            ultimo = max(ultimo, int(m.group(1)))
    numero = ultimo + 1
    contador.write_text(str(numero))
    return numero


def _nombre_archivo(texto: str) -> str:
    limpio = re.sub(r"[^a-z0-9]+", "_", _normalizar(texto)).strip("_")
    return limpio[:40] or "cliente"


def generar_pdf_cotizacion(estado: dict) -> Path:
    c = calcular(estado)
    numero = _siguiente_numero()
    hoy = date.today()
    ruta = COTIZACIONES_DIR / f"Cotizacion_{numero:04d}_{_nombre_archivo(estado['cliente'])}.pdf"

    # Datos del cliente
    datos = [["Cliente", estado["cliente"]]]
    if estado["rut"]:
        datos.append(["RUT / razón social", estado["rut"]])
    if estado["contacto"]:
        datos.append(["Contacto", estado["contacto"]])
    datos += [["Fecha", hoy.strftime("%d-%m-%Y")],
              ["Válida hasta", (hoy + timedelta(days=VALIDEZ_DIAS)).strftime("%d-%m-%Y")]]
    tabla_datos = Table([[Paragraph(f"<b>{k}</b>", _ST_NORMAL), Paragraph(str(v), _ST_NORMAL)] for k, v in datos],
                        colWidths=[40 * mm, ANCHO_UTIL - 40 * mm])
    tabla_datos.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CREMA2), ("BACKGROUND", (1, 0), (1, -1), CREMA),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    # Detalle
    data = [["Producto", "Cantidad", "Precio unitario\nneto", "Subtotal\nneto"]]
    for l in c["lineas"]:
        nombre = f"<b>{l['producto']}</b>"
        if l["detalle"]:
            nombre += f" <font color='#6B5B50' size='7.5'>({l['detalle']})</font>"
        data.append([Paragraph(nombre, _ST_NORMAL), str(l["cantidad"]), fmt(l["precio"]), fmt(l["subtotal"])])
    n_lineas = len(data)
    totales = []
    if c["descuento"]:
        totales += [["", "", "Subtotal neto", fmt(c["bruto"])],
                    ["", "", f"Descuento {estado['descuento_pct']:g}%", "−" + fmt(c["descuento"])]]
    totales += [["", "", "Neto", fmt(c["neto"])], ["", "", "IVA 19%", fmt(c["iva"])],
                ["", "", "TOTAL", fmt(c["total"])]]
    data += totales
    ultima = len(data) - 1
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), CAFE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("ALIGN", (2, n_lineas), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (1, 1), (-1, -1), 9.5), ("TEXTCOLOR", (1, 1), (-1, -1), CAFE),
        ("LINEBELOW", (0, 1), (-1, n_lineas - 1), 0.3, CREMA2),
        ("LINEABOVE", (2, n_lineas), (-1, n_lineas), 0.8, TERRA),
        ("BACKGROUND", (2, ultima), (-1, ultima), CAFE), ("TEXTCOLOR", (2, ultima), (-1, ultima), colors.white),
        ("FONTNAME", (2, ultima), (-1, ultima), "Helvetica-Bold"), ("FONTSIZE", (2, ultima), (-1, ultima), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for r in range(2, n_lineas, 2):
        estilo.append(("BACKGROUND", (0, r), (-1, r), CREMA))
    tabla = Table(data, colWidths=[82 * mm, 22 * mm, 34 * mm, 34 * mm])
    tabla.setStyle(TableStyle(estilo))

    nota = (f"Nivel {c['nivel']} aplicado: {c['unidades']} unidades por despacho "
            f"(nivel A: {MINIMO_UNIDADES} a {UMBRAL_NIVEL_B - 1} u; nivel B: {UMBRAL_NIVEL_B} u o más).")
    historia = _encabezado(f"Cotización N° {numero:04d}", "Precios mayoristas")
    historia += [tabla_datos, Spacer(1, 10), tabla, Spacer(1, 4),
                 Paragraph(f"<font size='7.5' color='#6B5B50'>{nota}</font>", _ST_NORMAL)]
    if estado["observaciones"]:
        historia += [Spacer(1, 6), Paragraph(f"<b>Observaciones:</b> {estado['observaciones']}", _ST_COND)]
    historia += [Spacer(1, 10),
                 _caja_condiciones([f"<b>Validez:</b> esta cotización es válida por {VALIDEZ_DIAS} días."]),
                 Spacer(1, 8), _pie()]
    _doc(ruta, f"Cotización {numero:04d} – Panadería Artesanal Malatesta").build(historia)
    return ruta


# --- Agregar / quitar productos de la venta mayorista -------------------------
#
# Las recetas del bot estan por lote (batch); la venta mayorista es por
# unidad. Cada producto de la lista queda enlazado a su receta
# (receta_producto + receta_variante) para mostrar el costo unitario al
# fijarle precio. Un producto "surtido" enlaza varias variantes separadas por
# "|" (ej. Factura: Membrillo|Pastelera|Manjar) y su costo es el promedio.

def _costo_unitario(receta_producto: str, receta_variante: str) -> float | None:
    from . import tools as t
    variantes = [v for v in receta_variante.split("|") if v] or [""]
    try:
        costos = [t.costo_unitario_producto(receta_producto, v) for v in variantes]
    except Exception:  # noqa: BLE001 -- receta borrada o mal enlazada
        return None
    costos = [c for c in costos if c]
    return sum(costos) / len(costos) if costos else None


def _precio_mostrador(receta_producto: str, receta_variante: str) -> float | None:
    from . import tools as t
    catalogo = t._load_catalogo()
    variantes = {t._normalizar(v) for v in receta_variante.split("|")}
    filas = catalogo[(catalogo["producto"].map(t._normalizar) == t._normalizar(receta_producto))
                     & (catalogo["variante"].map(t._normalizar).isin(variantes))]
    precios = pd.to_numeric(filas["precio_venta"], errors="coerce").dropna()
    return float(precios.mean()) if len(precios) else None


def _redondear(precio: float, a: int = 50) -> int:
    return int(round(precio / a) * a)


def iniciar_agregar() -> dict:
    return {"modo": "agregar", "preguntando": "agregar_buscar", "opciones": [], "receta_producto": "",
            "variantes": [], "nombre": "", "detalle": "", "categoria": "", "precio_a": 0, "precio_b": 0}


def iniciar_quitar() -> dict:
    return {"modo": "quitar", "preguntando": "quitar_elegir", "indices": []}


def _referencia_precios(estado: dict) -> str:
    costo = _costo_unitario(estado["receta_producto"], "|".join(estado["variantes"]))
    mostrador = _precio_mostrador(estado["receta_producto"], "|".join(estado["variantes"]))
    estado["costo"] = costo
    lineas = []
    if costo:
        piso = _redondear(costo * 2 * (1 + IVA))
        lineas.append(f"Costo unitario de fabricación: {fmt(costo)}. Para venderlo al menos al doble del "
                      f"costo, el precio con IVA debe ser {fmt(piso)} o más.")
    else:
        lineas.append("Ojo: no pude calcular el costo unitario de esta receta.")
    if mostrador:
        lineas.append(f"Precio de mostrador: {fmt(mostrador)}. Referencia nivel A (−20%): "
                      f"{fmt(_redondear(mostrador * 0.8))} · nivel B (−28%): {fmt(_redondear(mostrador * 0.72))}.")
    return "\n".join(lineas)


def siguiente_pregunta_gestion(estado: dict) -> str:
    paso = estado["preguntando"]
    if paso == "agregar_buscar":
        return "¿Qué producto del recetario quieres vender al por mayor? (ej. \"berlín manjar\", \"medialuna pistacho\")"
    if paso == "agregar_elegir":
        opciones = "\n".join(f"{i}. {o}" for i, o in enumerate(estado["opciones_texto"], start=1))
        return (f"Encontré varias recetas:\n{opciones}\n\nResponde el número. Si se vende surtido, "
                "indica varios números separados por coma (ej. \"1, 2, 3\").")
    if paso == "agregar_nombre":
        return f"¿Con qué nombre aparece en la lista? Responde \"ok\" para usar \"{estado['nombre']}\"."
    if paso == "agregar_categoria":
        categorias = list(dict.fromkeys(cargar_precios()["categoria"]))
        estado["categorias"] = categorias
        opciones = "\n".join(f"{i}. {c}" for i, c in enumerate(categorias, start=1))
        return f"¿En qué categoría de la lista va?\n{opciones}\n\nResponde el número o escribe una categoría nueva."
    if paso == "agregar_precio_a":
        return (_referencia_precios(estado) + "\n\n¿A cuánto se vende la unidad en NIVEL A "
                f"({MINIMO_UNIDADES} a {UMBRAL_NIVEL_B - 1} u), con IVA incluido?")
    if paso == "agregar_precio_b":
        return f"¿Y la unidad en NIVEL B ({UMBRAL_NIVEL_B} u o más), con IVA incluido?"
    if paso == "agregar_confirmacion":
        return formatear_resumen_agregar(estado)
    if paso == "quitar_elegir":
        return ("¿Qué producto quieres quitar de la venta mayorista? Responde el número "
                "(o varios separados por coma).\n\n" + listar_precios_texto())
    if paso == "quitar_confirmacion":
        df = cargar_precios()
        nombres = "\n".join(f"- {df.iloc[i]['producto']}" for i in estado["indices"])
        return (f"Voy a quitar de la lista mayorista:\n{nombres}\n\nLa receta no se borra, solo deja de "
                "venderse al por mayor. ¿Confirmas? (sí / cancelar)")
    raise ValueError(paso)


def _ganancia(precio_con_iva: int, costo: float | None) -> str:
    if not costo:
        return ""
    precio_neto = neto(precio_con_iva)
    ganancia = precio_neto - costo
    alerta = " ⚠️ bajo 2× el costo" if precio_neto < 2 * costo else ""
    return f" → ganancia {fmt(ganancia)} por unidad ({ganancia / precio_neto:.0%} del neto){alerta}"


def formatear_resumen_agregar(estado: dict) -> str:
    costo = estado.get("costo")
    detalle = f" ({estado['detalle']})" if estado["detalle"] else ""
    return (f"Producto mayorista nuevo:\n"
            f"{estado['nombre']}{detalle} — categoría {estado['categoria']}\n"
            f"Nivel A: {fmt(estado['precio_a'])} con IVA (neto {fmt(neto(estado['precio_a']))})"
            f"{_ganancia(estado['precio_a'], costo)}\n"
            f"Nivel B: {fmt(estado['precio_b'])} con IVA (neto {fmt(neto(estado['precio_b']))})"
            f"{_ganancia(estado['precio_b'], costo)}\n\n"
            "¿Lo agrego? (sí / cancelar)")


def _leer_numeros(texto: str, maximo: int) -> tuple[list[int], str | None]:
    numeros = [int(n) for n in re.findall(r"\d+", texto)]
    if not numeros:
        return [], "Responde con el número de la lista."
    fuera = [n for n in numeros if not 1 <= n <= maximo]
    if fuera:
        return [], f"El número {fuera[0]} no está en la lista (va de 1 a {maximo})."
    return list(dict.fromkeys(n - 1 for n in numeros)), None


def _leer_precio(texto: str) -> int | None:
    limpio = texto.replace("$", "").replace(".", "").replace(" ", "")
    m = re.search(r"\d+", limpio)
    return int(m.group(0)) if m else None


def _elegir_receta(estado: dict, filas: pd.DataFrame) -> str | None:
    """Fija la receta (o recetas, si es surtido) del producto nuevo y propone
    nombre/detalle. Devuelve error si ya esta en la lista mayorista."""
    from . import tools as t
    variantes = list(filas["variante"])
    estado["receta_producto"] = filas.iloc[0]["producto"]
    estado["variantes"] = variantes
    legibles = [t._legible(v).lower() for v in variantes if v]
    if len(variantes) > 1:
        estado["nombre"] = f"{t._legible(estado['receta_producto'])} surtido"
        estado["detalle"] = ", ".join(legibles[:-1]) + " y " + legibles[-1]
    else:
        estado["nombre"] = " ".join([t._legible(estado["receta_producto"])] + legibles)
        estado["detalle"] = ""

    clave = (t._normalizar(estado["receta_producto"]), {t._normalizar(v) for v in variantes})
    for fila in cargar_precios().itertuples():
        if (t._normalizar(fila.receta_producto), {t._normalizar(v) for v in fila.receta_variante.split("|")}) == clave:
            return (f"\"{fila.producto}\" ya está en la lista mayorista (A {fmt(fila.precio_a)} · "
                    f"B {fmt(fila.precio_b)}). Para cambiarle el precio pídelo así: "
                    f"\"cambia el precio mayorista A de {fila.producto} a 1200\".")
    return None


_OTRO_PRODUCTO = '\n\nIndica otro producto del recetario o escribe "cancelar".'


def aplicar_respuesta_gestion(estado: dict, texto: str) -> str | None:
    """Aplica la respuesta al paso actual de agregar/quitar. Devuelve un
    mensaje de error (sin avanzar) si la respuesta no sirve."""
    from . import tools as t
    paso = estado["preguntando"]
    texto = texto.strip()

    if paso == "agregar_buscar":
        catalogo = t._load_catalogo()
        filas = t._buscar_filas(catalogo, texto)
        if filas.empty:
            parecidos = t._alternativas_fuzzy(catalogo, texto)
            sugerencia = ""
            if parecidos:
                sugerencia = " ¿Quizás: " + ", ".join(f"{f.producto} {t._legible(f.variante)}".strip()
                                                     for f in parecidos) + "?"
            return f"No encontré \"{texto}\" en el recetario.{sugerencia}"
        if len(filas) == 1:
            error = _elegir_receta(estado, filas)
            if error:
                return error + _OTRO_PRODUCTO
            estado["preguntando"] = "agregar_nombre"
            return None
        estado["opciones"] = [(f.producto, f.variante) for f in filas.itertuples()]
        estado["opciones_texto"] = [f"{f.producto} {t._legible(f.variante)}".strip() for f in filas.itertuples()]
        estado["preguntando"] = "agregar_elegir"
        return None

    if paso == "agregar_elegir":
        indices, error = _leer_numeros(texto, len(estado["opciones"]))
        if error:
            return error
        elegidas = [estado["opciones"][i] for i in indices]
        if len({t._normalizar(p) for p, _ in elegidas}) > 1:
            return "Un producto surtido debe ser del mismo producto (ej. varias facturas). Elige de nuevo."
        error = _elegir_receta(estado, pd.DataFrame(elegidas, columns=["producto", "variante"]))
        if error:
            estado["preguntando"] = "agregar_buscar"
            return error + _OTRO_PRODUCTO
        estado["preguntando"] = "agregar_nombre"
        return None

    if paso == "agregar_nombre":
        if not re.match(r"^\s*(ok|s[ií]|dale|est[aá] bien)\s*[.!]*\s*$", texto, re.IGNORECASE):
            estado["nombre"] = texto
        if any(_normalizar(p) == _normalizar(estado["nombre"]) for p in cargar_precios()["producto"]):
            return f"Ya hay un producto llamado \"{estado['nombre']}\" en la lista. Escribe otro nombre."
        estado["preguntando"] = "agregar_categoria"
        return None

    if paso == "agregar_categoria":
        categorias = estado.get("categorias", [])
        if re.fullmatch(r"\d+", texto):
            n = int(texto)
            if not 1 <= n <= len(categorias):
                return f"El número {n} no está en la lista de categorías."
            estado["categoria"] = categorias[n - 1]
        else:
            existente = [c for c in categorias if _normalizar(c) == _normalizar(texto)]
            estado["categoria"] = existente[0] if existente else texto[:1].upper() + texto[1:]
        estado["preguntando"] = "agregar_precio_a"
        return None

    if paso in ("agregar_precio_a", "agregar_precio_b"):
        precio = _leer_precio(texto)
        if not precio or precio < 100:
            return "Indica el precio por unidad con IVA, en pesos (ej. \"1200\")."
        if paso == "agregar_precio_a":
            estado["precio_a"] = precio
            estado["preguntando"] = "agregar_precio_b"
        else:
            if precio > estado["precio_a"]:
                return (f"El nivel B es por volumen, no debería ser más caro que el A ({fmt(estado['precio_a'])}). "
                        "Indica el precio B de nuevo.")
            estado["precio_b"] = precio
            estado["preguntando"] = "agregar_confirmacion"
        return None

    if paso == "quitar_elegir":
        indices, error = _leer_numeros(texto, len(cargar_precios()))
        if error:
            return error
        estado["indices"] = indices
        estado["preguntando"] = "quitar_confirmacion"
        return None

    raise ValueError(paso)


def guardar_gestion(estado: dict) -> str:
    df = cargar_precios()
    if estado["modo"] == "quitar":
        nombres = ", ".join(df.iloc[i]["producto"] for i in estado["indices"])
        df = df.drop(df.index[estado["indices"]])
        df.to_csv(PRECIOS_MAYORISTA_PATH, index=False)
        return f"Listo, quité de la venta mayorista: {nombres}."

    nueva = {"categoria": estado["categoria"], "producto": estado["nombre"], "detalle": estado["detalle"],
             "receta_producto": estado["receta_producto"], "receta_variante": "|".join(estado["variantes"]),
             "precio_a": estado["precio_a"], "precio_b": estado["precio_b"]}
    # queda junto a los de su categoria (o al final si la categoria es nueva)
    misma = [i for i, c in enumerate(df["categoria"]) if c == estado["categoria"]]
    posicion = misma[-1] + 1 if misma else len(df)
    df = pd.concat([df.iloc[:posicion], pd.DataFrame([nueva]), df.iloc[posicion:]], ignore_index=True)
    df.to_csv(PRECIOS_MAYORISTA_PATH, index=False)
    return (f"Listo, agregué \"{estado['nombre']}\" a la venta mayorista "
            f"(A {fmt(estado['precio_a'])} · B {fmt(estado['precio_b'])} con IVA).")
