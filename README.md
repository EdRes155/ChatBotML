# 🤖 Bot de Ofertas Mercado Libre MX → Telegram

Bot que monitorea **50 productos** en tendencia en Mercado Libre México cada **5 minutos**, detecta descuentos mayores al **10%** y envía alertas a tu Telegram. Diseñado para correr 24/7 en **Railway**.

---

## 📦 Archivos del proyecto

| Archivo | Función |
|---|---|
| `main.py` | Lógica completa del bot (scraping, detección, envío) |
| `config.json` | Los 50 productos + parámetros (intervalo, umbrales, anti-spam) |
| `requirements.txt` | Dependencias |
| `Procfile` | Comando de arranque en Railway (worker) |
| `runtime.txt` | Versión de Python |
| `.env.example` | Plantilla de credenciales |
| `.gitignore` | Evita subir `.env` y el historial |

---

## 1️⃣ Crear el bot de Telegram (5 min)

1. Abre Telegram y busca **@BotFather**.
2. Envía `/newbot`, ponle nombre y usuario. Te dará un **TOKEN** como `123456789:AAxx...`.
3. Busca **@userinfobot**, mándale cualquier mensaje y te dará tu **CHAT_ID** (un número).
4. Importante: escríbele algo a **tu nuevo bot** primero (si no, no podrá enviarte mensajes).

---

## 2️⃣ Probar en tu computadora (local)

```bash
# Tener Python 3.8+ instalado
python --version

# Dentro de la carpeta del proyecto:
pip install -r requirements.txt

# Copiar la plantilla de credenciales:
cp .env.example .env
# Edita .env y pega tu TELEGRAM_TOKEN y CHAT_ID reales

# Ejecutar:
python main.py
```

Si todo está bien, recibirás en Telegram:
`🤖 Bot de ofertas Mercado Libre activado. Monitoreando...`

---

## 3️⃣ Desplegar 24/7 en Railway

1. Sube el proyecto a un repositorio de **GitHub** (sin el `.env`, ya está en `.gitignore`).
2. Entra a [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Selecciona tu repo. Railway detecta `Procfile` y `requirements.txt` automáticamente.
4. Ve a la pestaña **Variables** y agrega:
   - `TELEGRAM_TOKEN` = tu token
   - `CHAT_ID` = tu chat id
5. Railway construye y arranca el `worker`. Revisa **Deployments → Logs** para confirmar.

> ℹ️ El plan gratuito de Railway tiene horas limitadas al mes. Para 24/7 continuo quizá necesites el plan de uso (~$5 USD).

---

## ⚙️ Personalización (`config.json`)

```json
"configuracion": {
  "intervalo_minutos": 5,          // cada cuánto revisa
  "descuento_minimo": 10,          // % mínimo para alertar
  "descuento_precio_mas_bajo": 20, // a partir de aquí usa el formato "PRECIO MÁS BAJO"
  "anti_spam_minutos": 30,         // no repite el mismo producto antes de X min
  "max_items_por_busqueda": 8,     // cuántos resultados revisa por producto
  "max_reintentos": 4,             // reintentos si ML bloquea
  "backoff_base_segundos": 5       // espera base entre reintentos
}
```

Para cambiar productos, edita la lista `productos`: cada uno tiene `nombre`, `emoji`, `categoria`, `descripcion` y `busqueda` (lo que iría en la URL de listado de ML).

---

## 🛡️ Características técnicas

- **Anti-bloqueo**: rota 5 User-Agents distintos y hace pausas aleatorias entre búsquedas.
- **Selectores con 3 niveles de respaldo**: si ML cambia su HTML, el bot intenta varias rutas antes de rendirse.
- **Backoff exponencial** ante errores `403`/`429`.
- **Anti-spam** vía `historial_precios.json`: no te llega el mismo producto repetido.
- **A prueba de caídas**: si una ronda falla, el bot lo registra y sigue corriendo.

---

## 🔧 Problemas comunes

| Problema | Solución |
|---|---|
| No llegan mensajes | Verifica que le escribiste **primero** a tu bot; revisa TOKEN y CHAT_ID |
| `Sin items para...` constante | ML cambió su HTML; ajusta los selectores en `parsear_items()` |
| Muchos `403` | Sube `backoff_base_segundos`; ML está limitando; considera un proxy |
| Railway se duerme | Revisa el plan; el gratuito limita horas |

---

## 💡 Mejoras futuras (opcionales)

- Comandos `/status`, `/stop` por Telegram (polling).
- Filtrar por rango de precio o solo ciertas categorías.
- Base de datos para historial y gráficas de tendencia.
- Link de afiliado de Mercado Libre + publicación manual en Facebook (estrategia híbrida que ya discutimos: bajo riesgo y sin costo).

---

**Versión:** 2.0 — proyecto completo y funcional ✅
