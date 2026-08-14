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
# 2. CONEXIÓN A LA BASE DE DATOS
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
# 3. FUNCIONES DE AUDITORÍA Y SEGURIDAD
# -----------------------------------------------------------------------------
def registrar_bitacora(engine, idgestor, modulo, accion, detalles=""):
    """
    Inserta un evento de auditoría en la tabla 'bitacora'.
    """
    try:
        query = text("""
            INSERT INTO bitacora (idgestor, modulo, accion, detalles)
            VALUES (:idgestor, :modulo, :accion, :detalles)
        """)
        with engine.begin() as conn:
            conn.execute(query, {
                "idgestor": str(idgestor)[:3],  # Respeta el límite de 3 caracteres
                "modulo": modulo,
                "accion": accion,
                "detalles": detalles[:255] if detalles else ""
            })
    except Exception as e:
        # En auditoría, no interrumpimos la experiencia del usuario si falla el log
        print(f"⚠️ Error al escribir en bitácora: {e}")

def validar_gestor_por_password(engine, password):
    """
    Consulta la tabla 'gestor' para autenticar únicamente mediante la contraseña única.
    """
    try:
        query = text("""
            SELECT 
                LTRIM(RTRIM(idgestor)) AS idgestor, 
                LTRIM(RTRIM(nombre)) AS nombre, 
                LTRIM(RTRIM(puesto)) AS puesto 
            FROM gestor 
            WHERE LTRIM(RTRIM(password)) = :password
        """)
        with engine.connect() as conn:
            result = conn.execute(query, {
                "password": password.strip()
            }).fetchone()
            
            if result:
                return {
                    "idgestor": result[0],
                    "nombre": result[1],
                    "puesto": result[2]
                }
            return None
    except Exception as e:
        st.error(f"⚠️ Error de conexión al validar contraseña: {e}")
        return None

# -----------------------------------------------------------------------------
# 4. VISTA DE LOGIN
# -----------------------------------------------------------------------------
def mostrar_login(engine):
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Dashboard Institucional</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Control de Monitoreo - Jefatura de Docentes</p>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("form_login"):
            password_input = st.text_input("Ingrese su Contraseña de Gestor", type="password")
            submitted = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submitted:
                if not password_input:
                    st.warning("Por favor, ingrese su contraseña.")
                else:
                    datos_gestor = validar_gestor_por_password(engine, password_input)
                    if datos_gestor:
                        # Guardar estado de sesión
                        st.session_state["autenticado"] = True
                        st.session_state["gestor_actual"] = datos_gestor
                        
                        # Registrar en bitácora
                        registrar_bitacora(
                            engine=engine,
                            idgestor=datos_gestor["idgestor"],
                            modulo="Dashboard Docentes",
                            accion="LOGIN_EXITOSO",
                            detalles=f"Acceso de {datos_gestor['nombre']} ({datos_gestor['puesto']})"
                        )
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta o no registrada.")

# -----------------------------------------------------------------------------
# 5. VISTA DEL DASHBOARD PRINCIPAL (PROTEGIDO)
# -----------------------------------------------------------------------------
def mostrar_dashboard(engine):
    gestor = st.session_state["gestor_actual"]
    
    # Barra lateral con datos del usuario activo y botón de salida
    with st.sidebar:
        st.markdown(f"👤 **{gestor['nombre']}**")
        st.caption(f"Puesto: {gestor['puesto']} | ID: {gestor['idgestor']}")
        st.write("---")
        
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            registrar_bitacora(
                engine=engine,
                idgestor=gestor["idgestor"],
                modulo="Dashboard Docentes",
                accion="LOGOUT",
                detalles=f"Cierre de sesión de {gestor['nombre']}"
            )
            st.session_state["autenticado"] = False
            st.session_state["gestor_actual"] = None
            st.rerun()

    # Título principal
    st.title("🎛️ Panel de Monitoreo - Jefatura de Docentes")
    st.caption("Control de ingreso a clase en tiempo real")
    st.write("---")

    # Selección de fecha y refresco
    col_fecha, col_refresh = st.columns([2, 1])

    with col_fecha:
        fecha_consulta = st.date_input("📅 Selecciona la Fecha a Monitorear", value=datetime.now().date())

    with col_refresh:
        st.write("")
        st.write("")
        btn_actualizar = st.button("🔄 Actualizar Datos", use_container_width=True)

    dia_semana_num = fecha_consulta.isoweekday() # 1=Lunes ... 7=Domingo

    # Registrar en bitácora la consulta realizada
    if btn_actualizar or "ultima_fecha_consultada" not in st.session_state or st.session_state["ultima_fecha_consultada"] != fecha_consulta:
        st.session_state["ultima_fecha_consultada"] = fecha_consulta
        registrar_bitacora(
            engine=engine,
            idgestor=gestor["idgestor"],
            modulo="Dashboard Docentes",
            accion="CONSULTA_FECHA",
            detalles=f"Monitoreo fecha: {fecha_consulta.strftime('%Y-%m-%d')}"
        )

    # Consulta unificada a la Base de Datos
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

    # Construcción de la malla evaluando rangos (inicio <= h < fin)
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
            # Evalúa si el módulo 'h' cae dentro de la sesión (inicio <= h < fin)
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

    # Resumen del día
    st.write("---")
    st.subheader("📊 Resumen del Día")

    c1, c2, c3 = st.columns(3)
    c1.metric("Módulos Programados", clases_programadas_total)

    porcentaje = (clases_cubiertas_total / clases_programadas_total * 100) if clases_programadas_total > 0 else 0
    c2.metric("Módulos Cubiertos", clases_cubiertas_total, f"{porcentaje:.1f}% de cobertura")

    pendientes = clases_programadas_total - clases_cubiertas_total
    c3.metric("Módulos Sin Registro", pendientes, f"-{pendientes}" if pendientes > 0 else "0", delta_color="inverse")

# -----------------------------------------------------------------------------
# 6. CONTROLADOR PRINCIPAL
# -----------------------------------------------------------------------------
def main():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
        st.session_state["gestor_actual"] = None

    if not st.session_state["autenticado"]:
        mostrar_login(engine)
    else:
        mostrar_dashboard(engine)

if __name__ == "__main__":
    main()
