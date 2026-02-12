from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from api.db import get_db_connection
from datetime import date
from typing import Optional

app = FastAPI()

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

class PagoDeudaDTO(BaseModel):
    id_cuenta: int       # De dónde sale el dinero (ej. Mercado Pago)
    id_deuda: int        # Qué deuda estamos pagando (ej. Préstamo Horag)
    monto: float         # Cuánto pagamos (Positivo, el backend lo vuelve negativo para la trx)
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

# --- 4. SOLUCIÓN PROBLEMA 3: DATOS PARA GRÁFICOS ---
# Este endpoint alimenta la gráfica de dona del Frontend.
@app.get("/api/dashboard/gastos_categoria")
def gastos_por_categoria(mes: int = None, anio: int = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Si no envían fecha, usamos el mes actual
    if not mes or not anio:
        hoy = date.today()
        mes, anio = hoy.month, hoy.year

    query = """
        SELECT 
            c.nombre_categoria, 
            ABS(SUM(t.monto)) as total
        FROM transacciones t
        JOIN categorias c ON t.id_categoria = c.id
        WHERE t.monto < 0                  -- Solo gastos
        AND EXTRACT(MONTH FROM t.fecha) = %s
        AND EXTRACT(YEAR FROM t.fecha) = %s
        GROUP BY c.nombre_categoria
        ORDER BY total DESC;
    """
    
    cursor.execute(query, (mes, anio))
    datos = cursor.fetchall()
    conn.close()
    return datos


# --- 5. SOLUCIÓN PROBLEMA 2: PAGO DE DEUDAS  ---
@app.post("/api/deuda/pago")
def registrar_pago_deuda(datos: PagoDeudaDTO):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Validar que la deuda existe y obtener cuánto falta
        cursor.execute("SELECT monto_restante FROM deudas WHERE id = %s", (datos.id_deuda,))
        deuda = cursor.fetchone()
        
        if not deuda:
             raise HTTPException(status_code=404, detail="Deuda no encontrada")

        # 2. Registrar la salida de dinero (Gasto) en Transacciones
        # OJO: Asumimos que la tabla transacciones sí tiene 'id_deuda' según lo acordado.
        cursor.execute("""
            INSERT INTO transacciones (fecha, descripcion, monto, id_cuenta, id_deuda)
            VALUES (%s, %s, %s, %s, %s)
        """, (datos.fecha, "Abono a Deuda", -datos.monto, datos.id_cuenta, datos.id_deuda))

        # 3. Actualizar el saldo restante en la tabla Deudas
        # Ya no usamos 'activo', solo matemáticas.
        nuevo_restante = float(deuda['monto_restante']) - datos.monto
        
        # Evitamos números negativos absurdos (ej. -0.00001)
        if nuevo_restante < 0:
            nuevo_restante = 0

        cursor.execute("""
            UPDATE deudas
            SET monto_restante = %s
            WHERE id = %s
        """, (nuevo_restante, datos.id_deuda))

        conn.commit()
        return {"mensaje": "Pago registrado", "monto_restante_actual": nuevo_restante}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# --- 6. ENDPOINT EXTRA: VER DEUDAS ACTIVAS (CORREGIDO) ---
@app.get("/api/deudas")
def obtener_deudas():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # LÓGICA CORREGIDA:
    # Como no existe la columna 'activo', filtramos matemáticamente.
    # Una deuda está activa si todavía debes dinero (monto_restante > 0).
    query = """
        SELECT id, nombre, monto_total, monto_restante, fecha_inicio, id_cuenta_asociada
        FROM deudas 
        WHERE monto_restante > 0 
        ORDER BY monto_restante DESC
    """
    
    cursor.execute(query)
    deudas = cursor.fetchall()
    conn.close()
    return deudas