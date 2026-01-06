import os
import psycopg2
from dotenv import load_dotenv

# Cargar variables
load_dotenv()

url = os.environ.get("DATABASE_URL")
print(f"Intentando conectar a: {url.split('@')[1] if url else 'URL NO ENCONTRADA'}") # Imprime el host sin mostrar contraseña

try:
    conn = psycopg2.connect(url)
    print("\n✅ ¡ÉXITO! La conexión funciona perfectamente.")
    print("El problema podría estar en cómo FastAPI maneja la ruta, no en la BD.")
    conn.close()
except Exception as e:
    print("\n❌ ERROR DE CONEXIÓN:")
    print("-" * 30)
    print(e)
    print("-" * 30)