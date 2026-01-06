import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carga las variables del archivo .env a la memoria del sistema
load_dotenv()

def get_db_connection():
    """
    Establece una conexión con la base de datos Neon (PostgreSQL).
    Retorna el objeto de conexión o None si falla.
    """
    try:
        # Obtenemos la URL segura desde las variables de entorno
        db_url = os.environ.get("DATABASE_URL")
        
        if not db_url:
            raise ValueError("La variable DATABASE_URL no está configurada.")

        # Conectamos
        conn = psycopg2.connect(
            db_url,
            cursor_factory=RealDictCursor # Para recibir JSONs, no tuplas
        )
        return conn

    except Exception as e:
        print(f"❌ Error crítico conectando a la BD: {e}")
        return None