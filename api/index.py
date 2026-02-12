from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from api.db import get_db_connection
from datetime import date
from typing import Optional

app = FastAPI()

# --- MODELOS DE DATOS (DTOs) ---

class TransferenciaDTO(BaseModel):
    id_cuenta_origen: int
    id_cuenta_destino: int
    monto: float
    fecha: date = date.today()

class NuevaTransaccionDTO(BaseModel):
    id_cuenta: int
    id_categoria: Optional[int] = None
    monto: float
    descripcion: str
    fecha: date = date.today()

class PagoDeudaDTO(BaseModel):
    id_cuenta: int       
    id_deuda: int        
    monto: float         
    fecha: date = date.today()

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"mensaje": "API Finanzas Personales - Fase 2 Completa"}

# 1. GET CUENTAS
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

# 2. POST TRANSFERENCIA
@app.post("/api/transaccion/transferencia")
def crear_transferencia(datos: TransferenciaDTO):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if datos.id_cuenta_origen == datos.id_cuenta_destino:
            raise HTTPException(status_code=400, detail="Origen y destino son iguales")

        # Salida
        cursor.execute("""
            INSERT INTO transacciones (fecha, descripcion, monto, id_cuenta, es_transferencia)
            VALUES (%s, %s, %s, %s, TRUE)
        """, (datos.fecha, f"Transferencia a Cuenta #{datos.id_cuenta_destino}", -datos.monto, datos.id_cuenta_origen))

        # Entrada
        cursor.execute("""
            INSERT INTO transacciones (fecha, descripcion, monto, id_cuenta, es_transferencia)
            VALUES (%s, %s, %s, %s, TRUE)
        """, (datos.fecha, f"Transferencia desde Cuenta #{datos.id_cuenta_origen}", datos.monto, datos.id_cuenta_destino))
        
        conn.commit()
        return {"mensaje": "Transferencia exitosa"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# 3. POST TRANSACCIÓN SIMPLE
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

# 4. GET DASHBOARD (Solución Problema 3)
@app.get("/api/dashboard/gastos_categoria")
def gastos_por_categoria(mes: Optional[int] = None, anio: Optional[int] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if not mes or not anio:
        hoy = date.today()
        mes, anio = hoy.month, hoy.year

    query = """
        SELECT 
            c.nombre_categoria, 
            ABS(SUM(t.monto)) as total
        FROM transacciones t
        JOIN categorias c ON t.id_categoria = c.id
        WHERE t.monto < 0
        AND EXTRACT(MONTH FROM t.fecha) = %s
        AND EXTRACT(YEAR FROM t.fecha) = %s
        GROUP BY c.nombre_categoria
        ORDER BY total DESC;
    """
    cursor.execute(query, (mes, anio))
    datos = cursor.fetchall()
    conn.close()
    return datos

# 5. POST PAGO DEUDA (Solución Problema 2 - CORREGIDO)
@app.post("/api/deuda/pago")
def registrar_pago_deuda(datos: PagoDeudaDTO):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Validar existencia
        cursor.execute("SELECT monto_restante FROM deudas WHERE id = %s", (datos.id_deuda,))
        deuda = cursor.fetchone()
        
        if not deuda:
             raise HTTPException(status_code=404, detail="Deuda no encontrada")

        # Registrar Gasto
        cursor.execute("""
            INSERT INTO transacciones (fecha, descripcion, monto, id_cuenta, id_deuda)
            VALUES (%s, %s, %s, %s, %s)
        """, (datos.fecha, "Abono a Deuda", -datos.monto, datos.id_cuenta, datos.id_deuda))

        # Actualizar Saldo Restante (SIN tocar columna 'activo')
        nuevo_restante = float(deuda['monto_restante']) - datos.monto
        if nuevo_restante < 0: nuevo_restante = 0

        cursor.execute("UPDATE deudas SET monto_restante = %s WHERE id = %s", (nuevo_restante, datos.id_deuda))

        conn.commit()
        return {"mensaje": "Pago registrado", "monto_restante_actual": nuevo_restante}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# 6. GET DEUDAS ACTIVAS
@app.get("/api/deudas")
def obtener_deudas():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Filtramos por matemática, no por columna booleana
    cursor.execute("SELECT * FROM deudas WHERE monto_restante > 0 ORDER BY monto_restante DESC")
    deudas = cursor.fetchall()
    conn.close()
    return deudas