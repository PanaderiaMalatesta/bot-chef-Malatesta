"""Venta mayorista a cafeterias: lista de precios en PDF y cotizaciones
guiadas por Telegram.

Igual que la importacion de recetas, la cotizacion es un flujo de preguntas
en Python (no del LLM): el bot pregunta en orden, valida cada respuesta y
todos los montos se calculan aca, para que el modelo nunca invente precios.

Los precios de data/precios_mayorista.csv son FINALES CON IVA. El neto se
obtiene dividiendo por 1,19.

Descuento por volumen (regla de Raul, oct 2026, cantidades del asesor): cada
producto tiene un solo precio y su propia cantidad "descuento_desde" (ej.
facturas 24, muffins 12 por sabor). Dos escalones sobre el total comprado DE
ESE producto: DESCUENTO_NIVEL_1 (5%) desde "descuento_desde" y
DESCUENTO_NIVEL_2 (10%) desde FACTOR_NIVEL_2 (3) veces esa cantidad. Sin
"descuento_desde" = sin descuento (ej. brownie, muffins de menor margen).
Reemplazo a los niveles A/B (por cantidad total, despues por monto) y al
10% unico desde 24 u.
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
DESCUENTO_DESDE_ANTIGUO = 24  # umbral unico previo, para CSV sin la columna
DESCUENTO_NIVEL_1 = 0.05
DESCUENTO_NIVEL_2 = 0.10
FACTOR_NIVEL_2 = 3  # el 10% parte del triple de la cantidad del 5%
VALIDEZ_DIAS = 15

TELEFONO = "+56 9 3132 6999"
PIE = (
    "<b>Panadería Artesanal Malatesta</b> · Vicente Reyes 562, Villarrica<br/>"
    f"Pedidos y consultas: <b>{TELEFONO}</b> (WhatsApp) · oficialmalatesta@gmail.com · malatestachile.cl"
)
CONDICIONES = [
    "<b>Pedido mínimo por producto</b> según la lista de precios; puedes combinar productos libremente.",
    f"<b>Descuento por volumen:</b> {DESCUENTO_NIVEL_1:.0%} al llegar a la cantidad indicada para cada "
    f"producto y {DESCUENTO_NIVEL_2:.0%} desde el triple de esa cantidad, <b>sobre el total comprado de ese "
    "producto</b>.",
    "<b>Facturas</b> siempre surtidas (membrillo, pastelera y manjar).",
    "<b>Pedidos</b> con 24 horas de anticipación.",
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
    if "precio" not in df.columns:
        # formato antiguo con niveles A/B: el precio unico es el de nivel A
        df = df.rename(columns={"precio_a": "precio"}).drop(columns=["precio_b"], errors="ignore")
    # minimo de venta por producto (en su unidad) y unidad de venta ("u" o
    # "kg", ej. galletas por kilo); los CSV antiguos no traen estas columnas
    if "minimo" not in df.columns:
        df["minimo"] = 1
    if "unidad" not in df.columns:
        df["unidad"] = "u"
    # cantidad de ESE producto desde la que parte el 5% (vacio/0 = sin descuento)
    if "descuento_desde" not in df.columns:
        df["descuento_desde"] = DESCUENTO_DESDE_ANTIGUO
    df = df.drop(columns=["descuento_pct"], errors="ignore")  # columna de una version previa
    for columna in ("detalle", "receta_producto", "receta_variante"):
        df[columna] = df[columna].fillna("").astype(str)
    df["precio"] = df["precio"].astype(int)
    # los productos por kg aceptan medios kilos (ej. minimo 0,5 kg)
    df["minimo"] = df["minimo"].fillna(1).astype(float)
    df["unidad"] = df["unidad"].fillna("u").astype(str).replace("", "u")
    df["descuento_desde"] = pd.to_numeric(df["descuento_desde"], errors="coerce").fillna(0).astype(float)
    return df


def pct_descuento(cantidad: float, desde: float) -> float:
    """Descuento que corresponde a `cantidad` de un producto cuyo primer
    escalon parte en `desde`: 0, 5% o 10% (desde el triple)."""
    if desde <= 0 or cantidad < desde:
        return 0.0
    return DESCUENTO_NIVEL_2 if cantidad >= desde * FACTOR_NIVEL_2 else DESCUENTO_NIVEL_1


def _texto_descuento(desde: float, unidad: str) -> str:
    """'desde 36' / 'desde 3 kg' / 'sin descuento'."""
    return f"desde {_cant(desde, unidad)}" if desde > 0 else "sin descuento"


def _num(valor: float) -> str:
    """12 -> '12'; 0.5 -> '0,5'."""
    return f"{valor:g}".replace(".", ",")


def _cant(cantidad: float, unidad: str) -> str:
    """'12' para unidades, '0,5 kg' para productos por kilo."""
    return f"{_num(cantidad)} {unidad}" if unidad != "u" else _num(cantidad)


def _leer_cantidad(texto: str) -> float:
    """'12' -> 12; '0,5' o '0.5' -> 0.5."""
    return float(texto.replace(",", "."))


def _buscar_unico(df: pd.DataFrame, producto: str) -> tuple[int | None, str | None]:
    coincidencias = [i for i, p in enumerate(df["producto"]) if _normalizar(producto) in _normalizar(p)]
    if len(coincidencias) != 1:
        opciones = ", ".join(df["producto"])
        return None, f"No encontré un único producto mayorista para '{producto}'. Opciones: {opciones}"
    return coincidencias[0], None


def neto(precio_con_iva: float) -> int:
    return round(precio_con_iva / (1 + IVA))


def con_descuento(precio_con_iva: int, pct: float) -> int:
    return round(precio_con_iva * (1 - pct))


def fmt(n: float) -> str:
    return "$" + f"{n:,.0f}".replace(",", ".")


def listar_precios_texto() -> str:
    df = cargar_precios()
    lineas = ["Precios mayoristas NETOS por unidad, el IVA se suma en el total (descuento por volumen desde la cantidad "
              "indicada de cada producto):"]
    categoria = None
    for i, fila in enumerate(df.itertuples(), start=1):
        if fila.categoria != categoria:
            categoria = fila.categoria
            lineas.append(f"\n{categoria.upper()}")
        lineas.append(f"{i}. {fila.producto} — {_escalones(fila.precio, fila.descuento_desde, fila.unidad)} · "
                      f"mín. {_cant(fila.minimo, fila.unidad)}")
    return "\n".join(lineas)


def neto_con_descuento(precio_con_iva: int, pct: float) -> int:
    """Neto unitario con descuento, calculado igual que en la cotizacion
    (el descuento se aplica sobre el neto)."""
    return round(neto(precio_con_iva) * (1 - pct))


def _escalones(precio: int, desde: float, unidad: str, con_precio: bool = True) -> str:
    """Precios NETOS: '$840 · −5% desde 24: $798 · −10% desde 72: $756' (o
    'sin descuento'). El IVA se agrega solo en los totales."""
    por = "/kg" if unidad == "kg" else ""
    partes = [f"{fmt(neto(precio))}{por}"] if con_precio else []
    if desde > 0:
        partes += [f"−{DESCUENTO_NIVEL_1:.0%} desde {_cant(desde, unidad)}: "
                   f"{fmt(neto_con_descuento(precio, DESCUENTO_NIVEL_1))}{por}",
                   f"−{DESCUENTO_NIVEL_2:.0%} desde {_cant(desde * FACTOR_NIVEL_2, unidad)}: "
                   f"{fmt(neto_con_descuento(precio, DESCUENTO_NIVEL_2))}{por}"]
    else:
        partes.append("sin descuento")
    return " · ".join(partes)


def actualizar_descuento(producto: str, desde: float) -> str:
    """Cantidad de ese producto desde la que parte el 5% (el 10% parte del
    triple); 0 = sin descuento."""
    df = cargar_precios()
    i, error = _buscar_unico(df, producto)
    if error:
        return error
    unidad = df.at[i, "unidad"]
    if desde < 0 or (unidad == "u" and desde != int(desde)):
        return "La cantidad debe ser 0 (sin descuento) o mayor, y entera si el producto se vende por unidad."
    precio = int(df.at[i, "precio"])
    antes = _escalones(precio, float(df.at[i, "descuento_desde"]), unidad, con_precio=False)
    df.at[i, "descuento_desde"] = float(desde)
    df.to_csv(PRECIOS_MAYORISTA_PATH, index=False)
    return f"{df.at[i, 'producto']}: {antes} → {_escalones(precio, float(desde), unidad, con_precio=False)}."


def actualizar_minimo(producto: str, minimo: float) -> str:
    df = cargar_precios()
    i, error = _buscar_unico(df, producto)
    if error:
        return error
    unidad = df.at[i, "unidad"]
    if minimo <= 0 or (unidad == "u" and minimo != int(minimo)):
        return "El mínimo debe ser mayor a cero (y entero si el producto se vende por unidad)."
    anterior = float(df.at[i, "minimo"])
    df.at[i, "minimo"] = float(minimo)
    df.to_csv(PRECIOS_MAYORISTA_PATH, index=False)
    return (f"{df.at[i, 'producto']}: mínimo {_cant(anterior, unidad)} → {_cant(float(minimo), unidad)} "
            "por pedido.")


def actualizar_precio(producto: str, precio_con_iva: float) -> str:
    df = cargar_precios()
    i, error = _buscar_unico(df, producto)
    if error:
        return error
    anterior = int(df.at[i, "precio"])
    df.at[i, "precio"] = int(round(precio_con_iva))
    df.to_csv(PRECIOS_MAYORISTA_PATH, index=False)
    dcto = _escalones(int(round(precio_con_iva)), float(df.at[i, "descuento_desde"]), df.at[i, "unidad"],
                      con_precio=False)
    return (f"{df.at[i, 'producto']}: {fmt(anterior)} → {fmt(precio_con_iva)} con IVA "
            f"(neto {fmt(neto(precio_con_iva))}; {dcto}).")


# --- PDF ----------------------------------------------------------------------

def _doc(ruta: Path, titulo: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(str(ruta), pagesize=letter, leftMargin=22 * mm, rightMargin=22 * mm,
                             topMargin=12 * mm, bottomMargin=12 * mm, title=titulo, author="Panadería Artesanal Malatesta")


def _encabezado(titulo: str, subtitulo: str, ancho_logo: float = 46 * mm) -> list:
    partes = []
    if LOGO_PATH.exists():
        ancho = ancho_logo
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


# Niveles de compactacion (padding de filas, ancho del logo) que se prueban
# en orden hasta que la lista quepa en una pagina: la lista crece con cada
# producto agregado por chat y el pie no debe saltar a una segunda hoja.
_COMPACTACION_LISTA = [(3, 34 * mm), (2, 30 * mm), (1.5, 26 * mm), (1, 22 * mm), (0.5, 18 * mm)]


def generar_pdf_lista(ruta: Path | None = None) -> Path:
    """Lista de precios mayorista completa (la misma estructura del PDF que
    se reparte a las cafeterias). Se compacta sola para caber en una pagina."""
    df = cargar_precios()
    ruta = ruta or (COTIZACIONES_DIR / "Lista_precios_mayorista_Malatesta.pdf")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    for padding, ancho_logo in _COMPACTACION_LISTA:
        doc = _doc(ruta, "Lista de precios mayorista – Panadería Artesanal Malatesta")
        doc.build(_historia_lista(df, padding, ancho_logo))
        if doc.page == 1:
            break
    return ruta


def _historia_lista(df: pd.DataFrame, padding: float, ancho_logo: float) -> list:
    data = [
        # solo precios NETOS: el IVA se agrega en el total de la cotizacion
        ["Producto", "Mín.", "PRECIO\nNETO",
         f"−{DESCUENTO_NIVEL_1:.0%} POR VOLUMEN", "", f"−{DESCUENTO_NIVEL_2:.0%} POR VOLUMEN", ""],
        ["", "", "", "Desde", "Neto", "Desde", "Neto"],
    ]
    estilo = [
        ("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1)), ("SPAN", (2, 0), (2, 1)), ("SPAN", (3, 0), (4, 0)),
        ("SPAN", (5, 0), (6, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), CAFE), ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5), ("FONTSIZE", (0, 1), (-1, 1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER", (1, 0), (1, -1), 0.4, CREMA2), ("LINEAFTER", (2, 0), (2, -1), 0.8, TERRA),
        ("LINEAFTER", (4, 0), (4, -1), 0.8, TERRA),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding), ("TOPPADDING", (0, 0), (-1, -1), padding),
    ]
    r = 2
    categoria, alterna = None, 0
    for fila in df.itertuples():
        if fila.categoria != categoria:
            categoria, alterna = fila.categoria, 0
            data.append([categoria.upper(), "", "", "", "", "", ""])
            estilo += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), CREMA2),
                       ("TEXTCOLOR", (0, r), (-1, r), TERRA), ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"),
                       ("FONTSIZE", (0, r), (-1, r), 8.5), ("ALIGN", (0, r), (-1, r), "LEFT")]
            r += 1
        nombre = f"<b>{fila.producto}</b>"
        if fila.detalle:
            nombre += f" <font color='#6B5B50' size='7.5'>({fila.detalle})</font>"
        if fila.descuento_desde > 0:
            columnas_dcto = [_cant(fila.descuento_desde, fila.unidad),
                             fmt(neto_con_descuento(fila.precio, DESCUENTO_NIVEL_1)),
                             _cant(fila.descuento_desde * FACTOR_NIVEL_2, fila.unidad),
                             fmt(neto_con_descuento(fila.precio, DESCUENTO_NIVEL_2))]
        else:
            columnas_dcto = ["—", "—", "—", "—"]
        data.append([Paragraph(nombre, _ST_NORMAL), _cant(fila.minimo, fila.unidad), fmt(neto(fila.precio)),
                     *columnas_dcto])
        estilo += [("FONTSIZE", (1, r), (-1, r), 9.5), ("TEXTCOLOR", (1, r), (-1, r), CAFE),
                   ("FONTNAME", (2, r), (2, r), "Helvetica-Bold"), ("FONTNAME", (4, r), (4, r), "Helvetica-Bold"),
                   ("FONTNAME", (6, r), (6, r), "Helvetica-Bold"),
                   ("LINEBELOW", (0, r), (-1, r), 0.3, CREMA2)]
        if alterna % 2 == 1:
            estilo.append(("BACKGROUND", (0, r), (-1, r), CREMA))
        alterna += 1
        r += 1

    tabla = Table(data, colWidths=[60 * mm, 14 * mm, 22 * mm, 16 * mm, 22 * mm, 16 * mm, 22 * mm],
                  repeatRows=2)
    tabla.setStyle(TableStyle(estilo))

    historia = _encabezado("Lista de precios mayorista",
                           "Productos artesanales para tu cafetería · Precios netos por unidad (+ IVA)",
                           ancho_logo=ancho_logo)
    historia += [
        tabla, Spacer(1, 4),
        Paragraph("<font size='7.5' color='#6B5B50'>Precios netos por unidad. El IVA (19%) se agrega sobre el "
                  "total de la cotización y la factura. El descuento aplica al total comprado de un producto "
                  "cuando el pedido llega a la cantidad de la columna «Desde»; «—»: sin descuento.</font>",
                  _ST_NORMAL),
        Spacer(1, 8),
        _caja_condiciones(["<b>Vigencia:</b> precios por unidad, revisables cada 3 meses según el costo de los insumos."]),
        Spacer(1, 8), _pie(),
    ]
    return historia


# --- Cotizacion: flujo de preguntas -------------------------------------------
#
# El estado es un dict por chat (lo guarda telegram_bot.py). "preguntando" es
# la clave del paso actual; los pasos opcionales aceptan "omitir".

# La cotizacion parte por el RUT: si el cliente ya esta guardado
# (clientes_mayoristas.csv) se ofrecen sus datos ("confirmar_cliente") y se
# salta a productos; si es nuevo se piden y se guardan al generar el PDF.
PASOS = ["rut", "cliente", "razon_social", "contacto", "productos", "descuento", "observaciones", "confirmacion"]

PREGUNTAS = {
    "rut": "¿RUT del cliente? (ej. 76.123.456-7; responde \"omitir\" si no tiene)",
    "cliente": "¿Nombre de la cafetería o empresa?",
    "razon_social": "¿Razón social? (o \"omitir\")",
    "contacto": "¿Nombre y teléfono o correo del contacto? (o \"omitir\")",
    "descuento": "¿Algún descuento adicional para este cliente? Indica el porcentaje (ej. \"5%\") o \"no\".",
    "observaciones": "¿Alguna observación para la cotización? (o \"no\")",
}

_PATRON_OMITIR = re.compile(r"^\s*(omitir|omite|no|ninguna?|nada|sin|-|0)\s*[.!]*\s*$", re.IGNORECASE)
_PATRON_NUM_X_CANT = re.compile(r"^\s*(\d+)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:kg|kilos?)?\s*$", re.IGNORECASE)
_NUMERO = r"\d+(?:\.\d+)?"
_PATRON_SI = re.compile(r"^\s*(s[ií]|dale|ok|confirmo|correcto|genera\w*)\b", re.IGNORECASE)
_PATRON_EDITAR_PRODUCTOS = re.compile(r"producto|cambi|modific|correg", re.IGNORECASE)
_PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "y", "con", "u", "unidades", "unidad", "un", "una"}


def iniciar() -> dict:
    return {"preguntando": "rut", "cliente": "", "rut": "", "razon_social": "", "contacto": "",
            "actualizando": False, "items": [], "descuento_pct": 0.0, "observaciones": ""}


# --- Clientes (memoria por RUT) -------------------------------------------------

CLIENTES_PATH = DATA_DIR / "clientes_mayoristas.csv"
_COLUMNAS_CLIENTES = ["rut", "cliente", "razon_social", "contacto", "actualizado"]
_PATRON_MANTENER = re.compile(r"^\s*(igual|mantener|mant[eé]n\w*|ok|s[ií]|el mismo|la misma)\s*[.!]*\s*$",
                              re.IGNORECASE)


def normalizar_rut(texto: str) -> tuple[str | None, str | None]:
    """'77963899-5' / '77.963.899-5' -> '77.963.899-5'. Valida el digito
    verificador (modulo 11). Devuelve (rut, error)."""
    limpio = re.sub(r"[^0-9kK]", "", texto).upper()
    if len(limpio) < 7 or not limpio[:-1].isdigit():
        return None, "No reconozco ese RUT. Escríbelo así: 76.123.456-7 (o \"omitir\")."
    cuerpo, dv = limpio[:-1], limpio[-1]
    suma, factor = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    esperado = {11: "0", 10: "K"}.get(11 - suma % 11, str(11 - suma % 11))
    if dv != esperado:
        return None, f"El RUT {texto.strip()} no es válido (el dígito verificador debería ser {esperado}). Revísalo."
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}", None


def _cargar_clientes() -> pd.DataFrame:
    if not CLIENTES_PATH.exists():
        return pd.DataFrame(columns=_COLUMNAS_CLIENTES)
    return pd.read_csv(CLIENTES_PATH, dtype=str).fillna("")


def buscar_cliente(rut: str) -> dict | None:
    df = _cargar_clientes()
    fila = df[df["rut"] == rut]
    return fila.iloc[0].to_dict() if len(fila) else None


def guardar_cliente(estado: dict) -> None:
    """Crea o actualiza el cliente por su RUT (sin RUT no se guarda)."""
    if not estado.get("rut"):
        return
    df = _cargar_clientes()
    df = df[df["rut"] != estado["rut"]]
    nuevo = {"rut": estado["rut"], "cliente": estado["cliente"], "razon_social": estado.get("razon_social", ""),
             "contacto": estado.get("contacto", ""), "actualizado": date.today().isoformat()}
    df = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
    CLIENTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLIENTES_PATH, index=False)


def _datos_cliente_texto(estado: dict) -> str:
    lineas = [f"Cliente: {estado['cliente']}", f"RUT: {estado['rut']}"]
    if estado.get("razon_social"):
        lineas.append(f"Razón social: {estado['razon_social']}")
    if estado.get("contacto"):
        lineas.append(f"Contacto: {estado['contacto']}")
    return "\n".join(lineas)


def siguiente_pregunta(estado: dict) -> str:
    paso = estado["preguntando"]
    if paso == "confirmar_cliente":
        return ("Encontré este cliente:\n" + _datos_cliente_texto(estado)
                + "\n\n¿Uso estos datos? Responde \"sí\" o \"actualizar\".")
    if paso in ("cliente", "razon_social", "contacto") and estado.get("actualizando") and estado.get(paso):
        return f"{PREGUNTAS[paso]}\n(Actual: {estado[paso]}; responde \"igual\" para mantenerlo)"
    if paso == "productos":
        return ("¿Qué productos van en la cotización? Responde los números de la lista (ej. \"1, 4, 9\") y "
                "después te pregunto las cantidades. También puedes mandar todo junto: \"1x24, 4x12\" "
                "o \"24 facturas, 12 medialunas\".\n\n"
                + listar_precios_texto())
    if paso == "cantidades":
        df = cargar_precios()
        nombres = "\n".join(f"- {df.iloc[i]['producto']} (mín. {_cant(df.iloc[i]['minimo'], df.iloc[i]['unidad'])})"
                            for i in estado["seleccion"])
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
    texto = _decimales(texto)
    trozos = [t for t in re.split(r"[,;\n]+|\s+y\s+(?=\d)", texto) if t.strip()]
    cantidades: dict[int, float] = {}
    for trozo in trozos:
        m = _PATRON_NUM_X_CANT.match(trozo)
        if m:
            indice, cantidad = int(m.group(1)) - 1, float(m.group(2))
            if not 0 <= indice < len(df):
                return [], f"El número {indice + 1} no está en la lista (va de 1 a {len(df)})."
        else:
            numeros = re.findall(_NUMERO, trozo)
            if len(numeros) != 1:
                return [], (f"No entendí \"{trozo.strip()}\". Usa número x cantidad (ej. \"1x24\") "
                            "o cantidad y nombre (ej. \"24 facturas\").")
            if re.fullmatch(r"\s*\d+\s*", trozo):
                return [], (f"Al producto {numeros[0]} le falta la cantidad (ej. \"{numeros[0]}x12\").")
            cantidad = float(numeros[0])
            indice, error = _buscar_producto(re.sub(_NUMERO, " ", trozo), df)
            if error:
                return [], error
        if cantidad <= 0:
            return [], f"La cantidad de \"{trozo.strip()}\" debe ser mayor a cero."
        cantidades[indice] = cantidades.get(indice, 0) + cantidad

    if not cantidades:
        return [], "No encontré productos en tu respuesta."
    return _items_validados(cantidades)


def _decimales(texto: str) -> str:
    """Normaliza cantidades con decimales para productos por kg: "medio kilo"
    -> "0.5 kg", "0,5" -> "0.5", "1,5 kg" -> "1.5 kg". Las comas sin un 0
    adelante siguen separando cantidades ("24,12,12")."""
    texto = re.sub(r"\bmedio\s+(kilo|kg)\b", "0.5 kg", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\bmedio\b", "0.5", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\b0,(\d)", r"0.\1", texto)
    return re.sub(r"(\d),(\d+)(?=\s*(kg|kilo))", r"\1.\2", texto, flags=re.IGNORECASE)


def _items_validados(cantidades: dict[int, float]) -> tuple[list[dict], str | None]:
    """Cada producto debe cumplir su minimo de venta (no hay minimo total).
    Los productos por unidad no aceptan cantidades con decimales."""
    df = cargar_precios()
    faltan = []
    for i, c in sorted(cantidades.items()):
        fila = df.iloc[i]
        if fila["unidad"] == "u" and c != int(c):
            faltan.append(f"- {fila['producto']}: se vende por unidad (pediste {_num(c)})")
        elif c < fila["minimo"]:
            faltan.append(f"- {fila['producto']}: se vende desde {_cant(fila['minimo'], fila['unidad'])} "
                          f"(pediste {_cant(c, fila['unidad'])})")
    if faltan:
        return [], "No se cumple el mínimo por producto:\n" + "\n".join(faltan) + "\n\nIndica las cantidades de nuevo."
    return [{"indice": i, "cantidad": int(c) if c == int(c) else c} for i, c in sorted(cantidades.items())], None


# Palabras que acompañan a una seleccion de la lista sin cantidades
# ("el 1, el 4 y el 9 de la lista"): si solo quedan estas, son numeros de la lista.
_PALABRAS_SELECCION = {"el", "la", "los", "las", "y", "e", "de", "del", "lista", "numero", "numeros", "nro",
                       "n", "opcion", "opciones", "producto", "productos", "item", "items", "quiero", "solo"}


# En la pregunta de cantidades se puede corregir la seleccion antes de
# responder: "saca los muffin", "quita el 6", "sin berlines", o volver a
# elegir con "cambiar productos".
_PATRON_SACAR = re.compile(r"\b(sac|quit|elimin|borr|remuev|descart)\w*|\bsin\b|\bmenos\b", re.IGNORECASE)
_PATRON_CAMBIAR_SELECCION = re.compile(r"\b(cambi|volv|otros?\s+productos|elegir\s+de\s+nuevo)\w*", re.IGNORECASE)


def _sacar_de_seleccion(estado: dict, texto: str) -> str | None:
    """Quita de la seleccion los productos nombrados (por numero de la lista
    o por nombre). Devuelve error si no reconoce ninguno."""
    df = cargar_precios()
    seleccion = estado["seleccion"]
    numeros = {int(n) - 1 for n in re.findall(r"\d+", texto)}
    buscados = _tokens(re.sub(r"\d+", " ", texto))
    quitar = [i for i in seleccion
              if i in numeros or buscados & _tokens(df.iloc[i]["producto"])]
    if not quitar:
        return ("No reconocí qué producto sacar. Indica su número de la lista (ej. \"quita el 6\") "
                "o su nombre (ej. \"saca los muffin\").")
    estado["seleccion"] = [i for i in seleccion if i not in quitar]
    if not estado["seleccion"]:
        estado["preguntando"] = "productos"
    return None


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
    lineas = []
    for it in estado["items"]:
        fila = df.iloc[it["indice"]]
        # descuento por volumen: al llegar a "descuento_desde" de ESTE producto,
        # 10% sobre el total comprado de ese producto
        desde = float(fila["descuento_desde"])
        con_volumen = desde > 0 and it["cantidad"] >= desde
        # la lista guarda precios con IVA; la cotizacion va en neto por linea
        # y el IVA se agrega una sola vez sobre el total, como en la factura.
        # El descuento se calcula sobre el neto de la linea, para que la
        # columna "Descuento" cuadre con precio x cantidad - descuento.
        precio = neto(int(fila["precio"]))
        bruto_linea = round(precio * it["cantidad"])
        pct = pct_descuento(it["cantidad"], desde)
        descuento_linea = round(bruto_linea * pct)
        lineas.append({"producto": fila["producto"], "detalle": fila["detalle"], "cantidad": it["cantidad"],
                       "descuento_desde": desde, "pct": pct,
                       "unidad": fila["unidad"],
                       "precio": precio, "descuento_linea": descuento_linea,
                       "subtotal": bruto_linea - descuento_linea, "con_volumen": con_volumen})

    bruto = sum(l["subtotal"] for l in lineas)
    descuento = round(bruto * estado["descuento_pct"] / 100)
    total_neto = bruto - descuento
    iva = round(total_neto * IVA)
    return {"unidades": unidades, "lineas": lineas, "bruto": bruto, "descuento": descuento,
            "neto": total_neto, "iva": iva, "total": total_neto + iva}


def aplicar_respuesta(estado: dict, texto: str) -> str | None:
    """Guarda la respuesta del paso actual y avanza. Devuelve un mensaje de
    error (y no avanza) si la respuesta no sirve."""
    paso = estado["preguntando"]
    texto = texto.strip()
    omitido = bool(_PATRON_OMITIR.match(texto))
    mantener = estado.get("actualizando") and bool(_PATRON_MANTENER.match(texto))

    if paso == "rut":
        if omitido:
            estado["rut"] = ""
        else:
            rut, error = normalizar_rut(texto)
            if error:
                return error
            estado["rut"] = rut
            guardado = buscar_cliente(rut)
            if guardado:
                for campo in ("cliente", "razon_social", "contacto"):
                    estado[campo] = guardado.get(campo, "")
                estado["preguntando"] = "confirmar_cliente"
                return None
    elif paso == "confirmar_cliente":
        if re.match(r"^\s*(actualiz|cambi|modific|corrig|no\b)", texto, re.IGNORECASE):
            estado["actualizando"] = True
            estado["preguntando"] = "cliente"
            return None
        if not es_si(texto):
            return "Responde \"sí\" para usar estos datos o \"actualizar\" para cambiarlos."
        estado["preguntando"] = "productos"
        return None
    elif paso == "cliente":
        if not mantener:
            if not texto or omitido:
                return "Necesito el nombre de la cafetería o empresa para la cotización."
            estado["cliente"] = texto
    elif paso in ("razon_social", "contacto", "observaciones"):
        if not mantener:
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
        if _PATRON_SACAR.search(texto):
            return _sacar_de_seleccion(estado, texto)
        if _PATRON_CAMBIAR_SELECCION.search(texto):
            estado["preguntando"] = "productos"
            return None
        numeros = [float(n) for n in re.findall(_NUMERO, _decimales(texto))]
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
        lineas.append(f"RUT: {estado['rut']}")
    if estado.get("razon_social"):
        lineas.append(f"Razón social: {estado['razon_social']}")
    if estado["contacto"]:
        lineas.append(f"Contacto: {estado['contacto']}")
    lineas.append("\nDetalle por despacho:")
    for l in c["lineas"]:
        marca = (f" − {l['pct']:.0%} ({fmt(l['descuento_linea'])})" if l["con_volumen"] else "")
        lineas.append(f"- {_cant(l['cantidad'], l['unidad'])} × {l['producto']} a {fmt(l['precio'])} neto{marca} "
                      f"= {fmt(l['subtotal'])}")
    # aviso cuando a un producto le falta poco (25% o menos) para el
    # siguiente escalon de descuento (5% o 10%)
    for l in c["lineas"]:
        desde = l["descuento_desde"]
        if desde <= 0:
            continue
        meta, pct_meta = ((desde, DESCUENTO_NIVEL_1) if l["cantidad"] < desde else
                          (desde * FACTOR_NIVEL_2, DESCUENTO_NIVEL_2))
        if meta * 0.75 <= l["cantidad"] < meta:
            lineas.append(f"(Con {_cant(meta - l['cantidad'], l['unidad'])} más de {l['producto']} llega a "
                          f"{_cant(meta, l['unidad'])} y lleva {pct_meta:.0%} de descuento)")
    if c["descuento"]:
        lineas.append(f"Subtotal neto {fmt(c['bruto'])}")
        lineas.append(f"− Descuento {estado['descuento_pct']:g}%: {fmt(c['descuento'])}")
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
        datos.append(["RUT", estado["rut"]])
    if estado.get("razon_social"):
        datos.append(["Razón social", estado["razon_social"]])
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
    data = [["Producto", "Cantidad", "Precio unitario\nneto", "Descuento\npor volumen",
             "Subtotal\nneto"]]
    _st_dcto = ParagraphStyle("d", parent=_ST_NORMAL, alignment=TA_CENTER, textColor=TERRA, fontSize=9, leading=10.5)
    for l in c["lineas"]:
        nombre = f"<b>{l['producto']}</b>"
        if l["detalle"]:
            nombre += f" <font color='#6B5B50' size='7.5'>({l['detalle']})</font>"
        if l["con_volumen"]:
            dcto = Paragraph(f"{l['pct']:.0%}<br/>−{fmt(l['descuento_linea'])}", _st_dcto)
        else:
            dcto = "—"
        data.append([Paragraph(nombre, _ST_NORMAL), _cant(l["cantidad"], l["unidad"]), fmt(l["precio"]), dcto,
                     fmt(l["subtotal"])])
    n_lineas = len(data)
    totales = []
    if c["descuento"]:
        totales.append(["", "", "Subtotal neto", "", fmt(c["bruto"])])
        totales.append(["", "", f"Descuento adicional {estado['descuento_pct']:g}%", "", "−" + fmt(c["descuento"])])
    totales += [["", "", "Neto", "", fmt(c["neto"])], ["", "", "IVA 19%", "", fmt(c["iva"])],
                ["", "", "TOTAL", "", fmt(c["total"])]]
    data += totales
    ultima = len(data) - 1
    estilo = [("SPAN", (2, r), (3, r)) for r in range(n_lineas, len(data))] + [
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
    tabla = Table(data, colWidths=[66 * mm, 18 * mm, 28 * mm, 28 * mm, 32 * mm])
    tabla.setStyle(TableStyle(estilo))

    nota = ("Descuento por volumen: al llegar a la cantidad indicada en la lista de precios para cada "
            "producto, se aplica su % de descuento sobre el total comprado de ese producto (ver columna "
            "Descuento).")
    historia = _encabezado(f"Cotización N° {numero:04d}", "Precios mayoristas")
    historia += [tabla_datos, Spacer(1, 10), tabla, Spacer(1, 4),
                 Paragraph(f"<font size='7.5' color='#6B5B50'>{nota}</font>", _ST_NORMAL)]
    if estado["observaciones"]:
        historia += [Spacer(1, 6), Paragraph(f"<b>Observaciones:</b> {estado['observaciones']}", _ST_COND)]
    historia += [Spacer(1, 10),
                 _caja_condiciones([f"<b>Validez:</b> esta cotización es válida por {VALIDEZ_DIAS} días."]),
                 Spacer(1, 8), _pie()]
    _doc(ruta, f"Cotización {numero:04d} – Panadería Artesanal Malatesta").build(historia)
    _registrar_cotizacion(numero, hoy, estado["cliente"], c["total"], ruta)
    guardar_cliente(estado)
    return ruta


# --- Historial de cotizaciones -------------------------------------------------

REGISTRO_PATH = COTIZACIONES_DIR / "registro.csv"
_COLUMNAS_REGISTRO = ["numero", "fecha", "cliente", "total", "archivo"]


def _registrar_cotizacion(numero: int, fecha: date, cliente: str, total: int, ruta: Path) -> None:
    fila = pd.DataFrame([[numero, fecha.strftime("%d-%m-%Y"), cliente, total, ruta.name]], columns=_COLUMNAS_REGISTRO)
    fila.to_csv(REGISTRO_PATH, mode="a", header=not REGISTRO_PATH.exists(), index=False)


def listar_cotizaciones() -> list[dict]:
    """Cotizaciones emitidas, de la mas nueva a la mas antigua. Las que no
    estan en el registro (emitidas antes de que existiera) se reconstruyen
    desde el nombre del PDF."""
    registradas: dict[int, dict] = {}
    if REGISTRO_PATH.exists():
        for fila in pd.read_csv(REGISTRO_PATH).itertuples():
            registradas[int(fila.numero)] = {"numero": int(fila.numero), "fecha": fila.fecha, "cliente": fila.cliente,
                                             "total": int(fila.total), "archivo": fila.archivo}
    if COTIZACIONES_DIR.exists():
        for pdf in COTIZACIONES_DIR.glob("Cotizacion_*.pdf"):
            m = re.match(r"Cotizacion_(\d+)_(.*)\.pdf$", pdf.name)
            if m and int(m.group(1)) not in registradas:
                registradas[int(m.group(1))] = {
                    "numero": int(m.group(1)),
                    "fecha": date.fromtimestamp(pdf.stat().st_mtime).strftime("%d-%m-%Y"),
                    "cliente": m.group(2).replace("_", " ").title(), "total": None, "archivo": pdf.name}
    return [registradas[n] for n in sorted(registradas, reverse=True)
            if (COTIZACIONES_DIR / registradas[n]["archivo"]).exists()]


def listar_cotizaciones_texto(limite: int = 20) -> str | None:
    cotizaciones = listar_cotizaciones()
    if not cotizaciones:
        return None
    lineas = [f"Cotizaciones emitidas (últimas {min(limite, len(cotizaciones))} de {len(cotizaciones)}):"]
    for c in cotizaciones[:limite]:
        total = f" · {fmt(c['total'])}" if c["total"] is not None else ""
        lineas.append(f"N° {c['numero']:04d} · {c['fecha']} · {c['cliente']}{total}")
    lineas.append('\n¿Cuál te reenvío? Responde el número (ej. "1") o "cancelar".')
    return "\n".join(lineas)


def buscar_cotizacion(texto: str) -> tuple[Path | None, str | None]:
    m = re.search(r"\d+", texto)
    if not m:
        return None, 'Responde el número de la cotización (ej. "1") o "cancelar".'
    numero = int(m.group(0))
    for c in listar_cotizaciones():
        if c["numero"] == numero:
            return COTIZACIONES_DIR / c["archivo"], None
    return None, f"No encontré la cotización N° {numero:04d}. Responde otro número o \"cancelar\"."


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
            "variantes": [], "nombre": "", "detalle": "", "categoria": "", "precio": 0}


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
        lineas.append(f"Precio de mostrador: {fmt(mostrador)}. Referencia mayorista (−20%): "
                      f"{fmt(_redondear(mostrador * 0.8))}.")
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
    if paso == "agregar_precio":
        return (_referencia_precios(estado) + "\n\n¿A cuánto se vende la unidad al por mayor, con IVA "
                "incluido?")
    if paso == "agregar_minimo":
        return "¿Cuál es el pedido mínimo de este producto, en unidades? (ej. \"6\")"
    if paso == "agregar_descuento":
        return (f"¿Desde cuántas unidades de este producto parte el descuento de {DESCUENTO_NIVEL_1:.0%}? "
                f"(el {DESCUENTO_NIVEL_2:.0%} parte del triple; ej. \"12\") o \"sin descuento\"")
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
            f"Precio: {fmt(estado['precio'])} con IVA (neto {fmt(neto(estado['precio']))})"
            f"{_ganancia(estado['precio'], costo)}\n"
            + "".join(
                f"Con −{pct:.0%} desde {cantidad:g} u: {fmt(con_descuento(estado['precio'], pct))} con IVA"
                f"{_ganancia(con_descuento(estado['precio'], pct), costo)}\n"
                for pct, cantidad in [(DESCUENTO_NIVEL_1, estado["descuento_desde"]),
                                      (DESCUENTO_NIVEL_2, estado["descuento_desde"] * FACTOR_NIVEL_2)]
                if estado.get("descuento_desde"))
            + ("" if estado.get("descuento_desde") else "Sin descuento por volumen\n")
            + f"Mínimo por pedido: {estado['minimo']} u\n\n"
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
            return (f"\"{fila.producto}\" ya está en la lista mayorista ({fmt(fila.precio)} con IVA). "
                    f"Para cambiarle el precio pídelo así: "
                    f"\"cambia el precio mayorista de {fila.producto} a 1200\".")
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
        estado["preguntando"] = "agregar_precio"
        return None

    if paso == "agregar_precio":
        precio = _leer_precio(texto)
        if not precio or precio < 100:
            return "Indica el precio por unidad con IVA, en pesos (ej. \"1200\")."
        estado["precio"] = precio
        estado["preguntando"] = "agregar_minimo"
        return None

    if paso == "agregar_minimo":
        m = re.search(r"\d+", texto)
        if not m or int(m.group(0)) < 1:
            return "Indica el mínimo como un número de unidades (ej. \"6\")."
        estado["minimo"] = int(m.group(0))
        estado["preguntando"] = "agregar_descuento"
        return None

    if paso == "agregar_descuento":
        if re.search(r"\bsin\b|^\s*no\s*$", texto, re.IGNORECASE):
            estado["descuento_desde"] = 0
        else:
            desde = re.search(r"\d+", texto)
            if not desde:
                return "Indica desde cuántas unidades parte el 5% (ej. \"24\") o \"sin descuento\"."
            estado["descuento_desde"] = int(desde.group(0))
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
             "precio": estado["precio"], "minimo": estado.get("minimo", 1), "unidad": "u",
             "descuento_desde": estado.get("descuento_desde", 0)}
    # queda junto a los de su categoria (o al final si la categoria es nueva)
    misma = [i for i, c in enumerate(df["categoria"]) if c == estado["categoria"]]
    posicion = misma[-1] + 1 if misma else len(df)
    df = pd.concat([df.iloc[:posicion], pd.DataFrame([nueva]), df.iloc[posicion:]], ignore_index=True)
    df.to_csv(PRECIOS_MAYORISTA_PATH, index=False)
    return (f"Listo, agregué \"{estado['nombre']}\" a la venta mayorista "
            f"({fmt(estado['precio'])} con IVA).")
