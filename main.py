"""
========================================================================
  BOT DE MONITOREO DE OFERTAS - MERCADO LIBRE MÉXICO  ->  TELEGRAM
========================================================================
Monitorea 50 productos en tendencia, detecta descuentos > umbral y
envía alertas a Telegram. Pensado para correr 24/7 en Railway.

Autor: generado para Edwin
Licencia: uso personal
========================================================================
"""

import os
import json
import time
import random
import logging
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ----------------------------------------------------------------------
# CONFIGURACIÓN INICIAL
# ----------------------------------------------------------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
HISTORIAL_PATH = os.path.join(BASE_DIR, "historial_precios.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot-ml")

# Varios User-Agents para rotar y reducir bloqueos
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

URL_LISTADO = "https://listado.mercadolibre.com.mx/{busqueda}"


# ----------------------------------------------------------------------
# UTILIDADES DE ARCHIVOS
# ----------------------------------------------------------------------
def cargar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def cargar_historial():
    if not os.path.exists(HISTORIAL_PATH):
        return {}
    try:
        with open(HISTORIAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("Historial corrupto o ilegible. Se reinicia.")
        return {}


def guardar_historial(historial):
    try:
        with open(HISTORIAL_PATH, "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.error("No se pudo guardar el historial: %s", e)


# ----------------------------------------------------------------------
# SCRAPING DE MERCADO LIBRE
# ----------------------------------------------------------------------
def headers_aleatorios():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
    }


def descargar_pagina(url, cfg):
    """Descarga una página con reintentos y backoff exponencial."""
    max_reintentos = cfg["max_reintentos"]
    backoff = cfg["backoff_base_segundos"]

    for intento in range(1, max_reintentos + 1):
        try:
            resp = requests.get(
                url,
                headers=headers_aleatorios(),
                timeout=cfg["timeout_request"],
            )
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (403, 429):
                espera = backoff * (2 ** (intento - 1)) + random.uniform(0, 3)
                log.warning(
                    "Bloqueo %s en %s. Reintento %d/%d en %.1fs",
                    resp.status_code, url, intento, max_reintentos, espera,
                )
                time.sleep(espera)
                continue
            log.warning("HTTP %s en %s", resp.status_code, url)
            return None
        except requests.RequestException as e:
            espera = backoff * (2 ** (intento - 1)) + random.uniform(0, 3)
            log.warning("Error de red (%s). Reintento %d/%d en %.1fs",
                        e, intento, max_reintentos, espera)
            time.sleep(espera)
    log.error("Agotados los reintentos para %s", url)
    return None


def _texto_a_precio(texto):
    """Convierte '1.299' o '1,299' a float 1299.0"""
    if not texto:
        return None
    limpio = texto.strip().replace(",", "").replace(".", "")
    try:
        return float(limpio)
    except ValueError:
        return None


def parsear_items(html, max_items):
    """
    Extrae items con selectores de 3 niveles (fallbacks) porque ML
    cambia su HTML con frecuencia.
    """
    soup = BeautifulSoup(html, "lxml")

    # --- Nivel 1 / 2 / 3 para localizar las tarjetas de producto ---
    items = soup.select("li.ui-search-layout__item")
    if not items:
        items = soup.select("div.ui-search-result__wrapper")
    if not items:
        items = soup.select("div.poly-card")

    resultados = []
    for item in items[:max_items]:
        # ---- Título ----
        titulo_el = (
            item.select_one("a.poly-component__title")
            or item.select_one("h2.ui-search-item__title")
            or item.select_one("h3.poly-component__title-wrapper a")
            or item.select_one("h2 a")
        )
        titulo = titulo_el.get_text(strip=True) if titulo_el else None

        # ---- Link ----
        link_el = (
            item.select_one("a.poly-component__title")
            or item.select_one("a.ui-search-link")
            or item.select_one("a.ui-search-item__group__element")
            or item.select_one("a[href*='mercadolibre.com.mx']")
        )
        link = link_el["href"].split("#")[0] if link_el and link_el.has_attr("href") else None

        # ---- Precio actual ----
        precio_el = (
            item.select_one("div.poly-price__current span.andes-money-amount__fraction")
            or item.select_one("span.andes-money-amount__fraction")
        )
        precio_actual = _texto_a_precio(precio_el.get_text()) if precio_el else None

        # ---- Precio original (tachado) ----
        original_el = (
            item.select_one("s.andes-money-amount--previous span.andes-money-amount__fraction")
            or item.select_one("s.andes-money-amount__previous span.andes-money-amount__fraction")
            or item.select_one("s span.andes-money-amount__fraction")
        )
        precio_original = _texto_a_precio(original_el.get_text()) if original_el else None

        if titulo and link and precio_actual:
            resultados.append({
                "titulo": titulo,
                "link": link,
                "precio_actual": precio_actual,
                "precio_original": precio_original,
            })

    return resultados


def calcular_descuento(actual, original):
    if not original or original <= actual:
        return 0
    return round((original - actual) / original * 100)


# ----------------------------------------------------------------------
# TELEGRAM
# ----------------------------------------------------------------------
def enviar_telegram(texto):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log.error("Falta TELEGRAM_TOKEN o CHAT_ID en variables de entorno.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            return True
        log.error("Telegram respondió %s: %s", r.status_code, r.text[:200])
        return False
    except requests.RequestException as e:
        log.error("No se pudo enviar a Telegram: %s", e)
        return False


def formatear_mensaje(prod, oferta, descuento, umbral_alto):
    """Dos variantes según el tamaño del descuento."""
    nombre = oferta["titulo"]
    emoji = prod["emoji"]
    desc = prod["descripcion"]
    actual = f"${oferta['precio_actual']:,.0f}"
    original = f"${oferta['precio_original']:,.0f}" if oferta["precio_original"] else "N/D"
    link = oferta["link"]

    if descuento >= umbral_alto:
        return (
            f"🔥 <b>PRECIO MÁS BAJO</b> 🔥\n"
            f"{emoji} <b>{nombre}</b>\n\n"
            f"{desc}\n\n"
            f"💰 Descuento <b>{descuento}%</b>\n"
            f"Precio oferta: <b>{actual}</b>\n"
            f"Precio original: <s>{original}</s>\n\n"
            f"🔗 <a href=\"{link}\">Ver producto</a>"
        )
    return (
        f"⬇️ <b>DESCUENTO DEL {descuento}%</b> en {nombre} {emoji}\n\n"
        f"{desc}\n\n"
        f"Precio oferta: <b>{actual}</b>\n"
        f"Precio original: <s>{original}</s>\n\n"
        f"🔗 <a href=\"{link}\">Ver producto</a>"
    )


# ----------------------------------------------------------------------
# ANTI-SPAM
# ----------------------------------------------------------------------
def puede_alertar(historial, clave, anti_spam_min):
    registro = historial.get(clave)
    if not registro:
        return True
    try:
        ultima = datetime.fromisoformat(registro["ultima_alerta"])
    except (KeyError, ValueError):
        return True
    return datetime.now() - ultima >= timedelta(minutes=anti_spam_min)


# ----------------------------------------------------------------------
# CICLO PRINCIPAL
# ----------------------------------------------------------------------
def revisar_productos():
    data = cargar_config()
    cfg = data["configuracion"]
    productos = data["productos"]
    historial = cargar_historial()

    umbral = cfg["descuento_minimo"]
    umbral_alto = cfg["descuento_precio_mas_bajo"]
    anti_spam = cfg["anti_spam_minutos"]
    max_items = cfg["max_items_por_busqueda"]

    alertas_enviadas = 0

    for prod in productos:
        url = URL_LISTADO.format(busqueda=prod["busqueda"])
        html = descargar_pagina(url, cfg)
        if not html:
            continue

        items = parsear_items(html, max_items)
        if not items:
            log.info("Sin items para '%s'", prod["nombre"])
        for oferta in items:
            descuento = calcular_descuento(
                oferta["precio_actual"], oferta["precio_original"]
            )
            if descuento < umbral:
                continue

            clave = oferta["link"]
            if not puede_alertar(historial, clave, anti_spam):
                continue

            mensaje = formatear_mensaje(prod, oferta, descuento, umbral_alto)
            if enviar_telegram(mensaje):
                alertas_enviadas += 1
                historial[clave] = {
                    "producto": prod["nombre"],
                    "precio": oferta["precio_actual"],
                    "descuento": descuento,
                    "ultima_alerta": datetime.now().isoformat(),
                }
                log.info("Alerta enviada: %s (%d%%)", oferta["titulo"][:40], descuento)
                time.sleep(1)  # respeta límite de Telegram

        # pausa corta entre búsquedas para no saturar a ML
        time.sleep(random.uniform(1.5, 3.5))

    guardar_historial(historial)
    return alertas_enviadas


def main():
    log.info("=" * 55)
    log.info("BOT MERCADO LIBRE MX -> TELEGRAM iniciado")
    log.info("=" * 55)

    if not TELEGRAM_TOKEN or not CHAT_ID:
        log.error("Configura TELEGRAM_TOKEN y CHAT_ID antes de iniciar.")
        return

    data = cargar_config()
    intervalo = data["configuracion"]["intervalo_minutos"]

    enviar_telegram("🤖 Bot de ofertas Mercado Libre activado. Monitoreando...")

    while True:
        inicio = datetime.now()
        log.info("Iniciando ronda de revisión...")
        try:
            n = revisar_productos()
            log.info("Ronda terminada. %d alertas enviadas.", n)
        except Exception as e:  # noqa: BLE001 - el bot nunca debe morir
            log.exception("Error en la ronda: %s", e)

        transcurrido = (datetime.now() - inicio).total_seconds()
        espera = max(0, intervalo * 60 - transcurrido)
        log.info("Esperando %.0f s para la siguiente ronda.", espera)
        time.sleep(espera)


if __name__ == "__main__":
    main()
