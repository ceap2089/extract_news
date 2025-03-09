from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

def obtener_contenido_noticia(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        articulo = soup.find('div', class_='story-contents') or soup.find('div', {'id': 'content'})

        if articulo:
            titulo = soup.find('h1').get_text(strip=True) if soup.find('h1') else 'Título no encontrado'
            parrafos = articulo.find_all('p')
            contenido = '\n'.join(p.get_text(strip=True) for p in parrafos)
            return titulo, contenido
        else:
            return None, 'No se encontró el contenido del artículo.'
    else:
        return None, f'Error {response.status_code}'

@app.route("/extraer", methods=["POST"])
def extraer():
    data = request.json
    url = data.get("url", "")
    titulo, contenido = obtener_contenido_noticia(url)
    return jsonify({"titulo": titulo, "contenido": contenido})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
