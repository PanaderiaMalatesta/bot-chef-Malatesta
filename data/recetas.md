# Recetario Malatesta — Panadería Artesanal

Documento de referencia interna. Cantidades por lote/receta base, según costeo validado del plan de negocios (julio 2026). Los precios de insumos vigentes están en `precios_insumos.csv`.

## Facturas clásicas argentinas

### Masa base (hojaldre) — rinde 103 facturas por lote
Ingredientes del lote: 320 g leche en polvo, 418 g azúcar, 40 g glucosa, 4,8 kg harina 0000, 2,5 L agua, 80 g sal, 100 g esencia de vainilla, ~1.327 g margarina de hoja (laminado, ratio 450 g de grasa por cada 2,8 kg de masa).
Costo total del lote: ~$14.545. Costo de masa por unidad: ~$141.

### Relleno membrillo (por factura)
20 g de dulce de membrillo por unidad. Costo: $50/unidad (membrillo a $2.500/kg).

### Relleno pastelera (por factura)
Receta de crema pastelera casera (rinde ~1.710 g, costo lote $2.336, $1,37/g): 0,05 L esencia de vainilla, 4 huevos, 300 g azúcar, 100 g maicena, 20 g harina, 120 g leche en polvo reconstituida a 1 L.
Uso por factura: 40 g → costo $55/unidad.

### Relleno manjar (por factura)
40 g de manjar por unidad. Costo: $160/unidad (manjar a $4.000/kg).

### Costo total y precio — Facturas
- Membrillo: costo $191/unidad · precio venta $1.500 · food cost 12,7%
- Pastelera: costo $196/unidad · precio venta $1.500 · food cost 13,1%
- Manjar: costo $301/unidad · precio venta $1.500 · food cost 20,1%
- Promedio surtida (1/3 de cada sabor): costo $229/unidad · food cost 15,3%

Formatos de venta: unitaria $1.500 · trío (3u) $4.000 · media docena (6u) $6.000 · docena (12u) $11.000.

## Medialunas de mantequilla

### Masa base — rinde 71 medialunas por lote (9,585 kg masa + laminado)
Mismo pastón base que facturas pero con mantequilla en vez de margarina (laminado con 500 g de mantequilla por cada 2,8 kg de masa — empaste que rinde 24 medialunas). Usa esencia de vainilla regular, igual que facturas (100 ml por lote) — ya NO lleva vainilla de Tahití.
Costo total del lote: $24.433,57 (harina $4.800, leche en polvo $2.665,60, azúcar $417,97, glucosa $80, sal $40, esencia de vainilla $150, mantequilla $16.280).
Costo de masa por unidad: ~$344.

### Almíbar de naranja (glaseado)
100 g azúcar + 100 ml agua por docena de medialunas. Costo: ~$8/unidad.

### Línea Tradicional (sin relleno)
Solo masa + almíbar. Costo total: $352/unidad. Precio venta $1.790. Food cost 19,7%.

### Línea Clásica (con relleno, precio venta $2.000 todas)
- Dulce de leche: 50 g de dulce de leche → costo total $492 → food cost 24,6%
- Membrillo: 40 g de membrillo → costo total $452 → food cost 22,6%
- Pastelera (misma receta que facturas): 40 g → costo total $406 → food cost 20,3%
- Manzana canela: 50 g de relleno → costo total $467 → food cost 23,3%
  (receta de relleno: 900 g manzana verde, 60 g mantequilla, 170 g azúcar, ~7 g canela en polvo, ~8 g maicena, ~1,5 g sal, 30 ml agua)

### Línea Especial (precio venta $2.390 todas)
- Chocotorta: relleno 40 g (20 g dulce de leche + 20 g queso crema) + baño chocolate 25 g + galleta de chocolate molida → costo total $921 → food cost 38,6%
- Nutella chocolate blanco y nueces: 40 g Nutella + 20 g chocolate blanco + 5 g nueces → costo total $804 → food cost 33,6%

### Línea Premium (precio venta $3.690)
- Pistacho: 40 g crema de pistacho (relleno interno) + 3 g pistacho picado (topping, sin cobertura adicional) → costo total $1.411 → food cost 38,2%

Nota de metodología: el food cost de esta sección se calcula como costo ÷ precio de venta (precio de mostrador tal cual, sin descontar IVA) — consistente con el resto de este documento y con el cálculo en vivo del bot. Es distinto del food cost "neto" (sin IVA) usado en el análisis de punto de equilibrio del negocio, que da un porcentaje más alto para el mismo producto.

## Sándwiches de mañana

### Baguette base (600 g) — rinde 20 baguettes/día
Receta 75% hidratación / 2% sal: 7,8 kg harina, 5,85 L agua, 156 g sal. Costo lote: $6.318. Costo por baguette: $316.

### Jamón y queso
Baguette + 50 g queso ($10.000/kg) + 50 g jamón ($10.000/kg), sin palta. Costo total $1.316. Precio venta $3.290. Food cost 40,0%.

### Pollo y palta
Baguette + 100 g pollo pechuga ($2.900/kg) + 200 g palta ($3.000/kg), sin queso. Costo total $1.206. Precio venta $3.020. Food cost 39,9%.

## Muffins
Ver la sección "Muffins" más abajo (receta base de vainilla y sus 4 variantes, costeadas en el bot).

## Café al paso (Máquina Iperautomática, insumo comprado — no receta propia)
Costo insumo promedio real por café 9oz: $845 neto. Precio venta café con leche 9oz: $2.690.

## Masas quebradas (categoría base, recetario interno en ampliación)

Las masas quebradas se caracterizan por su crocancia y capacidad de quebrarse o
desmenuzarse al morder. Sus ingredientes principales son un alto contenido de
mantequilla, azúcar y harina, con poca o nada de líquido. Estas recetas son
**masas base** — insumos para otros productos (tartas, galletas), no
necesariamente productos con precio de venta propio todavía.

### Técnica general
Existen dos métodos principales para integrar la mantequilla con la harina:
- **Sablage (arenado):** se integra la harina con la mantequilla fría hasta
  formar un arenado antes de agregar huevos/líquidos, impermeabilizando la
  harina para minimizar el desarrollo de gluten. Se usa para masas más
  quebradizas (ej. Sablée Salada).
- **Cremado (cremage):** se crema mantequilla con azúcar hasta lograr una
  textura ligera, luego se agregan los huevos formando una emulsión antes de
  incorporar la harina. Da una masa más homogénea (ej. Sablée, Sucrée).

Reglas generales: no sobremezclar ni amasar en exceso (desarrolla gluten no
deseado); estirar entre papel guitarra a 2 mm (galletas 3-5 mm); reposar en
frío (idealmente 12h a 1 día) antes de usar — esto estabiliza la masa sin
generar tenacidad. Para conservar más de 3 días, congelar (hasta 3 meses); en
refrigeración dura solo ~7 días.

### Streusel Regular — rinde 240,5 g (usar por cada 100 g del mix)
Ingredientes por 100 g: harina 0000 47,4 g, mantequilla fría 26,2 g, azúcar
26,2 g, sal 0,21 g.
Procedimiento: procesar todos los ingredientes hasta formar migas medianas
(procesadora o batidora con pala) → esparcir en bandeja y congelar 10 min →
hornear a 160°C por 10-12 min hasta dorar → enfriar y reservar. Se conserva
congelado (crudo u horneado) hasta 3 meses; para regenerar, hornear 5 min a
160°C.

### Streusel de Frutos Secos — rinde 240,5 g (por cada 100 g del mix)
Ingredientes por 100 g: harina 0000 24,95 g, fruto seco/nueces 24,95 g,
mantequilla fría 24,95 g, azúcar 24,95 g, sal 0,21 g. Mismo procedimiento que
el streusel regular.

### Masa Sablée — rinde 479 g (por cada 100 g del mix)
Ingredientes por 100 g: mantequilla a temperatura ambiente 18,37 g, azúcar
flor 14,82 g, huevo 0,17 unidad, harina 0000 43,64 g, harina de almendras
10,65 g, sal 0,21 g, pasta de vainilla 2,1 mL.
Procedimiento (cremado): cremar azúcar flor con mantequilla a velocidad media
hasta ablandar → agregar huevos (temperatura ambiente) y pasta de vainilla,
seguir cremando → bajar bordes del bowl y cremar a velocidad alta hasta
integrar → bajar a velocidad mínima y agregar de golpe los secos previamente
mezclados → mezclar solo hasta formar masa (no sobremezclar) → integrar a
mano en la mesada → estirar entre papel guitarra a 2 mm → llevar a
congelador, reposar idealmente de un día para otro → retirar papel superior
antes de usar.

### Masa Sablée de Cacao — rinde 469 g (por cada 100 g del mix)
Ingredientes por 100 g: mantequilla 18,76 g, azúcar flor 15,13 g, huevo 0,17
unidad, harina 0000 42,42 g, harina de almendras 10,87 g, sal 0,21 g, cacao en
polvo 2,13 g. Mismo procedimiento que la Sablée (sin pasta de vainilla, se
agrega el cacao con los secos).

### Masa Sablée Salada — rinde 500 g (por cada 100 g del mix)
Ingredientes por 100 g: mantequilla fría 21 g, huevo 0,19 unidad, harina 0000
47 g, harina de almendras 20 g, sal 0,4 g.
Procedimiento (sablage): mantequilla + harina + harina de almendras + sal en
la batidora con pala, mezclar a velocidad mínima hasta formar arenado →
agregar huevos e integrar a velocidad 1 hasta formar masa → integrar a mano →
estirar a 2 mm entre papel guitarra → congelar 25 min → retirar papel
superior.

**Fonzado (forrar moldes de tarta):** cortar tiras de masa fría de 2 cm x 31
cm (largo = diámetro del molde × π, menos el espesor de la masa × 2) →
colocar la tira dentro del aro rociado con spray vegetal → acomodar con los
dedos sin presionar de más → congelar 20 min → estirar el resto de la masa
para la base, colocar el molde encima, rociar un acrílico con spray vegetal y
golpear los bordes con mazo de goma para adherir → congelar 20 min más →
desmoldar, quitar plástico y repasar bordes con cuchillo → hornear a 150°C
por 18-22 min hasta dorar. Se conserva horneada en congelador hasta 3 meses
(regenerar 5 min a 160°C).

### Galletas de Queso Parmesano — rinde 37 unidades (615 g: 515 g masa Sablée Salada + 100 g queso)
Ingredientes por unidad: masa Sablée Salada (mantequilla 2,92 g, huevo 0,03
unidad, harina 0000 6,54 g, harina de almendras 2,78 g, sal 0,06 g) + queso
parmesano 2,7 g.
Procedimiento: rallar queso parmesano fino y masa Sablée Salada gruesa →
unir con las manos hasta integrar → estirar a 5 mm entre papel guitarra →
marcar con cortador circular de 5 cm → congelar → hornear a 150°C por ~15
min.

### Masa Murbe de Nuez — rinde 50 galletas (670 g, por galleta)
Ingredientes por galleta: harina 0000 6 g, azúcar flor 2 g, mantequilla fría
4 g, nueces picadas 1,4 g.
Procedimiento: integrar harina + azúcar flor + mantequilla en batidora con
pala a velocidad baja hasta arenado → agregar nueces picadas, subir
velocidad → integrar a mano → formar 2 cilindros rectangulares con ayuda de
una placa de cartón → opcional: pasar por azúcar granulada para que se
adhiera → congelar 20 min → cortar galletas de 5 mm de espesor → congelar
mínimo 3 h → hornear a 150°C por 10 min (no deben dorarse).

### Masa Sucrée — rinde 505 g (por cada 100 g del mix)
Ingredientes por 100 g: harina 0000 49,5 g, azúcar 15,84 g, mantequilla fría
21,78 g, huevo 0,21 unidad.
Procedimiento (cremado): cremar mantequilla con azúcar hasta ablandar →
agregar huevos temperatura ambiente, integrar a velocidad máxima (repetir
bajando bordes del bowl hasta integrar completo) → bajar a velocidad mínima y
agregar la harina → integrar a mano, formar cilindro → reposar en frío con
film 10 min.

### Masa Sucrée de Cacao — rinde 24 galletas (505 g, por galleta)
Ingredientes por galleta: harina 0000 9,88 g, cacao en polvo 0,54 g, azúcar
3,33 g, mantequilla fría 4,58 g, huevo 0,05 unidad.
Procedimiento: igual que la Sucrée, agregando el cacao junto con la harina →
tras el reposo, dar forma a las galletas → hornear a 150°C por ~12 min.

## Galletas (categoría base, recetario interno en ampliación — teoría, recetas pendientes)

Base técnica para toda la línea de galletas. Aún no hay recetas con gramajes
cargadas en esta categoría — esto es el conocimiento de por qué funciona cada
ingrediente, para cuando se agreguen recetas específicas.

### Harina
Se usa harina floja o de todo uso (10-11% proteína) — genera poco gluten, da
estructura suficiente para una galleta gruesa que no se expande demasiado. La
harina aporta también el almidón que gelatiniza durante el horneado, dando
firmeza a la galleta cocida. Sustituto sin gluten (si se necesita): 70%
almidón de maíz + 20% harina de arroz + 10% almidón de tapioca + 0,3% goma
xantana (imita la función del gluten; no omitir la goma xantana).

### Materia grasa — por qué mantequilla y no margarina
La mantequilla real (solo crema de leche, 80-82% grasa, 14-16% agua, punto de
fusión 28-29°C) aporta sabor, aroma, humedad, y actúa como ablandador
recubriendo la harina (limita el desarrollo de gluten → galleta crujiente
por fuera, tierna por dentro). También dispara la reacción de Maillard
(proteínas + azúcares de la mantequilla → color/sabor/aroma tostado).
Margarinas y mantecas vegetales tienen más agua (alteran el balance de la
receta) y un punto de fusión más alto (40-42°C) — producen galletas más
duras, pálidas, con sensación grasosa en boca y sin el aroma a tostado.
Sustituto vegano: 82% aceite de coco refinado + 18% agua + 1% lecitina de
soya/girasol (imita el % de agua y la función emulsionante de la
mantequilla).

### Líquidos acuosos y huevo
El agua es esencial para hidratar la harina, formar gluten y gelatinizar el
almidón — no se puede alterar el contenido de agua de una receta sin ajustar
el resto. El huevo aporta emulsión, hidratación, función ligante y (en menor
medida que en otras masas) estructura. Composición aproximada del huevo: 74%
agua, 10% grasa, 16% proteína. Sustituto de 100 g de huevo: 74 g de agua +
10 g de aceite + 16 g de harina + 1% de lecitina de soya/girasol (o
reemplazar el agua por un puré de fruta con equivalente % de agua, restando
del azúcar/harina de la receta lo que aporte ese puré).

### Azúcar
Además de endulzar, retiene humedad (higroscopía — retrasa el desarrollo de
gluten y compite por el agua con el almidón, dando una textura más suave) y
se carameliza en el horno aportando aroma/sabor/color. Sin azúcar, la galleta
sale con textura de pan (mucho gluten, miga elástica y seca). El azúcar
moreno (con melaza) es más higroscópico → galletas más húmedas, sabor a
melaza.

### Leudantes químicos
Bicarbonato de sodio y/o polvo de hornear (doble acción: reaccionan al
mezclarse y de nuevo con el calor del horno). Deben pesarse con balanza de
precisión menor a 1 g — un exceso hace la galleta demasiado esponjosa
(no deseado en galletas).

### Saborizantes y toppings
Vainilla, especias, cacao, ralladura de cítricos, sal: aportan sabor/aroma,
no son estructurales. Si son en polvo, se resta un poco de harina de la
receta para compensar (absorben humedad). Los toppings (chips de chocolate,
frutos secos) se agregan AL FINAL, después de que la masa está lista —
si se agregan antes, la batidora los tritura y altera la composición de la
masa. No tienen función estructural, se puede ajustar su cantidad libremente.

### Procedimiento general (orden de una receta de galletas)
1. **Cremado:** mantequilla + azúcar en batidora (accesorio pala/lira), ~6
   min a velocidad alta, hasta lograr una mezcla aireada y cremosa. No exceder
   el tiempo (exceso de aire = textura indeseada).
2. **Emulsión:** agregar huevos de forma gradual (y vainilla, si la receta la
   lleva) hasta que la mezcla esté homogénea, aireada, y se despegue del
   bowl.
3. **Secos:** tamizar harina + polvos de hornear/bicarbonato + cacao (si
   aplica) para evitar grumos y contaminantes. Incorporar a velocidad mínima
   solo hasta homogeneizar (segundos) — no sobremezclar.
4. **Toppings:** incorporar al final, distribuir uniformemente.
5. **Formado:** porcionar según el peso de la receta, bolear. Se puede
   congelar la masa cruda hasta 3 meses, u hornear directo.
6. **Horneado:** ~180°C (varía según receta y horno — usar termómetro interno,
   la temperatura del panel del horno rara vez coincide con la real). Dejar
   espacio entre galletas para que circule el calor.

### Qué pasa dentro del horno (ciencia del horneado)
- 28-33°C: la mantequilla se derrite, la masa se expande, el gluten deja
  escapar gas formando las grietas típicas de la superficie.
- 62°C: las proteínas del huevo coagulan, aportando estructura.
- 60-70°C: gelatinización del almidón (absorbe agua, da firmeza).
- ~130-154°C: reacción de Maillard visible (color/aroma tostado) y
  caramelización del azúcar (intensifica color/aroma/sabor).
- Al enfriar, la grasa vuelve a solidificarse y el almidón termina de dar
  firmeza — ahí la galleta está lista para despegar de la lata.

### Cookie Clásica de Chips de Chocolate — rinde 10 cookies (1.548,7 g)
Ingredientes: mantequilla a temperatura ambiente 276 g, azúcar morena 242 g,
azúcar 109 g, huevos 133 g, harina floja 570 g, sal 4,7 g, maicena 4 g,
bicarbonato 4 g, chocolate negro 70% picado 206 g.
Procedimiento: cremar mantequilla + ambos azúcares 5-7 min a velocidad alta →
incorporar huevos poco a poco hasta homogeneizar → bajar a mínimo, agregar
secos tamizados + chocolate picado, mezclar hasta masa homogénea → porcionar
esferas de 150 g → congelar mínimo 3 h → hornear a 200°C ~10 min (bordes
dorados, centro aún húmedo) → retirar, redondear con cortador circular →
enfriar completamente antes de desmoldar.

### Cookie Red Velvet — rinde 10 cookies
**Insert de queso crema** (221 g): queso crema tipo Philadelphia 176 g,
azúcar 40 g, pasta de vainilla 5 g. Cremar todo → verter en molde semiesfera
de 4 cm → congelar mínimo 4 h (se conserva congelado hasta 3 meses).
**Masa cookie** (1.350,8 g): mantequilla 241 g, azúcar 275 g, huevos 116 g,
harina floja 516 g, cacao en polvo 12 g, sal 3,6 g, maicena 3,6 g, polvos de
hornear 3,6 g, chips de chocolate blanco 180 g, colorante rojo hidrosoluble
c/n.
Procedimiento: cremar mantequilla + azúcar 6-7 min → incorporar huevos
gradualmente hasta emulsionar → bajar a mínimo, agregar secos tamizados +
chips → porcionar esferas de 130 g, insertar el relleno de queso crema
congelado dentro → congelar mínimo 3 h → hornear a 180°C ~12 min → redondear
con cortador, decorar con chips a gusto → enfriar antes de desmoldar.

### Mini Galletas de Avellanas y Chocolate — rinde 30 unidades (801 g)
Ingredientes: mantequilla 117 g, azúcar moreno 53 g, azúcar 89 g, glucosa
37 g, pasta de avellanas 30 g, huevos 55 g, harina floja 214 g, polvos de
hornear 3 g, bicarbonato 2 g, sal 3 g, avellanas tostadas picadas 99 g,
chocolate negro 56% picado 99 g.
Procedimiento: cremar mantequilla + ambos azúcares + glucosa + pasta de
avellanas ~5 min velocidad media → agregar huevo, subir a alta hasta
emulsionar → bajar a mínimo, agregar secos tamizados + chocolate + avellanas
picadas → porcionar esferas de 25 g → congelar mínimo 3 h → hornear a 180°C
7-8 min → decorar recién horneadas con avellanas partidas y praliné →
enfriar antes de desmoldar.

### Mini Galleta de Cacao — rinde 30 unidades (801 g)
Ingredientes: mantequilla 127 g, azúcar moreno 119 g, azúcar 71 g, huevos
67 g, harina floja 246 g, cacao en polvo 24 g, maicena 2 g, bicarbonato 2 g,
sal 2 g, chocolate negro 56% picado 141 g.
Procedimiento: cremar mantequilla + ambos azúcares 5-6 min velocidad media →
agregar huevo hasta homogeneizar → bajar a mínimo, agregar secos tamizados +
chocolate → porcionar esferas de 25 g → congelar mínimo 3 h → hornear a
180°C 7-8 min → decorar con chips recién horneadas → enfriar antes de
desmoldar.

### Mini Galleta de Pistacho y Limón — rinde 30 unidades (799,6 g)
Ingredientes: mantequilla 111 g, azúcar moreno 29 g, azúcar 103 g, glucosa
34 g, pasta de pistachos 34 g, zeste de limón 3 g, huevos 55 g, harina floja
224 g, matcha en polvo 4 g, polvos de hornear 7,2 g, sal 1,4 g, chocolate de
leche 40% picado 129 g, pistachos picados 65 g.
Procedimiento: cremar mantequilla + azúcares + glucosa + zeste + pasta de
pistachos 5-6 min velocidad media → agregar huevo hasta homogeneizar → bajar
a mínimo, agregar secos tamizados + chips + pistachos picados → porcionar
esferas de 25 g → congelar mínimo 3 h → hornear a 180°C 7-8 min → decorar
con pistachos verdes y praliné de pistacho recién horneadas → enfriar antes
de desmoldar.

### Galleta de Mantequilla y Almendras — rinde 30 unidades (800,4 g)
Ingredientes: mantequilla 126 g, azúcar 155 g, glucosa 38 g, pasta de
almendras 75 g, huevos 60 g, harina floja 231 g, almendras laminadas
tostadas 107 g, sal 3 g, polvos de hornear 3,4 g, bicarbonato 2 g.
Procedimiento: cremar mantequilla + azúcar + pasta de almendras + glucosa
~5 min velocidad media → agregar huevo hasta emulsionar → bajar a mínimo,
agregar secos tamizados + almendras laminadas → porcionar esferas de 25 g y
pasar por almendras laminadas → congelar mínimo 3 h → hornear a 180°C 7-8
min → enfriar antes de desmoldar.

### Galleta Streusel de Frambuesa — rinde 16 cuadrados de 5x5 cm
**Streusel de almendras** (241 g): harina floja 60 g, harina de almendras
60 g, mantequilla fría 60 g, azúcar 60 g, sal 1 g. Mezclar todo hasta formar
migas, reservar congelado.
**Masa Sablée** (500,5 g): mantequilla fría 72 g, azúcar flor 65 g, huevos
55 g, harina floja 220 g, harina de almendras 78 g, pasta de vainilla 10 g,
sal 0,5 g. Cremar azúcar flor + mantequilla → agregar huevos + vainilla,
cremar hasta integrar → agregar secos, mezclar sin amasar de más → estirar a
3 mm → congelar, reposar idealmente un día.
**Mermelada de frambuesas** (291,7 g, se usan 230 g): puré de frambuesas
144 g, azúcar 144 g, pectina NH 2,8 g, ácido cítrico 0,9 g. Calentar puré a
60°C → agregar azúcar+pectina → cocinar a 103°C → apagar, agregar ácido
cítrico → enfriar, reservar en manga.
**Montaje:** cortar la masa sablée con la base de un molde cuadrado de
20x20 cm → forrar el molde aceitado y forrado con papel → verter 230 g de
mermelada → espolvorear el streusel de manera uniforme → congelar mínimo
2 h → hornear a 160°C 20-25 min → enfriar, desmoldar, cortar cuadrados de
5x5 cm → espolvorear con azúcar flor antes de servir.

### Galleta Barrita de Nuez — rinde 10 barritas de 8x5 cm
**Relleno de nueces** (352 g): leche condensada 195 g, mantequilla 30 g,
nueces picadas 125 g, sal 2 g. Cocinar leche condensada + mantequilla hasta
dorar → agregar nueces + sal, cocinar hasta espesar.
**Streusel de nueces** (480 g): harina floja 120 g, harina de almendras
60 g, nueces 60 g, mantequilla fría 120 g, azúcar 120 g. Procesar harina +
harina de almendras + azúcar + nueces hasta polvo fino → agregar mantequilla
fría, procesar hasta migas.
**Montaje:** extender la mitad del streusel en la base de un molde cuadrado
de 22x22 cm → verter el relleno de nueces, alisar → distribuir el resto del
streusel encima → congelar mínimo 2 h → hornear a 160°C ~20 min → enfriar,
desmoldar, cortar tiras de 8x5 cm.

### Mantecados — rinde 30 unidades cada receta (cortador de 5 cm, 5 mm espesor)
Procedimiento común a las 6 variantes: procesar los secos hasta polvo fino →
agregar la grasa (manteca vegetal) y procesar hasta formar masa → integrar a
mano → estirar a 5 mm entre papel guitarra → cortar con cortador de 5 cm →
congelar 20 min → hornear a 150°C 10-12 min → enfriar completamente antes de
retirar de la bandeja.
- **Tradicional** (350 g): harina floja 134 g, harina de almendras 27 g,
  canela en polvo 1 g, azúcar flor 81 g, manteca vegetal 107 g.
- **De Maní** (350,5 g): harina floja 83 g, maní 112 g, sal 0,5 g, azúcar
  flor 84 g, manteca vegetal 71 g.
- **De Nuez** (350 g): harina floja 115 g, nueces 81 g, canela en polvo 1 g,
  azúcar flor 81 g, manteca vegetal 72 g.
- **De Sésamo** (351 g): harina floja 97 g, tahini 74 g, canela en polvo
  1 g, azúcar flor 81 g, manteca vegetal 71 g, sésamo negro 27 g.
- **De Pistacho** (351 g): harina floja 83 g, pistachos pelados 112 g,
  azúcar flor 84 g, sal 0,5 g, manteca vegetal 71 g.
- **De Chocolate y Naranja** (349 g): harina floja 95 g, harina de
  almendras 27 g, nibs de cacao 80 g, azúcar flor 80 g, zeste de naranja
  2 g, manteca vegetal 65 g.

### Florentinas — rinde 15 unidades
Ingredientes: crema de leche 35% materia grasa 100 g, azúcar 110 g, miel
70 g, 1 vaina de vainilla, flor de sal 1 g, almendras enfiladas 200 g (más
chocolate negro 56% templado para bañar, cantidad no especificada).
Procedimiento: retirar las semillas de la vaina de vainilla y agregarlas a
la crema de leche → cocinar crema + azúcar + miel a fuego medio hasta 115°C
→ agregar almendras + flor de sal, seguir cociendo hasta 118°C → porcionar
en molde semiesfera de 4 cm → congelar → desmoldar, hornear a 180°C hasta
dorar → cortar bordes con cortador de 5 cm (opcional) → bañar la mitad con
chocolate negro 56% templado.

## Brownies (categoría nueva, recetario interno en ampliación)

### Brownie — receta adaptada a 300 g de mantequilla, chocolate negro Ecuador 56% (rinde 2.816,8 g de mezcla, con glucosa)
La receta original se escaló proporcionalmente aumentando la mantequilla de 80 g
a 300 g (factor 3,75) y manteniendo la glucosa.
Ingredientes: mantequilla derretida y tibia 300 g, chocolate negro Ecuador 56%
picado o en gotas 581 g, azúcar flor tamizada 289 g, azúcar 300 g, glucosa
líquida 67,5 g, huevos a temperatura ambiente 439 g, harina floja tamizada
394 g, cacao en polvo sin azúcar 56 g, sal 6,8 g, nueces o avellanas tostadas
picadas groseramente 383 g.
Procedimiento: derretir el chocolate junto con la mantequilla → integrar
azúcar flor, azúcar y glucosa → agregar los huevos → incorporar los secos
tamizados (harina, cacao en polvo, sal) → agregar al final las nueces o
avellanas picadas.
Horneado en horno convector a 160°C, 32 a 38 minutos (revisar a los 30 min).
Punto ideal de cocción: superficie craquelada, bordes firmes, centro
ligeramente húmedo — al insertar un palillo deben salir migas húmedas, nunca
masa líquida.
Importante: dejar enfriar completamente y refrigerar de 8 a 12 horas antes de
cortar, para mejores cortes y textura.

## Croissants (categoría nueva, recetario interno en ampliación)

### Croissant Plano — receta base de laminado (rinde 12 croissants grandes)
Ingredientes de la masa: harina sin polvos de hornear (idealmente harina de
fuerza/panadera, aunque también sirve harina común) 600 g, azúcar blanca
60 g, sal 12 g, levadura fresca 20 g (la receta original pedía 10 g de
levadura instantánea; se reemplazó por fresca usando el doble de cantidad),
agua tibia 360 mL.
Mantequilla para el laminado: mantequilla sin sal a temperatura ambiente
250 g.
Para barnizar: 1 huevo + 1 cucharada (15 mL) de agua a temperatura ambiente.

Procedimiento:
**Masa:** mezclar los ingredientes secos en un bowl, hacer un hoyo y verter
los líquidos (agua tibia con la levadura fresca disuelta) → amasar 20 min a
mano o 10 min en máquina a velocidad media-baja → dejar leudar 1 hora en
lugar tibio → desinflar, aplanar ligeramente y refrigerar envuelta en film
30 min.
**Mantequilla de laminado:** envolver entre papel mantequilla formando un
sobre tipo A4 → golpear suavemente con rodillo hasta suavizar → estirar de
manera uniforme → refrigerar.
**Laminado:** estirar la masa a 1,5 veces el tamaño de la mantequilla →
colocar la mantequilla dejando 3 cm sin cubrir en la base → doblar el
tercio superior sobre la mantequilla y luego el inferior encima (3 capas) →
refrigerar 30-60 min si hace falta.
**Primer pliegue (book fold):** estirar a ~60 cm → doblar ambos extremos al
centro y luego doblar por la mitad (4 capas) → refrigerar 30 min.
**Segundo pliegue (tri-fold):** estirar en dirección perpendicular → doblar
en tres (9 capas totales) → refrigerar 30 min o toda la noche.
**Formado:** estirar la masa a 30x40 cm (5-7 mm de grosor) → cortar
triángulos de 10 cm de base × 30 cm de altura → estirar ligeramente cada
triángulo → enrollar desde la base hacia la punta, jalando la masa durante
el proceso → presionar la punta bajo el croissant.
**Fermentación y horneado:** colocar en bandeja con papel mantequilla →
dejar leudar 2 horas en lugar cálido → barnizar con la mezcla de huevo y
agua → hornear a 200°C por 25-30 minutos hasta dorar.

## Tortas (categoría nueva, recetario interno en ampliación)

### Carrot Cake — 1 torta entera (porciones aún sin definir, pendiente de prueba)
Ingredientes del bizcocho: zanahoria 175 g, aceite de maravilla 100 mL
(reemplaza el aceite de coco original), esencia de vainilla al gusto (se usa
5 mL como referencia para el costeo, ajustar si se define otra cantidad),
huevos 4 unidades, azúcar (flor de coco o azúcar de caña) 150 g, harina de
repostería 150 g, impulsor/polvo de hornear 10 g, canela 3 g, nuez moscada
1,5 g, clavo de olor 0,5 g.
Ingredientes del frosting: nata para montar 500 mL, azúcar glas con
vainilla 80 g (40 g + 40 g), queso crema o mascarpone 175 g, chocolate
blanco 100 g.

Procedimiento:
**Base de zanahoria:** triturar la zanahoria en dados junto con el aceite y
la vainilla hasta obtener un puré fino.
**Huevos y azúcar:** batir los huevos con el azúcar hasta conseguir una
mezcla aireada.
**Integrar la zanahoria:** añadir el puré a la mezcla de huevos e integrar
mezclando suavemente.
**Secos:** tamizar la harina con el impulsor y las especias. Añadir en dos
veces, mezclando con movimientos suaves y envolventes.
**Horneado:** verter la masa en un molde engrasado y hornear a 180°C
durante 25-30 minutos. Dejar enfriar completamente.

**Frosting:** semi montar la nata con 40 g de azúcar glas → mezclar el
queso crema con los otros 40 g de azúcar y el chocolate blanco fundido →
incorporar esta mezcla a la nata y terminar de montar suavemente.

**Montaje:** abrir el bizcocho, rellenar con el frosting, cerrar y decorar
al gusto.

## Muffins (recetario interno, actualizado 10-oct-2026)

Todas las recetas rinden 24 muffins. Horneado a 165 °C por 26 minutos.

### Masa base de vainilla (para Vainilla chispas, Manzana crumble y Arándanos)
Húmedos: aceite maravilla 360 mL, huevos 6 unidades, azúcar 720 g, leche 765 mL
(o 91,8 g de leche en polvo disuelta en agua).
Secos: harina 1.173 g, polvo de hornear 30 g, bicarbonato 7,5 g, sal 4,5 g.
Sin mantequilla, sin cacao y sin café.

### Muffin Vainilla Chispas
Masa base + chispas de chocolate 400 g en la masa.
Decoración: chispas de chocolate 90 g y azúcar flor 72 g.

### Muffin Manzana Crumble
Masa base + relleno de manzana confitada (comprado listo) 600 g, 25 g por muffin.
Crumble: harina 144 g, azúcar 96 g, mantequilla 120 g (15 g por muffin).

### Muffin Arándanos Glaseado
Masa base + arándanos 480 g (20 g por muffin).
Glaseado: azúcar flor 192 g y jugo de limón 48 g (10 g por muffin).

### Muffin Chocolate Ganache
Masa de chocolate: aceite maravilla 360 mL, huevos 6 unidades, azúcar 720 g,
café soluble 36 g, leche 765 mL (o 91,8 g de leche en polvo), harina 975 g,
cacao en polvo 198 g, polvo de hornear 30 g, bicarbonato 7,5 g, sal 4,5 g,
chispas de chocolate 400 g.
Decoración: chispas de chocolate 90 g y azúcar flor 72 g.
Inserto de ganache: 20 g por muffin, mitad crema 35% y mitad chocolate
(240 g de crema + 240 g de chocolate por lote).

## Alfajores (categoría nueva, recetario interno en ampliación)

### Alfajor Marplatense — rinde 12 alfajores (24 tapas, clásico de Mar del Plata: tapas de chocolate, relleno de dulce de leche, baño de chocolate semiamargo)
**Tapas de chocolate** (receta base ×2 para completar las 24 tapas del lote): mantequilla 300 g, azúcar 100 g, glucosa 100 g, ralladura de limón 5 g, ralladura de naranja 8 g, huevo 2 unidades, esencia de vainilla 8 g, harina todo uso 500 g, fécula de maíz 100 g, polvo de hornear 16 g, bicarbonato de sodio 10 g, cacao en polvo 40 g.
Procedimiento: batir la mantequilla a temperatura ambiente hasta suavizar → agregar azúcar, glucosa y las ralladuras de limón y naranja, batir hasta cremar → añadir el huevo y la esencia de vainilla, integrar → incorporar los secos tamizados (harina, fécula de maíz, polvo de hornear, bicarbonato, cacao en polvo), mezclar primero con espátula y luego a mano sin amasar → estirar entre láminas de papel film a 4 mm de espesor, refrigerar 1 hora o congelar 30 minutos → cortar tapas con cortante de 7 cm, refrigerar 10 minutos más → hornear a 170°C por 8-10 minutos, hasta que al tocar no queden marcas → enfriar sobre la placa y luego pasar a rejilla.

**Armado:** rellenar la mitad de las tapas (lado liso hacia afuera) con manga pastelera de dulce de leche casero, usando ~65 g por alfajor (900 g de dulce de leche para las 24 tapas/12 alfajores) → colocar la tapa restante encima y ajustar bordes con más dulce de leche.

**Baño de chocolate semiamargo:** calentar 550 g de cobertura de chocolate semiamargo en microondas en intervalos de 30 segundos hasta 40-45°C (sin curva de temperado) → sumergir cada alfajor cubriendo ambos lados, escurrir el exceso → dejar reposar a temperatura ambiente en lugar fresco, evitando el refrigerador (para que no formen vetas).
Reposo antes de consumir: mínimo 2 días, para que las tapas absorban humedad del relleno. Conservación: envase hermético, lugar fresco, 7 a 10 días.

## Notas de food cost objetivo por categoría (benchmark del negocio)
- Facturas: objetivo <20% (rango sano boutique 25-35%, facturas están debajo por ser el producto ancla)
- Medialunas Clásicas: objetivo <30%
- Especial/Premium: hasta ~42% aceptable si es bajo volumen (<10-15% del mix)
- Sobre 45% sostenido en producto de alto volumen: alarmante — revisar receta o precio


## Cheesecakes — Recetario técnico de producción Malatesta (gramos enteros; gelatina, agar agar, pectina y agua de la gelatina con su decimal exacto)
Rendimiento de referencia: 1 cheesecake para molde de 16 cm × 6 cm. En el bot: producto Cheesecake, 1 unidad = 1 cheesecake.

### Cheesecake — Migas sablée especiada (base de Frambuesa, Maracuyá, Frío, Café y Pistacho)
Ingredientes: azúcar flor 20 g; azúcar rubia 19 g; canela 1 g; harina 148 g; mantequilla fría sin sal 77 g; huevo 22 g.
Procedimiento: mezclar los secos con la mantequilla a baja velocidad hasta textura arenosa. Incorporar el huevo y trabajar a velocidad 1 hasta formar migas. Distribuir sobre bandeja y hornear a 180 °C unos 10 min, hasta coloración dorada uniforme. Enfriar antes de usar.

### Cheesecake — Base reconstituida (con migas sablée especiada)
Ingredientes: migas sablée especiada 137 g; mantequilla derretida 18 g; clara de huevo 8 g.
Procedimiento: procesar las migas hasta polvo fino. Mezclar con la mantequilla y la clara hasta masa arenosa y homogénea. Distribuir de forma uniforme en el molde de 16 cm y compactar suavemente, evitando una base demasiado densa.

### Cheesecake — Migas sablée de cacao (base de Chocolate y Dulce de leche)
Ingredientes: azúcar flor 20 g; azúcar rubia 19 g; harina 134 g; cacao en polvo 15 g; mantequilla fría sin sal 77 g; huevo 22 g.
Procedimiento: arenar secos y mantequilla a baja velocidad, incorporar el huevo y formar migas. Hornear a 180 °C unos 10 min hasta dorado uniforme. Enfriar.

### Cheesecake — Base reconstituida de cacao
Ingredientes: migas sablée de cacao 137 g; mantequilla derretida 18 g; clara de huevo 8 g.
Procedimiento: procesar las migas hasta polvo, mezclar con mantequilla y clara, extender en el molde y compactar suavemente.

### Cheesecake — Relleno cheesecake de vainilla (Frambuesa y Maracuyá)
Ingredientes: queso crema 376 g; azúcar 84 g; huevo 37 g; crema 35% 121 g; pasta de vainilla 6 g; maicena 8 g.
Procedimiento: procesar todo hasta mezcla homogénea, sin sobrebatir. Verter sobre la base. Cocer a 110 °C por 40–50 min hasta 65–70 °C en el centro. Enfriar a temperatura ambiente y congelar ~1 h antes de desmoldar.

### Cheesecake de Frambuesa — Ganache de frambuesa
Ingredientes: pulpa de frambuesa fresca 100 g; glucosa 40 g; chocolate blanco 31% 150 g; manteca de cacao 30 g; mantequilla fría 100 g; ácido cítrico 5 g.
Procedimiento: calentar la pulpa con la glucosa hasta ebullición. Verter sobre el chocolate blanco y la manteca de cacao y reposar ~20 s. Comprobar que supere 45 °C (si no, recalentar 20–30 s). Emulsionar con mixer de inmersión sin incorporar aire. Agregar la mantequilla y el ácido cítrico y emulsionar hasta ganache lisa y brillante. Cubrir a contacto y cristalizar hasta 12 h a ≤20 °C. Si se refrigera, sacar ~1 h antes de usar.

### Cheesecake de Frambuesa — Gel de frambuesa
Ingredientes: pulpa de frambuesa fresca 350 g; azúcar 100 g; agar agar 3,5 g.
Procedimiento: calentar la pulpa a 60 °C. Mezclar el azúcar con el agar agar e incorporarlo. Llevar a ebullición y mantener 1–2 min. Enfriar, procesar hasta homogeneizar y poner en manga sin boquilla.
Armado: base reconstituida + relleno de vainilla horneado. Decorar con la ganache, el gel, frambuesas y fruta glaseada.

### Cheesecake de Maracuyá — Gel mango–maracuyá–vainilla
Ingredientes: pulpa de mango 119 g; pulpa de maracuyá 119 g; pasta de vainilla 18 g; pectina NH 4,2 g; azúcar 45 g.
Procedimiento: calentar las pulpas y la vainilla a 60 °C. Mezclar el azúcar con la pectina NH e incorporarlos. Llevar a ebullición y mantener 1–2 min. Enfriar y procesar hasta textura lisa.
Armado: base reconstituida + relleno de vainilla horneado. Aplicar el gel sobre la superficie y terminar con mango glaseado, crocante de maracuyá y menta.

### Cheesecake Oreo — Base Oreo
Ingredientes: galletas Oreo sin crema 123 g; mantequilla derretida 32 g; clara de huevo 7 g.
Procedimiento: procesar las galletas hasta polvo fino. Incorporar mantequilla y clara y mezclar hasta textura arenosa. Distribuir en el molde y compactar ligeramente.

### Cheesecake Oreo — Relleno cheesecake Oreo
Ingredientes: queso crema 313 g; azúcar 70 g; huevo 31 g; crema 35% 101 g; pasta de vainilla 5 g; maicena 7 g; galletas Oreo trituradas 70 g.
Procedimiento: procesar hasta mezcla homogénea, incorporar las galletas trituradas y mezclar de forma uniforme. Verter sobre la base. Hornear a 110 °C por 40–50 min hasta 65–70 °C en el centro. Enfriar y congelar ~1 h antes de desmoldar.

### Cheesecake Oreo — Chantilly Oreo
Ingredientes: crema 35% fría 200 g; azúcar flor 20 g; Oreo triturada tamizada según necesidad.
Procedimiento: batir la crema fría con el azúcar flor hasta semi-montada. Incorporar la Oreo tamizada y seguir batiendo hasta crema firme y estable. Dosificar con boquilla lisa de ~1,5 cm y decorar con galletas Oreo.

### Cheesecake de Chocolate — Ganache de chocolate
Ingredientes: crema 35% 250 g; glucosa 5 g; chocolate con leche 56% 250 g.
Procedimiento: calentar crema y glucosa hasta ebullición. Verter sobre el chocolate, reposar ~20 s y comprobar que supere 45 °C. Emulsionar sin incorporar aire. Cubrir a contacto y cristalizar 12–24 h a ≤20 °C, o refrigerar y sacar ~1 h antes de usar.

### Cheesecake de Chocolate — Relleno cheesecake de chocolate
Ingredientes: queso crema 179 g; azúcar 95 g; huevo 60 g; crema 35% 138 g; cacao en polvo 41 g; maicena 10 g; chocolate negro 70% derretido 109 g.
Procedimiento: procesar hasta homogeneidad. Verter sobre la base reconstituida de cacao y hornear a 110 °C por 40–50 min hasta 65–70 °C en el centro. Enfriar y congelar ~1 h. Decorar con la ganache de chocolate, avellanas tostadas, praliné y hoja de oro.

### Cheesecake Frío — Base fría reconstituida
Ingredientes: migas sablée especiada 137 g; mantequilla derretida 20 g.
Procedimiento: procesar las migas y mezclar con la mantequilla. Distribuir en el molde de 16 cm y compactar uniformemente.

### Cheesecake Frío de Vainilla
Ingredientes: gelatina 180 Bloom 2 g; agua 10 g; queso crema 336 g; leche condensada 23 g; azúcar 25 g; azúcar flor 6 g; crema 35% caliente 100 g; vaina de vainilla 0,5 ud.
Procedimiento: hidratar la gelatina con el agua. Extraer las semillas de la vainilla e incorporarlas a la crema caliente; disolver allí la gelatina. Procesar con el resto hasta mezcla lisa. Verter sobre la base y congelar mínimo 12 h antes de desmoldar. No se hornea.

### Cheesecake Frío de Chocolate
Ingredientes: gelatina 180 Bloom 1,5 g; agua 7,5 g; queso crema 336 g; leche condensada 23 g; azúcar 25 g; cacao en polvo 8 g; azúcar flor 6 g; crema 35% caliente 100 g; chocolate negro 70% derretido 50 g.
Procedimiento: hidratar la gelatina con el agua y disolverla en la crema caliente. Procesar con el resto hasta emulsión homogénea. Verter sobre la base y congelar mínimo 12 h. No se hornea. Nota: el total declarado en la fuente no coincide con la suma de ingredientes; se conservan los ingredientes.

### Cheesecake de Dulce de Leche — Relleno
Ingredientes: queso crema 313 g; azúcar 70 g; huevo 31 g; crema 35% 101 g; pasta de vainilla 5 g; maicena 7 g; dulce de leche 100 g.
Procedimiento: trabajar queso crema, azúcar, maicena y vainilla a velocidad media 1 min; raspar el bowl y seguir ~30 s. Agregar el resto y batir 3–4 min a velocidad media-alta hasta homogeneizar. Verter sobre la base reconstituida de cacao y hornear a 110 °C por 40–50 min hasta 65–70 °C en el centro. Enfriar y congelar ~1 h.

### Cheesecake de Dulce de Leche — Ganache de chocolate blanco caramelizado
Ingredientes: crema 35% 115 g; leche entera 50 g; glucosa 73 g; Dulcey 35% 255 g; manteca de cacao 31 g; mantequilla fría 62 g.
Procedimiento: calentar crema, leche y glucosa. Verter sobre el chocolate y la manteca de cacao, reposar ~20 s y emulsionar cuando supere 45 °C. Incorporar la mantequilla y volver a emulsionar. Aplicar sobre el cheesecake y refrigerar 30–45 min para cristalizar. Decorar con líneas de chocolate negro y crispearls.

### Cheesecake de Café — Relleno
Ingredientes: queso crema 313 g; azúcar 70 g; huevo 31 g; crema 35% 101 g; pasta de vainilla 5 g; maicena 7 g; agua 8 g; café instantáneo 2 g.
Procedimiento: procesar todo hasta homogeneizar. Verter sobre la base reconstituida y hornear a 110 °C por 40–50 min hasta 65–70 °C en el centro. Enfriar y congelar ~1 h.

### Cheesecake de Café — Ganache montada de café
Ingredientes: crema 35% 141 g; café instantáneo 1 g; glucosa 4 g; chocolate blanco 31% 54 g.
Procedimiento: calentar crema, café y glucosa hasta ebullición. Verter sobre el chocolate, reposar ~20 s y emulsionar por completo. Cubrir a contacto y refrigerar al menos 12 h antes de montar.

### Cheesecake de Café — Ganache de chocolate negro
Ingredientes: chocolate negro 56% 130 g; crema 35% 78 g; azúcar invertido 38 g (sustituible 1:1 por glucosa); manteca de cacao 20 g.
Procedimiento: calentar la fase líquida con el chocolate y la manteca de cacao, asegurando más de 45 °C. Emulsionar y cubrir a contacto. Cristalizar 12 h a ≤20 °C o refrigerar y llevar a temperatura ambiente antes de usar.

### Cheesecake de Café — Ganache de café
Ingredientes: espresso 65 g; glucosa 25 g; sorbitol 10 g (sustituible 1:1 por glucosa); chocolate con leche 40% 255 g; manteca de cacao 5 g; mantequilla fría 62 g.
Procedimiento: calentar espresso, glucosa y sorbitol hasta ebullición. Verter sobre chocolate y manteca de cacao, reposar ~20 s y emulsionar. Incorporar la mantequilla fría y emulsionar hasta brillo y textura uniforme. Aplicar una capa de ~5 mm sobre el cheesecake y refrigerar 35–40 min.

### Cheesecake de Café — Placas de chocolate amargo
Ingredientes: chocolate negro 56% 200 g.
Procedimiento: templar el chocolate siguiendo la curva del fabricante. Extender y formar las placas decorativas según el formato de producción.

### Cheesecake de Pistacho — Ganache montada de pistacho
Ingredientes: crema 35% 202 g; glucosa 4 g; chocolate blanco 31% 77 g; pasta de pistacho 32 g.
Procedimiento: calentar crema y glucosa hasta ebullición. Verter sobre chocolate y pasta de pistacho, reposar ~20 s y emulsionar hasta ganache lisa. Cubrir a contacto y refrigerar al menos 12 h antes de montar.

### Cheesecake de Pistacho — Relleno
Ingredientes: queso crema 313 g; azúcar 70 g; huevo 31 g; crema 35% 101 g; pasta de vainilla 5 g; maicena 7 g; pasta de pistacho 80 g.
Procedimiento: procesar hasta homogeneidad. Verter sobre la base reconstituida y hornear a 110 °C por 40–50 min hasta 65–70 °C en el centro. Enfriar y congelar ~1 h.

### Cheesecake de Pistacho — Ganache de pistacho
Ingredientes: crema 35% 163 g; glucosa 50 g; chocolate blanco 31% 120 g; manteca de cacao 10 g; pasta de pistacho 55 g; colorante verde hidrosoluble c/n.
Procedimiento: calentar crema y glucosa hasta ebullición. Verter sobre chocolate y manteca de cacao, reposar 20 s y emulsionar. Incorporar la pasta de pistacho y, si corresponde, el colorante. Aplicar sobre la superficie del cheesecake y refrigerar 30–45 min.

### Cheesecake de Pistacho — Pistachos caramelizados
Ingredientes: pistachos 100 g; azúcar 25 g; clara de huevo 10 g.
Procedimiento: mezclar hasta recubrir los pistachos. Hornear a 180 °C por 8–10 min. Enfriar completamente antes de usar.

### Cheesecake de Avellana — Ganache de avellana
Ingredientes: crema 35% 105 g; chocolate con leche 40% 175 g; leche entera 50 g; glucosa 53 g; pasta de avellana 20 g.
Procedimiento: calentar chocolate, crema, leche y glucosa. Verificar más de 45 °C y emulsionar hasta textura lisa. Incorporar la pasta de avellana y completar la emulsión. Depositar en molde espiral y congelar ~2 h antes de desmoldar.

### Cheesecake de Avellana — Migas sablée de avellana
Ingredientes: azúcar flor 20 g; azúcar rubia 19 g; harina 105 g; mantequilla fría sin sal 77 g; huevo 22 g; avellanas 43 g; canela 1 g.
Procedimiento: procesar los secos con las avellanas hasta polvo fino. Arenar con la mantequilla a baja velocidad, incorporar el huevo y formar migas. Hornear a 180 °C unos 10 min hasta dorar.

### Cheesecake de Avellana — Base reconstituida de avellana
Ingredientes: migas sablée de avellana 137 g; mantequilla derretida 18 g; clara de huevo 8 g.
Procedimiento: procesar las migas y mezclar con mantequilla y clara. Distribuir y compactar uniformemente en el molde.

### Cheesecake de Avellana — Relleno
Ingredientes: queso crema 407 g; azúcar 91 g; huevo 40 g; crema 35% 131 g; pasta de vainilla 6 g; maicena 9 g; pasta de avellana 104 g.
Procedimiento: procesar hasta homogeneidad. Verter sobre la base y hornear a 110 °C por 40–50 min hasta 65–70 °C en el centro. Enfriar y congelar ~1 h antes de desmoldar.

### Cheesecake de Avellana — Avellanas caramelizadas
Ingredientes: avellanas 100 g; azúcar 25 g; clara de huevo 10 g.
Procedimiento: mezclar hasta cubrir las avellanas. Hornear a 180 °C por 8–10 min y enfriar.
