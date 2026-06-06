"""
app.py

API Flask para extraer texto de noticias desde una URL.
Pensado para desplegarse en Render/Railway/Fly y ser llamado desde GitHub Pages.
"""

from __future__ import annotations

import os

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

from extractor import obtener_contenido_noticia

app = Flask(__name__)
CORS(app)


@app.get("/")
def home():
    return jsonify(
        {
            "status": "ok",
            "message": "API de extraccion de noticias activa.",
            "endpoints": {
                "health": "GET /health",
                "extraer": "POST /extraer con JSON {'url': 'https://...'}",
            },
        }
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/extraer")
def extraer():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"ok": False, "error": "Debes enviar una URL en el campo 'url'."}), 400

    try:
        noticia = obtener_contenido_noticia(url)
        return jsonify({"ok": True, "noticia": noticia})

    except requests.Timeout:
        return jsonify({"ok": False, "error": "La pagina tardo demasiado en responder."}), 504

    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else 502
        return jsonify(
            {
                "ok": False,
                "error": f"No pude descargar la pagina. Codigo HTTP: {status_code}.",
            }
        ), 502

    except requests.RequestException as error:
        return jsonify({"ok": False, "error": f"Error de conexion: {error}"}), 502

    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    except Exception as error:  # pragma: no cover
        return jsonify({"ok": False, "error": f"Error inesperado: {error}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
