import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
import urllib
import pyodbc

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Monitoreo de Docentes - CBTis 139",
    page_icon="🎛️",
    layout="wide"
)

# -----------------------------------------------------------------------------
# 2. CONEXIÓN A BASE DE DATOS
# -----------------------------------------------------------------------------
@st.cache_resource
def obtener_conexion():
    drivers_instalados = pyodbc.drivers()
    driver_elegido = "SQL Server"
    
    for d in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]:
        if d in drivers_instalados:
            driver_elegido = d
            break

    try:
        server = st.secrets["db_credentials"]["SERVER"]
        database = st.secrets["db_credentials"]["DATABASE"]
        username = st.secrets["db_credentials"]["UID"]
        password = st.secrets["db_credentials"]["PWD"]
    except Exception:
        server = "CBTis139.mssql.somee.com"
        database = "CBTis139"
        username = "TovarLara_SQLLogin_1"
        password = "1hmetvyyiv"

    connection_string = (
        f"DRIVER={{{driver_elegido}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )

    params = urllib.parse.quote_plus(connection_string)
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

engine = obtener_conexion()

# -----------------------------------------------------------------------------
# 3. INTERFAZ Y CONTROLES
# -----------------------------------------------------------------------------
st.title("🎛️ Panel de Monitoreo - Jefatura de Docentes")
st.caption("Control de ingreso a clase en tiempo real")
st.write("---")

col_fecha, col_refresh = st.columns([2, 1])

with col_fecha:
    fecha_consulta = st.date_input("📅 Selecciona la Fecha a Monitorear", value=datetime.now().date())

with col_refresh:
    st.write("")
    st.write("")
    btn_actualizar = st.button("🔄 Actualizar Datos", use_container_width=True)

dia_semana_num = fecha_consulta.isoweekday() # 1=Lunes ... 7=Domingo

# -----------------------------------------------------------------------------
# 4. CONSULTA UNIFICADA
# -----------------------------------------------------------------------------
query_unificada = text("""
    SELECT 
        a.idhorario,
        LTRIM(RTRIM(a.grupo)) AS grupo,
        a.dia_semana,
        CONVERT(VARCHAR(5), a.inicio, 108) AS inicio,
        CONVERT(VARCHAR(5), a.fin, 108) AS fin,
        ISNULL(
            NULLIF(LTRIM(RTRIM(m.nombrecorto)), ''), 
            ISNULL(LTRIM(RTRIM(m.usuario)), 'Doc. ' + LTRIM(RTRIM(a.idmaestro)))
        ) AS docente,
        b.fecha,
        CONVERT(VARCHAR(5), b.hora, 108) AS hora_registro
    FROM Horario_Grupo a
    LEFT JOIN maestros m ON LTRIM(RTRIM(a.idmaestro)) = LTRIM(RTRIM(m.idmaestro))
    LEFT JOIN asistencia_docente b 
           ON b.idhorario = a.idhorario 
          AND b.fecha = :fecha
    WHERE a.dia_semana = :dia_semana
    ORDER BY a.inicio, a.grupo
""")

df_cruce = pd.DataFrame()

try:
    with engine.connect() as conn:
        df_cruce = pd.read_sql(query_unificada, conn, params={
            "fecha": str(fecha_consulta),
            "dia_semana": dia_semana_num
        })
except Exception as e:
    st.error(f"⚠️ Error al consultar la base de datos: {e}")

# -----------------------------------------------------------------------------
# 5. CONSTRUCCIÓN DE LA MALLA EVALUANDO RANGOS (INICIO <= HORA < FIN)
# -----------------------------------------------------------------------------
horas = ["07:30", "08:20", "09:10", "10:30", "11:20", "12:10", "13:00", "13:50"]

if not df_cruce.empty:
    grupos_activos = sorted(df_cruce["grupo"].unique().tolist())
else:
    grupos_activos = ["1AMA", "1BMA", "1CIA", "1DSG", "1ELO", "1FRH", "1GRH", "1HCO"]

matriz_datos = []
clases_programadas_total = 0
clases_cubiertas_total = 0

for h in horas:
    fila = {"Hora / Módulo": h}
    for g in grupos_activos:
        # Evaluamos si el módulo 'h' está dentro del bloque de la clase (inicio <= h < fin)
        reg = df_cruce[
            (df_cruce["grupo"] == g) & 
            (df_cruce["inicio"] <= h) & 
            (df_cruce["fin"] > h)
        ]
        
        if not reg.empty:
            clases_programadas_total += 1
            docente = reg.iloc[0]["docente"]
            hora_reg = reg.iloc[0]["hora_registro"]
            
            if pd.notna(hora_reg) and hora_reg != "":
                fila[g] = f"🟢 {docente} ({hora_reg})"
                clases_cubiertas_total += 1
            else:
                fila[g] = f"🔴 {docente}"
        else:
            fila[g] = "⚪ Libre"
            
    matriz_datos.append(fila)

df_malla = pd.DataFrame(matriz_datos).set_index("Hora / Módulo")

dias_nombre = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo"}
nombre_dia_str = dias_nombre.get(dia_semana_num, "")

st.subheader(f"Malla de Cobertura - {nombre_dia_str} {fecha_consulta.strftime('%d/%m/%Y')}")

col_l1, col_l2, col_l3 = st.columns(3)
col_l1.caption("🟢 **Presente**: Registró entrada en el bloque correspondiente.")
col_l2.caption("🔴 **Falta / Pendiente**: Clase programada sin registro.")
col_l3.caption("⚪ **Libre**: Módulo sin clase asignada.")

st.dataframe(df_malla, use_container_width=True, height=380)

# -----------------------------------------------------------------------------
# 6. MÉTRICAS Y RESUMEN
# -----------------------------------------------------------------------------
st.write("---")
st.subheader("📊 Resumen del Día")

c1, c2, c3 = st.columns(3)
c1.metric("Módulos Programados", clases_programadas_total)

porcentaje = (clases_cubiertas_total / clases_programadas_total * 100) if clases_programadas_total > 0 else 0
c2.metric("Módulos Cubiertos", clases_cubiertas_total, f"{porcentaje:.1f}% de cobertura")

pendientes = clases_programadas_total - clases_cubiertas_total
c3.metric("Módulos Sin Registro", pendientes, f"-{pendientes}" if pendientes > 0 else "0", delta_color="inverse")