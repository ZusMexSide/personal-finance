from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from api.db import get_db_connection
from datetime import date

app = FastAPI()

# --- MODELOS DE DATOS (Pydantic) ---
# Esto valida que los datos que lleguen del Frontend sean correctos.
# Si falta un campo o el tipo de dato está mal, FastAPI devuelve error automáticamente.

class TransferenciaDTO(BaseModel):
    id_cuenta_origen: int
    id_cuenta_destino: int
    monto: float
    fecha: date = date.today() # Si no envían fecha, usa la de hoy

class NuevaTransaccionDTO(BaseModel):
    id_cuenta: int
    id_categoria: int = None # Opcional (puede ser null)
    monto: float # Negativo para gasto, positivo para ingreso
    descripcion: str
    fecha: date = date.today()

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"mensaje": "API Finanzas Personales - Fase 2"}

# 1. GET CUENTAS (Con Saldo Calculado)
# En lugar de solo leer el saldo inicial, sumamos todas las transacciones históricas
# para decirte cuánto dinero tienes REALMENTE ahora mismo.
@app.get("/api/cuentas")
def obtener_cuentas_con_saldo():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            c.id, 
            c.nombre, 
            c.tipo,
            (c.saldo_inicial + COALESCE(SUM(t.monto), 0)) as saldo_actual
        FROM cuentas c
        LEFT JOIN transacciones t ON c.id = t.id_cuenta
        GROUP BY c.id, c.nombre, c.tipo, c.saldo_inicial
        ORDER BY saldo_actual DESC;
    """
    
    cursor.execute(query)
    cuentas = cursor.fetchall()
    conn.close()
    return cuentas

# 2. SOLUCIÓN PROBLEMA 1: TRANSFERENCIAS
# Crea dos transacciones internas automáticamente.
@app.post("/api/transaccion/transferencia")
def crear_transferencia(datos: TransferenciaDTO):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Validación lógica: No transferir a la misma cuenta
        if datos.id_cuenta_origen == datos.id_cuenta_destino:
            raise HTTPException(status_code=400, detail="Origen y destino son iguales")

        # 1. Salida de Dinero (Restar a Origen)
        cursor.execute("""
            INSERT INTO transacciones (fecha, descripcion, monto, id_cuenta, es_transferencia)
            VALUES (%s, %s, %s, %s, TRUE)
        """, (datos.fecha, f"Transferencia a Cuenta #{datos.id_cuenta_destino}", -datos.monto, datos.id_cuenta_origen))

        # 2. Entrada de Dinero (Sumar a Destino)
        cursor.execute("""
            INSERT INTO transacciones (fecha, descripcion, monto, id_cuenta, es_transferencia)
            VALUES (%s, %s, %s, %s, TRUE)
        """, (datos.fecha, f"Transferencia desde Cuenta #{datos.id_cuenta_origen}", datos.monto, datos.id_cuenta_destino))
        
        # CONFIRMAR CAMBIOS (COMMIT)
        # Si algo falla antes de llegar aquí, nada se guarda.
        conn.commit()
        return {"mensaje": "Transferencia exitosa"}

    except Exception as e:
        conn.rollback() # Deshacer cambios si hubo error
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# 3. TRANSACCIÓN SIMPLE (Gasto o Ingreso)
@app.post("/api/transaccion")
def crear_transaccion(datos: NuevaTransaccionDTO):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO transacciones (fecha, descripcion, monto, id_cuenta, id_categoria)
            VALUES (%s, %s, %s, %s, %s)
        """, (datos.fecha, datos.descripcion, datos.monto, datos.id_cuenta, datos.id_categoria))
        
        conn.commit()
        return {"mensaje": "Transacción registrada"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()