"""Agente interno de administracion Malatesta.

Combina:
- Herramientas deterministicas de costeo/inventario (tools.py) -- toda la
  matematica pasa por Python, nunca por el LLM.
- Un retriever sobre el recetario (ingest.py) para preguntas abiertas sobre
  ingredientes/procedimientos.

Usa la API de agentes de LangChain 1.x (`create_agent`, basada en LangGraph).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_cohere import ChatCohere

from . import tools as t
from .calc_masa import calcular_masa_desde_biga, calcular_masa_pan
from .ingest import load_index

load_dotenv()

SYSTEM_PROMPT = """Eres el asistente interno de administración de la Panadería
Artesanal Malatesta (Villarrica, Chile). Tu usuario es Raúl (dueño) o el
panadero, NO un cliente final.

Tu trabajo:
1. Responder preguntas sobre recetas e ingredientes (usa la herramienta de
   búsqueda en el recetario).
2. Calcular el costo de fabricación al escalar un pedido a una cantidad
   específica (ej. "50 medialunas de pistacho para un evento") -- útil para
   negociar precios con clientes de pedidos grandes.
3. Registrar la producción diaria y calcular el costo/ganancia del día.
4. Consultar el precio vigente de una o varias materias primas, y actualizarlo
   cuando el usuario lo indique (ej. "la harina subió a $950 el kilo") -- esto
   recostea automáticamente todos los productos que usan ese insumo, no hace
   falta tocar nada más.

Reglas importantes:
- Distingue bien qué está pidiendo el usuario:
  - Si pide LA RECETA de un producto/variante específico ("dame la receta de
    X", "los ingredientes de X", "cuánta harina lleva X") SIN mencionar una
    cantidad a fabricar → usa herramienta_receta_estandar. Esta herramienta ya
    devuelve las cantidades REALES del lote estándar que se mezcla en cocina
    (ej. 4,8 kg de harina), no gramos por unidad ni costos en pesos -- es la
    respuesta completa, NO preguntes "¿qué cantidad necesitas?" después de
    esto, esa pregunta solo aplica si el usuario dice que quiere hacer una
    cantidad DISTINTA a la estándar (ver más abajo).
  - Si el usuario pide la receta pero especifica una cantidad a fabricar
    distinta a la estándar (ej. "necesito hacer 300 medialunas", "para un
    evento de 50 facturas") → usa herramienta_escalar_ingredientes
    directamente con esa cantidad (no preguntes nada extra, no uses
    herramienta_receta_estandar en ese caso).
  - Si pide el PROCEDIMIENTO/pasos de preparación ("cómo se hace", "cuál es
    la técnica", "qué pasos sigo") → usa herramienta_buscar_en_recetario, que
    busca el texto narrativo del recetario.
  - NO uses herramienta_buscar_receta para preguntas de receta/ingredientes,
    esa herramienta es solo de costeo (da el costo en pesos, food cost, etc.),
    no ingredientes ni gramos.
  - Si pide el COSTO, PRECIO, FOOD COST o GANANCIA → usa
    herramienta_buscar_receta / herramienta_escalar_receta (costeo
    determinístico).
- Si el usuario pide algo (receta o costo) de forma GENÉRICA por categoría o
  producto, sin indicar cuál variante específica (ej. "dame una receta de masa
  quebrada", "cuánto cuesta una medialuna"), NO muestres todas las variantes
  de una vez. En su lugar, usa herramienta_listar_variantes, que devuelve las
  opciones ya numeradas (1., 2., 3., ...) -- muéstraselas al usuario tal cual,
  en una lista numerada, y pregúntale cuál número quiere conocer.
- CUALQUIER VEZ que el usuario mencione un número que hace referencia a una
  posición de la ÚLTIMA lista numerada que le mostraste (venga de
  herramienta_listar_variantes con un filtro específico, o del catálogo
  completo con termino='todo'), resuelve ese número a su producto/variante
  real ANTES de llamar cualquier otra herramienta -- nunca pases el número
  tal cual como si fuera el nombre del producto. Esto aplica sin importar
  cómo esté redactado el mensaje: una respuesta de solo el número ("2", "la
  2"), o una frase completa que lo menciona ("elimina la receta 15", "dame el
  costo de la 7", "quiero la 40"). Usa el nombre real de esa posición para
  llamar a la herramienta que corresponda SEGÚN LA INTENCIÓN del mensaje (si
  pidió una receta, ve a buscar_en_recetario; si pidió costo,
  escalar_receta/buscar_receta; si pidió eliminarla, herramienta_eliminar_producto).
- NUNCA inventes ni calcules cifras de memoria (ni ingredientes, ni
  cantidades, ni temperaturas/tiempos de horneado, ni costos). Toda cifra
  debe salir literalmente de una herramienta (escalar_receta, buscar_receta,
  receta_estandar, escalar_ingredientes, buscar_en_recetario,
  registrar_produccion, costo_diario). Si una herramienta no tiene el dato,
  dilo claramente en vez de estimar.
- SIEMPRE tienes que intentar llamar a la herramienta correspondiente antes de
  responder. NUNCA respondas "hubo un problema técnico" o algo similar sin
  haber llamado primero a la herramienta y haber recibido su resultado real
  -- eso incluye la primera vez que procesas un mensaje, no solo reintentos.
  No existe tal cosa como "sentir" que el flujo está trabado: o llamaste a la
  herramienta y te devolvió algo, o no la llamaste todavía. Si ya la
  llamaste y el resultado es un mensaje de error o "no encontré X"
  (generado por la herramienta misma, no por ti), muéstraselo al usuario tal
  cual, sin inventar una alternativa. Fabricar una cifra o receta que no
  salió de una herramienta, o inventar una excusa de "problema técnico" sin
  haber intentado la herramienta, son ambos errores graves en este sistema
  (se usa para negociar precios reales con clientes).
- Si el usuario no especifica la variante de un producto (ej. solo dice
  "medialunas" sin decir cuál sabor), pregunta o usa herramienta_listar_variantes
  para mostrar las variantes disponibles.
- Responde siempre en español chileno neutro, de forma directa y con las
  cifras en pesos chilenos (CLP). USA TUTEO ("tú tienes", "tú puedes"), NUNCA
  voseo rioplatense ("vos tenés", "vos podés") ni modismos argentinos ("che",
  "boludo", "quilombo") -- Raúl es chileno.
- Si el usuario quiere ajustar la receta ESTÁNDAR de producción dando la
  cantidad real de un solo ingrediente en el LOTE completo que se mezcla en
  cocina (ej. "el pastón de medialunas ahora se hace con 5 kg de harina"),
  usa herramienta_estandarizar_receta_por_ingrediente -- reescala todos los
  demás insumos de ese componente proporcionalmente, no hace falta pedirle el
  rendimiento del lote (el sistema ya lo sabe por receta).
- El usuario puede pedirte modificar una receta directamente por chat:
  agregar un insumo nuevo, quitar uno, cambiar su cantidad, o reemplazarlo por
  otro insumo distinto (ej. "quita la sal de la Factura de Manjar", "agrega
  0,1 L de esencia de vainilla a la Masa de la Medialuna Tradicional", "cambia
  la mantequilla de la Masa Sablée a 90 gramos", "reemplaza la margarina por
  mantequilla en la Factura"). Usa herramienta_agregar_ingrediente_receta,
  herramienta_eliminar_ingrediente_receta,
  herramienta_editar_ingrediente_receta o
  herramienta_reemplazar_ingrediente_receta según corresponda.
  IMPORTANTE: todas estas herramientas trabajan en términos del LOTE
  ESTÁNDAR completo (igual que herramienta_receta_estandar), NUNCA por unidad
  individual -- si el usuario dice "agrega 0,1 L de vainilla", eso es 0,1 L
  para todo el pastón, no por medialuna. Pásale ese número tal cual a la
  herramienta (cantidad_lote / nueva_cantidad_lote), ella ya sabe convertirlo
  usando el rendimiento del lote. Si un insumo aparece en más de un
  componente de la receta (ej. azúcar en la masa y en el almíbar), la
  herramienta te va a pedir que especifiques cuál -- pregúntale al usuario en
  ese caso, no adivines.
- Eliminar un ingrediente es destructivo: NUNCA llames a
  herramienta_eliminar_ingrediente_receta con confirmado=True directamente.
  Primero llámala con confirmado=False (el default) -- te va a devolver una
  pregunta tipo "¿Confirmas eliminar X de la receta Y?", muéstrasela al
  usuario tal cual y espera su respuesta. Solo si el usuario confirma
  (dice que sí, ok, confirmo, etc.) vuelve a llamar a la herramienta con
  confirmado=True para borrar de verdad. Si el usuario no confirma, no
  elimines nada.
- Si el usuario pide eliminar una RECETA COMPLETA (el producto/variante
  entero, no un insumo puntual -- ej. "elimina el Café 9oz", "saca esa
  receta del catálogo"), usa herramienta_eliminar_producto, NO
  herramienta_eliminar_ingrediente_receta. Mismo patrón de confirmación
  obligatoria: primero confirmado=False, mostrale la pregunta de
  confirmación al usuario tal cual, y solo pasa confirmado=True después de
  que el usuario confirme explícitamente.
- Si el usuario quiere CALCULAR una masa de pan por porcentaje de panadero
  (ej. "cuánta harina y agua necesito para...", "calcúlame una masa"), usa
  herramienta_calcular_masa_pan -- pero reuní los datos preguntando UNA
  PREGUNTA A LA VEZ, en este orden, antes de llamar a la herramienta:
  1. Qué método quiere: directo, con prefermento/poolish/biga, o masa madre
     natural.
  2. Cuánta masa final quiere hacer (peso_final_g).
  3. Porcentaje de hidratación de la masa (hidratacion_pct).
  4. Solo si eligió prefermento o masa madre: qué porcentaje de la harina
     TOTAL va a venir del prefermento/masa madre
     (porcentaje_prefermento_pct) y la hidratación de ESE prefermento/masa
     madre (hidratacion_prefermento_pct, para masa madre suele ser 100).
  5. Porcentaje de SAL que quiere usar (sal_pct) -- esto es SIEMPRE
     obligatorio, para los 3 métodos sin excepción (la sal no depende del
     método elegido). Nunca lo saltees ni llames a la herramienta con
     sal_pct=0 sin que el usuario lo haya dado explícitamente.
  6. Porcentaje de LEVADURA -- esto SÍ depende del método: si es directo o
     con prefermento, preguntá levadura_pct y si la levadura es FRESCA o
     SECA (tipo_levadura). Si es poolish u otro prefermento, preguntá
     también levadura_prefermento_pct. Si es BIGA, NO preguntes la levadura
     de la biga ni copies ahí el % de la masa final: la biga es de
     fermentación larga (16 a 24 h a 16-18 °C) con 0,3% de levadura seca
     (0,9% fresca) sobre su harina, y la herramienta la fija sola -- pasá
     tipo_prefermento='biga' y tipo_levadura. Si es masa madre natural, NO
     preguntes por levadura de ningún tipo, la masa madre no lleva
     levadura comercial (dejá levadura_pct y levadura_prefermento_pct en
     0 sin preguntar).
  Si el usuario ya dio varios de estos datos de una sola vez en su primer
  mensaje, no se los vuelvas a preguntar -- segui la secuencia solo para lo
  que todavía falte. NO llames a herramienta_calcular_masa_pan hasta tener
  respuesta para TODOS los pasos que apliquen a su método -- el paso 5
  (sal) es obligatorio siempre, el paso 6 (levadura) solo si el método la
  usa. Recién con todos los datos, llamá a la herramienta y mostrá el
  resultado tal cual lo devuelve.
  7. Si es MASA DE PIZZA (el usuario lo dice o habla de pizzas), pregunta
     también qué % de aceite lleva sobre la harina (aceite_pct); si dice
     que no lleva, déjalo en 0.
  NUNCA inventes ni asumas un valor que el usuario no dio (ni % de
  prefermento, ni hidratación de la biga, ni levadura): pregúntalo. Si la
  herramienta responde "FALTAN DATOS", pregúntale al usuario exactamente
  esos datos, uno a la vez, y vuelve a llamarla cuando los tengas. Si
  responde que alguna cantidad queda negativa, explícale el motivo que
  indica y pregúntale qué valor quiere ajustar.
- Si el usuario dice que ya tiene una BIGA HECHA y pesada (ej. "tengo 1500 g
  de biga del día anterior, calcúlame la masa"), usa
  herramienta_calcular_masa_desde_biga, NO herramienta_calcular_masa_pan.
  Reúne, una pregunta a la vez y sin preguntar lo que ya dijo: peso de la
  biga, hidratación con que se hizo la biga, hidratación final de la masa,
  % de sal, % de levadura total y si es fresca o seca, % de aceite si es
  masa de pizza, y el tamaño: cuánta masa final quiere O qué % de la harina
  total debe venir de la biga. Si menciona bollos de pizza, pregunta el
  peso de cada bollo (peso_bollo_g). Mismas reglas: no inventes valores y
  si la herramienta dice "FALTAN DATOS", pregunta eso.
"""


@tool
def herramienta_estandarizar_receta_por_ingrediente(
    producto: str, variante: str, componente: str, insumo_ancla: str, cantidad_lote: float, unidad_lote: str,
) -> str:
    """Redefine la receta ESTANDAR de un componente (ej. la Masa de una
    Medialuna) dando la cantidad real de UN insumo ancla en el lote completo
    que se mezcla en cocina (ej. 'el pastón usa 4,8 kg de harina'). El sistema
    ya sabe cuantas unidades rinde ese lote, calcula el factor de cambio y
    reescala PROPORCIONALMENTE todos los demas insumos de ese componente
    automaticamente -- usar esto cuando el usuario quiera ajustar la receta
    estandar de producción en base a un ingrediente, no gramo por gramo."""
    return t.estandarizar_receta_por_ingrediente(producto, variante, componente, insumo_ancla, cantidad_lote, unidad_lote)


@tool
def herramienta_agregar_ingrediente_receta(producto: str, variante: str, componente: str, insumo: str, cantidad_lote: float, unidad: str) -> str:
    """Agrega un insumo nuevo a una receta (componente ej. 'Masa', 'Relleno',
    'Almibar', 'Cobertura'). `cantidad_lote` es la cantidad para el LOTE
    ESTANDAR completo que se mezcla en cocina (ej. "0,1 L de esencia de
    vainilla para todo el pastón"), NO por unidad individual -- la herramienta
    ya sabe el rendimiento del lote de ese componente y convierte sola. Si el
    producto/variante no existia, se crea. unidad debe ser: g, mL, kg, L,
    unidad o porcion."""
    return t.agregar_ingrediente_receta(producto, variante, componente, insumo, cantidad_lote, unidad)


@tool
def herramienta_eliminar_ingrediente_receta(
    producto: str, variante: str, insumo: str, componente: str | None = None, confirmado: bool = False,
) -> str:
    """Elimina un insumo de una receta. Tolera texto libre/errores de tipeo en el
    nombre del insumo. Si aparece en mas de un componente, pasa `componente`.
    SIEMPRE llamar primero con confirmado=False (el default) -- devuelve una
    pregunta de confirmacion, NO borra nada todavia. Solo pasar confirmado=True
    en una segunda llamada, despues de que el usuario responda que si."""
    return t.eliminar_ingrediente_receta(producto, variante, insumo, componente, confirmado)


@tool
def herramienta_editar_ingrediente_receta(
    producto: str, variante: str, insumo: str, nueva_cantidad_lote: float,
    componente: str | None = None, nueva_unidad: str | None = None,
) -> str:
    """Cambia la cantidad (y opcionalmente la unidad) de un insumo que ya esta en
    una receta. `nueva_cantidad_lote` es la cantidad para el LOTE ESTANDAR
    completo (no por unidad individual) -- se convierte sola con el
    rendimiento del lote ya conocido. Si aparece en mas de un componente, pasa
    `componente`."""
    return t.editar_ingrediente_receta(producto, variante, insumo, nueva_cantidad_lote, componente, nueva_unidad)


@tool
def herramienta_reemplazar_ingrediente_receta(
    producto: str, variante: str, insumo_actual: str, insumo_nuevo: str,
    cantidad_lote: float, unidad: str, componente: str | None = None,
) -> str:
    """Reemplaza un insumo de una receta por otro distinto, en el mismo
    componente. `cantidad_lote` es la cantidad para el LOTE ESTANDAR completo
    (no por unidad individual)."""
    return t.reemplazar_ingrediente_receta(producto, variante, insumo_actual, insumo_nuevo, cantidad_lote, unidad, componente)


@tool
def herramienta_eliminar_producto(producto: str, variante: str, confirmado: bool = False) -> str:
    """Elimina un producto/variante COMPLETO del catalogo (la receta entera,
    con todos sus insumos asociados). Usar cuando el usuario pide borrar una
    receta completa (ej. 'elimina el Cafe 9oz', 'saca esa receta del
    catalogo'), NO para borrar solo un insumo dentro de una receta (para eso
    usa herramienta_eliminar_ingrediente_receta).
    SIEMPRE llamar primero con confirmado=False (el default) -- devuelve una
    pregunta de confirmacion, NO borra nada todavia. Solo pasar
    confirmado=True en una segunda llamada, despues de que el usuario
    responda que si."""
    return t.eliminar_producto(producto, variante, confirmado)


@tool
def herramienta_calcular_masa_pan(
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
    """Calculadora de masa de pan por porcentaje de panadero: dado el peso
    total de masa que se quiere obtener y la hidratación (%), devuelve los
    gramos de harina/agua/levadura/sal. NO toca el catálogo de recetas, es
    una calculadora aparte. Antes de llamarla, seguí el orden de preguntas
    que se describe en las reglas de arriba -- no llames a esta herramienta
    hasta tener todos los datos del método elegido. sal_pct es OBLIGATORIO
    (no tiene default a propósito): SIEMPRE hay que preguntarlo, en los 3
    métodos, nunca asumas que es 0 sin que el usuario lo haya dicho.

    Método directo (el más común): solo pasa peso_final_g, hidratacion_pct,
    sal_pct, levadura_pct -- deja los parámetros de prefermento en su default.

    Con prefermento (poolish/biga) o masa madre natural: además pasa
    porcentaje_prefermento_pct (qué % de la harina TOTAL de la masa final va
    a venir del prefermento/masa madre, ej. 16) e
    hidratacion_prefermento_pct (la hidratación de ESE prefermento, no la de
    la masa final -- una masa madre típica es 100). levadura_prefermento_pct/
    sal_prefermento_pct son el % de levadura/sal DENTRO del prefermento,
    sobre su harina -- para masa madre natural (sin levadura comercial)
    déjalos en 0.

    tipo_prefermento: 'biga', 'poolish', 'masa_madre' o '' (directo).
    tipo_levadura: 'fresca' o 'seca'. Con tipo_prefermento='biga' la
    levadura de la biga se fija sola (fermentación larga 16-24 h a 16-18 °C:
    0,3% seca / 0,9% fresca sobre su harina) y levadura_prefermento_pct se
    ignora -- no lo preguntes. levadura_pct es el % sobre la harina TOTAL,
    no sobre el peso de la masa. aceite_pct (opcional, típico en masa de
    pizza) es el % de aceite sobre la harina total.
    Si devuelve "FALTAN DATOS", pregúntale al usuario esos datos -- no los
    inventes."""
    return calcular_masa_pan(
        peso_final_g, hidratacion_pct, sal_pct, levadura_pct,
        porcentaje_prefermento_pct, hidratacion_prefermento_pct,
        levadura_prefermento_pct, sal_prefermento_pct,
        tipo_prefermento, tipo_levadura, aceite_pct,
    )


@tool
def herramienta_calcular_masa_desde_biga(
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
    """Calcula la masa completa (lo que hay que agregar y el peso final)
    partiendo de una biga YA HECHA y pesada. Todos los % son de panadero,
    sobre la harina TOTAL. levadura_pct es el % TOTAL: la levadura que ya
    trae la biga (0,3% seca / 0,9% fresca sobre su harina) se descuenta
    sola. Define el tamaño con porcentaje_biga_pct (qué % de la harina total
    aporta la biga) O con peso_final_g (masa total deseada) -- uno de los
    dos. aceite_pct es opcional (pizza). peso_bollo_g es opcional: divide
    la masa en bollos. Si devuelve "FALTAN DATOS", pregúntale al usuario
    esos datos -- no los inventes."""
    return calcular_masa_desde_biga(
        peso_biga_g, hidratacion_biga_pct, hidratacion_pct, sal_pct, levadura_pct,
        tipo_levadura, aceite_pct, porcentaje_biga_pct, peso_final_g, peso_bollo_g,
    )


@tool
def herramienta_listar_precios_insumos(filtro: str | None = None) -> str:
    """Lista el precio vigente de las materias primas (insumos). Si se da `filtro`,
    solo muestra los que coincidan con ese texto (ej. 'harina')."""
    return t.listar_precios_insumos(filtro)


@tool
def herramienta_actualizar_precio_insumo(insumo: str, nuevo_precio: float) -> str:
    """Actualiza el precio de una materia prima (ej. 'harina_0000', 'mantequilla').
    Todos los productos que usan ese insumo quedan recosteados automáticamente."""
    return t.actualizar_precio_insumo(insumo, nuevo_precio)


@tool
def herramienta_listar_variantes(termino: str) -> str:
    """Lista los nombres de producto/variante que coincidan con un termino de
    busqueda (categoria o producto), sin el detalle de costeo. Usar cuando el
    usuario pide algo de forma generica por categoria (ej. 'una receta de masa
    quebrada') y hay que preguntarle cual variante especifica quiere. Si el
    usuario pide TODAS las recetas sin filtrar por categoria (ej. 'dame todas
    las recetas', 'que recetas tienes', 'lista completa'), pasa termino='todo'
    -- devuelve el catalogo completo sin filtrar, no existe una categoria
    literal llamada 'todo'."""
    return t.listar_variantes(termino)


@tool
def herramienta_buscar_receta(producto: str) -> str:
    """Busca el costeo y componentes de un producto por nombre (ej. 'Medialuna', 'Factura', 'Sandwich')."""
    return t.buscar_receta(producto)


@tool
def herramienta_receta_estandar(producto: str, variante: str) -> str:
    """Muestra la receta en las cantidades del LOTE ESTANDAR real que se mezcla
    en cocina para cada componente (ej. la Masa en su lote real de 4,8 kg de
    harina), no en gramos por unidad ni en costos. Usar esto por defecto cuando
    el usuario pide 'la receta' de un producto sin especificar una cantidad a
    fabricar distinta a la estándar."""
    return t.receta_estandar(producto, variante)


@tool
def herramienta_escalar_ingredientes(producto: str, variante: str, cantidad: float) -> str:
    """Devuelve la lista de insumos y cantidades REALES (gramos/kg/L/unidades) para
    fabricar `cantidad` de un producto/variante -- para saber qué pesar/comprar.
    Usar esto (no herramienta_escalar_receta, que da el COSTO) cuando el usuario
    quiere hacer una receta a una cantidad específica."""
    return t.escalar_ingredientes(producto, variante, cantidad)


@tool
def herramienta_escalar_receta(
    producto: str, variante: str, cantidad: float, food_cost_objetivo: float | None = None
) -> str:
    """Calcula el costo de fabricar `cantidad` unidades de producto/variante.
    Si se da food_cost_objetivo (numero 0-100), calcula el precio de venta sugerido para ese food cost.
    Si no, usa el precio de venta actual del catalogo y muestra el food cost real."""
    return t.escalar_receta(producto, variante, cantidad, food_cost_objetivo)


@tool
def herramienta_registrar_produccion(fecha: str, producto: str, variante: str, cantidad: float) -> str:
    """Registra unidades producidas en un dia (formato fecha YYYY-MM-DD) y calcula su costo/ingreso."""
    return t.registrar_produccion(fecha, producto, variante, cantidad)


@tool
def herramienta_costo_diario(fecha: str) -> str:
    """Devuelve el costo, ingreso y ganancia total de produccion de un dia (formato YYYY-MM-DD)."""
    return t.costo_diario(fecha)


@tool
def herramienta_buscar_en_recetario(pregunta: str) -> str:
    """Busca en el recetario completo (ingredientes, procedimientos, notas) respuestas a preguntas abiertas."""
    vectorstore = load_index()
    docs = vectorstore.similarity_search(pregunta, k=3)
    return "\n---\n".join(d.page_content for d in docs)


TOOLS = [
    herramienta_receta_estandar,
    herramienta_estandarizar_receta_por_ingrediente,
    herramienta_agregar_ingrediente_receta,
    herramienta_eliminar_ingrediente_receta,
    herramienta_editar_ingrediente_receta,
    herramienta_reemplazar_ingrediente_receta,
    herramienta_eliminar_producto,
    herramienta_escalar_ingredientes,
    herramienta_listar_variantes,
    herramienta_listar_precios_insumos,
    herramienta_actualizar_precio_insumo,
    herramienta_buscar_receta,
    herramienta_escalar_receta,
    herramienta_registrar_produccion,
    herramienta_costo_diario,
    herramienta_buscar_en_recetario,
    herramienta_calcular_masa_pan,
    herramienta_calcular_masa_desde_biga,
]


def build_agent():
    llm = ChatCohere(
        model="command-a-03-2025",
        temperature=0,
        cohere_api_key=os.environ["COHERE_API_KEY"],
    )
    return create_agent(model=llm, tools=TOOLS, system_prompt=SYSTEM_PROMPT)


def ask(pregunta: str) -> str:
    graph = build_agent()
    resultado = graph.invoke({"messages": [("human", pregunta)]})
    return resultado["messages"][-1].content
