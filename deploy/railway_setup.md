# Deploy en Railway

Se evaluó Oracle Cloud (OCI Compute Always Free) primero, pero la verificación
de cuenta demora hasta 24 horas — Railway permite desplegar en minutos con
login por GitHub, así que se usó para esta entrega. El enunciado del challenge
permite cualquier plataforma, OCI era solo una sugerencia.

El bot usa long-polling hacia la API de Telegram, así que no hace falta
exponer ningún puerto ni configurar networking.

## Pasos (ya ejecutados para este proyecto)

1. Crear cuenta en [railway.app](https://railway.app) con "Continue with GitHub".
2. Aceptar los términos (Privacy and Data Policy + Fair Use Policy).
3. Instalar la Railway GitHub App, con acceso limitado **solo** al repo
   `bot-chef-malatesta` (Settings → Only select repositories).
4. New Project → GitHub Repository → seleccionar el repo. Railway detecta
   Python automáticamente (builder **Railpack**, no Nixpacks -- Railway migró
   de builder en algún momento de 2026; un `nixpacks.toml` en la raíz del repo
   NO tiene ningún efecto en este builder, se ignora en silencio. Paquetes de
   sistema como Tesseract se agregan con `railpack.json` → `deploy.aptPackages`
   en su lugar, ver ese archivo en la raíz del repo).
5. En la pestaña **Variables** del servicio, cargar (Raw Editor):
   ```
   COHERE_API_KEY=...
   TELEGRAM_BOT_TOKEN=...
   ```
6. En **Settings → Deploy → Custom Start Command**, poner:
   ```
   python -m src.ingest && python -m src.telegram_bot
   ```
   (reconstruye el índice FAISS en cada deploy antes de levantar el bot,
   porque `data/index_recetas/` está en `.gitignore` y no se sube al repo).
7. Deploy. Verificar en **Deployments → Deploy Logs** que aparezcan líneas
   `INFO:httpx:HTTP Request: POST https://api.telegram.org/bot.../sendMessage
   "HTTP/1.1 200 OK"` sin errores.

## Gotchas de deploy (encontrados en producción, septiembre 2026)
- **`railway redeploy` sola NO reconstruye la imagen** -- redeploya el último
  build ya armado, aunque haya commits nuevos en GitHub. Para forzar un
  rebuild real desde el commit más reciente hace falta
  `railway redeploy --from-source -y`.
- El auto-deploy por push a GitHub puede dejar de dispararse sin aviso (pasó
  en esta sesión: dos semanas sin redeploy real pese a varios push seguidos).
  Conviene confirmar el `deployment ID` con `railway status` después de cada
  push importante, y no asumir que un push ya quedó desplegado.

## Costo
Railway da un trial de $5 USD o 30 días (lo que se cumpla primero) sin tarjeta
para arrancar. Un bot de bajo tráfico como este consume centavos por día de
ese crédito.
