import requests
from bs4 import BeautifulSoup

def obtener_contenido_noticia(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    # Realizar la solicitud HTTP
    response = requests.get(url, headers=headers)

    # Verificar si la solicitud fue exitosa
    if response.status_code == 200:
        # Analizar el contenido HTML de la página
        soup = BeautifulSoup(response.text, 'html.parser')

        # Intentar encontrar el contenedor principal del artículo
        articulo = soup.find('div', class_='story-contents')  # Clase común en Gestión.pe

        if not articulo:
            # A veces los artículos pueden estar en otro contenedor, probamos otro método
            articulo = soup.find('div', {'id': 'content'})

        if articulo:
            # Extraer el título
            titulo = soup.find('h1').get_text(strip=True) if soup.find('h1') else 'Título no encontrado'

            # Extraer todos los párrafos dentro del artículo
            parrafos = articulo.find_all('p')
            contenido = '\n'.join(p.get_text(strip=True) for p in parrafos)

            return titulo, contenido
        else:
            return None, 'No se encontró el contenido del artículo. Es posible que esté cargado dinámicamente con JavaScript.'
    else:
        return None, f'Error al acceder a la página: Código {response.status_code}'

# URL de la noticia
url = 'https://gestion.pe/opinion/precio-del-dolar-tipo-de-cambio-el-sol-que-brilla-analisis-del-tipo-de-cambio-para-el-proximo-mes-noticia/'

# Obtener el contenido de la noticia
titulo, contenido = obtener_contenido_noticia(url)

if titulo:
    print(f'Título: {titulo}\n')
    print('Contenido:')
    print(contenido)
else:
    print(contenido)
