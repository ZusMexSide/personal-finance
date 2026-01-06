from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.db import get_db_connection

app = FastAPI()

# --- CONFIGURACIÓN CORS ---
# Permitimos que cualquier origen ("*") se conecte por ahora.
# En producción, esto se debería cambiar por la URL real de tu frontend para más seguridad.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], # Permitir GET, POST, PUT, DELETE
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"mensaje": "Bienvenido a la API de Finanzas Personales"}

# Endpoint de Prueba de Conexión
@app.get("/api/test-db")
def test_db():
    conn = get_db_connection()
    if conn:
        conn.close()
        return {"status": "success", "mensaje": "Conexión a Neon DB exitosa 🟢"}
    else:
        # Retornamos un error HTTP 500 (Internal Server Error)
        raise HTTPException(status_code=500, detail="Fallo la conexión a la BD 🔴")