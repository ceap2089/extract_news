"""
extractor.py

Modulo de extraccion de noticias para la API Flask.

Este archivo toma la logica principal del script original del usuario,
pero elimina la ejecucion directa con una URL fija para que pueda ser usado
como libreria desde app.py.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

try:
    from bs4 import BeautifulSoup, Tag
except ModuleNotFoundError:  # pragma: no cover
    BeautifulSoup = None
    Tag = Any

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

SELECTORES_ARTICULO = [
    '[itemprop="articleBody"]',
    "#contenedor",
    "article",
    "main article",
    ".sc__content",
    ".sc__container",
    ".story-contents",
    ".story-content",
    ".article-content",
    ".entry-content",
    ".post-content",
    ".content-body",
    ".main-content",
    "#content",
]

PATRONES_RUIDO = [
    r"^lee tambi[ée]n",
    r"^mira:",
    r"^adem[aá]s",
    r"^video recomendado",
    r"^te puede interesar",
    r"^recibe",
    r"^suscr[ií]bete",
    r"^newsletter",
    r"^director period",
    r"^empresa editora",
    r"^copyright",
    r"^miembro del grupo",
    r"^este resumen es generado por inteligencia artificial",
    r"^noticias informaci[oó]n basada en hechos",
]


def validar_dependencias() -> None:
    if BeautifulSoup is None:
        raise RuntimeError(
            "Falta instalar 'beautifulsoup4'. Ejecuta: python -m pip install beautifulsoup4 requests"
        )


def limpiar_espacios(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    texto = re.sub(r"\s+([,.;:%)\]])", r"\1", texto)
    texto = re.sub(r"([(\[]) +", r"\1", texto)
    return texto


def _ip_es_segura(hostname: str) -> bool:
    """Evita que el backend consulte localhost o redes privadas."""
    try:
        direcciones = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False

    for item in direcciones:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def normalizar_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("Debes ingresar una URL.")

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("La URL debe empezar con http:// o https://.")
    if not parsed.netloc:
        raise ValueError("La URL no parece valida. Revisa el enlace.")
    if not _ip_es_segura(parsed.hostname or ""):
        raise ValueError("Por seguridad no se permiten URLs internas, locales o privadas.")

    return url


def descargar_html(url: str, timeout: int = 20) -> Tuple[str, str]:
    respuesta = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    respuesta.raise_for_status()

    content_type = respuesta.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type and content_type:
        raise ValueError("La URL no parece ser una pagina HTML de noticia.")

    if not respuesta.encoding or respuesta.encoding.lower() == "iso-8859-1":
        respuesta.encoding = respuesta.apparent_encoding or "utf-8"

    return respuesta.text, respuesta.url


def extraer_meta(soup: BeautifulSoup, atributo: str, valor: str) -> Optional[str]:
    etiqueta = soup.find("meta", attrs={atributo: valor})
    if etiqueta and etiqueta.get("content"):
        return limpiar_espacios(etiqueta["content"])
    return None


def aplanar_json_ld(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        resultado: List[Dict[str, Any]] = []
        for item in payload:
            resultado.extend(aplanar_json_ld(item))
        return resultado

    if isinstance(payload, dict):
        resultado = [payload]
        if isinstance(payload.get("@graph"), list):
            for item in payload["@graph"]:
                resultado.extend(aplanar_json_ld(item))
        return resultado

    return []


def iterar_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    encontrados: List[Dict[str, Any]] = []
    scripts = soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)})
    for script in scripts:
        contenido = script.string or script.get_text(strip=True)
        if not contenido:
            continue
        try:
            payload = json.loads(contenido)
        except json.JSONDecodeError:
            continue
        encontrados.extend(aplanar_json_ld(payload))
    return encontrados


def es_tipo_articulo(item: Dict[str, Any]) -> bool:
    tipo = item.get("@type", [])
    if isinstance(tipo, str):
        tipos = {tipo.lower()}
    else:
        tipos = {str(valor).lower() for valor in tipo}
    tipos_validos = {"article", "newsarticle", "reportagearticle", "liveblogposting", "blogposting"}
    return bool(tipos & tipos_validos)


def extraer_datos_json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
    for item in iterar_json_ld(soup):
        if not es_tipo_articulo(item):
            continue

        autor = item.get("author")
        if isinstance(autor, list):
            autor = ", ".join(
                persona.get("name", "").strip()
                for persona in autor
                if isinstance(persona, dict) and persona.get("name")
            )
        elif isinstance(autor, dict):
            autor = autor.get("name")

        return {
            "titulo": limpiar_espacios(item.get("headline", "")) or None,
            "descripcion": limpiar_espacios(item.get("description", "")) or None,
            "contenido": limpiar_espacios(item.get("articleBody", "")) or None,
            "autor": limpiar_espacios(str(autor)) if autor else None,
            "fecha_publicacion": item.get("datePublished"),
        }

    return {}


def texto_valido(texto: str) -> bool:
    texto_limpio = limpiar_espacios(texto)
    if len(texto_limpio) < 30:
        return False
    texto_minuscula = texto_limpio.lower()
    return not any(re.match(patron, texto_minuscula) for patron in PATRONES_RUIDO)


def extraer_parrafos(contenedor: Tag) -> List[str]:
    parrafos: List[str] = []
    vistos: set[str] = set()

    for nodo in contenedor.find_all(["p", "h2", "h3"]):
        if nodo.find_parent(["aside", "footer", "header", "nav", "form"]):
            continue
        texto = limpiar_espacios(nodo.get_text(" ", strip=True))
        if not texto_valido(texto):
            continue
        if texto not in vistos:
            vistos.add(texto)
            parrafos.append(texto)

    return parrafos


def es_contenedor_prometedor(nodo: Tag) -> bool:
    identificador = (nodo.get("id") or "").lower()
    clases = " ".join(nodo.get("class", [])).lower()
    pistas = (
        "article",
        "story",
        "content",
        "body",
        "entry",
        "post",
        "nota",
        "paywall",
        "main",
        "sc__",
    )
    texto = f"{identificador} {clases}"
    return any(pista in texto for pista in pistas)


def buscar_mejor_contenedor(soup: BeautifulSoup) -> Optional[Tag]:
    candidatos: List[Tag] = []
    vistos: set[int] = set()

    for selector in SELECTORES_ARTICULO:
        for nodo in soup.select(selector):
            identificador = id(nodo)
            if identificador not in vistos:
                vistos.add(identificador)
                candidatos.append(nodo)

    for nodo in soup.find_all(["article", "main", "section", "div"]):
        identificador = id(nodo)
        if identificador in vistos:
            continue
        if es_contenedor_prometedor(nodo):
            vistos.add(identificador)
            candidatos.append(nodo)

    mejor_contenedor = None
    mejor_puntaje = (0, 0)
    for candidato in candidatos:
        parrafos = extraer_parrafos(candidato)
        puntaje = (len(parrafos), sum(len(parrafo) for parrafo in parrafos))
        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor_contenedor = candidato

    return mejor_contenedor


def construir_contenido(soup: BeautifulSoup, contenido_json_ld: Optional[str]) -> str:
    if contenido_json_ld and len(contenido_json_ld) > 200:
        return contenido_json_ld

    contenedor = buscar_mejor_contenedor(soup)
    if not contenedor:
        return ""

    parrafos = extraer_parrafos(contenedor)
    return "\n\n".join(parrafos)


def slugify(texto: str) -> str:
    texto_normalizado = unicodedata.normalize("NFKD", texto)
    texto_ascii = texto_normalizado.encode("ascii", "ignore").decode("ascii")
    texto_limpio = re.sub(r"[^a-zA-Z0-9]+", "-", texto_ascii).strip("-").lower()
    return texto_limpio or "noticia"


def obtener_contenido_noticia(url: str) -> Dict[str, Any]:
    validar_dependencias()
    url_normalizada = normalizar_url(url)
    html, url_final = descargar_html(url_normalizada)
    soup = BeautifulSoup(html, "html.parser")
    datos_json_ld = extraer_datos_json_ld(soup)

    titulo = (
        datos_json_ld.get("titulo")
        or extraer_meta(soup, "property", "og:title")
        or extraer_meta(soup, "name", "twitter:title")
        or (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else None)
    )

    descripcion = (
        datos_json_ld.get("descripcion")
        or extraer_meta(soup, "name", "description")
        or extraer_meta(soup, "property", "og:description")
    )

    contenido = construir_contenido(soup, datos_json_ld.get("contenido"))
    if len(contenido) < 200:
        raise ValueError(
            "No pude identificar el cuerpo de la noticia. Usa el enlace directo del articulo, no la portada o una seccion."
        )

    return {
        "url": url_final,
        "dominio": urlparse(url_final).netloc,
        "titulo": titulo or "Titulo sin identificar",
        "descripcion": descripcion,
        "autor": datos_json_ld.get("autor"),
        "fecha_publicacion": datos_json_ld.get("fecha_publicacion")
        or extraer_meta(soup, "property", "article:published_time"),
        "contenido": contenido,
        "num_caracteres": len(contenido),
    }


def exportar_noticia(datos: Dict[str, Any], directorio_salida: Path, formato: str = "txt") -> Path:
    """Funcion opcional para uso local, no necesaria para la API."""
    directorio_salida.mkdir(parents=True, exist_ok=True)
    nombre_base = slugify(datos["titulo"])

    if formato == "json":
        ruta_salida = directorio_salida / f"{nombre_base}.json"
        ruta_salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        return ruta_salida

    ruta_salida = directorio_salida / f"{nombre_base}.txt"
    lineas = [f"Titulo: {datos['titulo']}", f"URL: {datos['url']}"]

    if datos.get("autor"):
        lineas.append(f"Autor: {datos['autor']}")
    if datos.get("fecha_publicacion"):
        lineas.append(f"Fecha: {datos['fecha_publicacion']}")
    if datos.get("descripcion"):
        lineas.append(f"Descripcion: {datos['descripcion']}")

    lineas.extend(["", "Contenido:", datos["contenido"]])
    ruta_salida.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_salida
