from datetime import datetime, date
import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Portal Escolar - Zona 1", page_icon="🏫", layout="wide"
)

# --- CONEXIÓN DIRECTA A GOOGLE SHEETS ---
def conectar_gspread():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if "gcp_service_account" in st.secrets:
        credentials_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(
            credentials_dict, scopes=scope
        )
    else:
        st.error(
            "No se encontraron las credenciales 'gcp_service_account' en secrets.toml"
        )
        st.stop()
    client = gspread.authorize(creds)
    return client.open("ORGANIGRAMA_ZONA1")

try:
    spreadsheet = conectar_gspread()
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()

# --- SISTEMA DE SELECCIÓN DE ESCUELA (ESTILO TARJETA CENTRAL TIPO LOGIN) ---
if "escuela_seleccionada" not in st.session_state:
    st.session_state["escuela_seleccionada"] = None

if st.session_state["escuela_seleccionada"] is None:
    _, col_centro, _ = st.columns([1, 1.5, 1])
    with col_centro:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>🏫 Portal Escolar - Zona 1</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Sistema de Seguimiento y Control de Planteles</p>", unsafe_allow_html=True)
            st.markdown("---")
            
            # Opciones de las 12 escuelas con nombres exactos en mayúsculas como en Google Sheets
            opciones_escuelas = [f"ESCUELA {i}" for i in range(1, 13)]
            plantel_elegido = st.selectbox("🏫 Selecciona tu Plantel", opciones_escuelas)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Entrar al Panel", use_container_width=True):
                st.session_state["escuela_seleccionada"] = plantel_elegido
                st.rerun()
    st.stop()

# Una vez seleccionada la escuela, obtenemos su nombre
nombre_pestana_escuela = st.session_state["escuela_seleccionada"]

try:
    sheet_escuela = spreadsheet.worksheet(nombre_pestana_escuela)
except Exception as e:
    st.error(f"No se encontró la pestaña '{nombre_pestana_escuela}' en el archivo de Google Sheets. Por favor, verifícalo.")
    if st.button("🔄 Cambiar de Plantel"):
        st.session_state["escuela_seleccionada"] = None
        st.rerun()
    st.stop()

# --- BARRA LATERAL PARA CAMBIAR DE PLANTEL O SALIR ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/school.png", width=80)
    st.title("Portal Escolar")
    st.markdown(f"Conectado a: **{nombre_pestana_escuela}**")
    st.markdown("---")
    if st.button("🔄 Cambiar de Plantel", use_container_width=True):
        st.session_state["escuela_seleccionada"] = None
        st.rerun()

# --- CARGAR Y DEPURAR DATOS DE LA ESCUELA ---
def cargar_datos_escuela():
    data = sheet_escuela.get_all_records()
    if not data:
        df = pd.DataFrame(columns=["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado"])
    else:
        df = pd.DataFrame(data)
        df.columns = [str(col).strip() for col in df.columns]
        
        for col in ["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado"]:
            if col not in df.columns:
                match = [c for c in df.columns if col.lower().replace(" ", "") in c.lower().replace(" ", "")]
                if match:
                    df.rename(columns={match[0]: col}, inplace=True)
                else:
                    df[col] = ""
                    
        df["Fecha Inicio"] = df["Fecha Inicio"].astype(str).str.split("T").str[0].str.strip()
        
        col_fin_real = next((c for c in df.columns if "fin" in c.lower()), "Fecha Fin")
        if col_fin_real != "Fecha Fin":
            df.rename(columns={col_fin_real: "Fecha Fin"}, inplace=True)
            
        df["Fecha Fin"] = df["Fecha Fin"].astype(str).str.split("T").str[0].str.strip()
        df["Fecha Fin"] = df["Fecha Fin"].replace(["", "nan", "NaT", "None"], pd.NA)
        df["Fecha Fin"] = df["Fecha Fin"].fillna(df["Fecha Inicio"])
        
    return df

df_tareas_escuela = cargar_datos_escuela()

# --- FUNCIÓN AUXILIAR PARA FORMATEAR FECHAS A DD-MM-YY ---
def formatear_fecha_corta(fecha_val):
    if not fecha_val or str(fecha_val).strip() == "":
        return ""
    try:
        dt = pd.to_datetime(str(fecha_val).split("T")[0])
        return dt.strftime("%d-%m-%y")
    except:
        return str(fecha_val).split("T")[0]

# --- TÍTULO PRINCIPAL ---
st.title(f"🏫 Panel de Seguimiento - {nombre_pestana_escuela}")
st.markdown("Consulta tus actividades asignadas, revisa fechas límite y marca tu progreso de cumplimiento.")

hoy_date_obj = date.today()
hoy_dt = pd.Timestamp(hoy_date_obj).normalize()

if not df_tareas_escuela.empty:
    df_tareas_escuela["Fecha_Inicio_dt"] = pd.to_datetime(df_tareas_escuela["Fecha Inicio"].astype(str).str.split("T").str[0], errors='coerce').dt.normalize()
    df_tareas_escuela["Fecha_Fin_dt"] = pd.to_datetime(df_tareas_escuela["Fecha Fin"].astype(str).str.split("T").str[0], errors='coerce').dt.normalize()
    df_tareas_escuela["Fecha_Fin_dt"] = df_tareas_escuela["Fecha_Fin_dt"].fillna(df_tareas_escuela["Fecha_Inicio_dt"])
    
    # Filtrar por categorías de prioridad (Atrasadas y Pendientes hasta arriba)
    atrasadas_df = df_tareas_escuela[
        (df_tareas_escuela["Fecha_Fin_dt"] < hoy_dt) & 
        (df_tareas_escuela["Estado"].str.lower() != "completada")
    ]
    
    hoy_df = df_tareas_escuela[
        (df_tareas_escuela["Fecha_Inicio_dt"] <= hoy_dt) & 
        (df_tareas_escuela["Fecha_Fin_dt"] >= hoy_dt) & 
        (df_tareas_escuela["Estado"].str.lower() != "completada")
    ]

    futuras_df = df_tareas_escuela[
        (df_tareas_escuela["Fecha_Inicio_dt"] > hoy_dt) & 
        (df_tareas_escuela["Estado"].str.lower() != "completada")
    ]

    # --- 1. ACTIVIDADES ATRASADAS (MÁXIMA PRIORIDAD ARRIBA) ---
    if not atrasadas_df.empty:
        st.markdown("### ⚠️ Actividades Atrasadas")
        for idx, row in atrasadas_df.iterrows():
            orig_idx = row.name
            f_ini_raw = str(row["Fecha Inicio"]).split("T")[0]
            f_fin_raw = str(row["Fecha Fin"]).split("T")[0] if row["Fecha Fin"] else f_ini_raw
            f_ini_fmt = formatear_fecha_corta(f_ini_raw)
            f_fin_fmt = formatear_fecha_corta(f_fin_raw)
            
            rango_fechas = f"📅 Del {f_ini_fmt} al {f_fin_fmt}" if f_ini_raw != f_fin_raw else f"📅 {f_ini_fmt}"
            
            with st.container(border=True):
                col_p1, col_p2, col_p3 = st.columns([3.5, 1, 0.8])
                with col_p1:
                    st.markdown(f"**🏫 {row['Actividad']}** &nbsp;|&nbsp; *<small>{rango_fechas}</small>*", unsafe_allow_html=True)
                with col_p2:
                    st.markdown("🔴 Atrasada", unsafe_allow_html=True)
                with col_p3:
                    if st.button("✔️ Marcar Hecho", key=f"btn_esc_atrasada_{orig_idx}"):
                        sheet_escuela.update_cell(orig_idx + 2, 5, "Completada")
                        st.success("¡Completada!")
                        st.rerun()

    # --- 2. PENDIENTES DE HOY ---
    if not hoy_df.empty:
        st.markdown("### 🔔 Actividades para Hoy")
        for idx, row in hoy_df.iterrows():
            orig_idx = row.name
            f_ini_raw = str(row["Fecha Inicio"]).split("T")[0]
            f_fin_raw = str(row["Fecha Fin"]).split("T")[0] if row["Fecha Fin"] else f_ini_raw
            f_ini_fmt = formatear_fecha_corta(f_ini_raw)
            f_fin_fmt = formatear_fecha_corta(f_fin_raw)
            
            rango_fechas = f"📅 Del {f_ini_fmt} al {f_fin_fmt}" if f_ini_raw != f_fin_raw else f"📅 {f_ini_fmt}"
            
            with st.container(border=True):
                col_h1, col_h2, col_h3 = st.columns([3.5, 1, 0.8])
                with col_h1:
                    st.markdown(f"**🏫 {row['Actividad']}** &nbsp;|&nbsp; *<small>{rango_fechas}</small>*", unsafe_allow_html=True)
                with col_h2:
                    st.markdown("🟠 Pendiente Hoy", unsafe_allow_html=True)
                with col_h3:
                    if st.button("✔️ Marcar Hecho", key=f"btn_esc_hoy_{orig_idx}"):
                        sheet_escuela.update_cell(orig_idx + 2, 5, "Completada")
                        st.success("¡Completada!")
                        st.rerun()

    # --- 3. PRÓXIMAS ACTIVIDADES ---
    if not futuras_df.empty:
        st.markdown("### 🗓️ Próximas Actividades")
        for idx, row in futuras_df.iterrows():
            orig_idx = row.name
            f_ini_raw = str(row["Fecha Inicio"]).split("T")[0]
            f_fin_raw = str(row["Fecha Fin"]).split("T")[0] if row["Fecha Fin"] else f_ini_raw
            f_ini_fmt = formatear_fecha_corta(f_ini_raw)
            f_fin_fmt = formatear_fecha_corta(f_fin_raw)
            
            rango_fechas = f"📅 Del {f_ini_fmt} al {f_fin_fmt}" if f_ini_raw != f_fin_raw else f"📅 {f_ini_fmt}"
            
            with st.container(border=True):
                col_f1, col_f2, col_f3 = st.columns([3.5, 1, 0.8])
                with col_f1:
                    st.markdown(f"**🏫 {row['Actividad']}** &nbsp;|&nbsp; *<small>{rango_fechas}</small>*", unsafe_allow_html=True)
                with col_f2:
                    st.markdown("🔵 Programada", unsafe_allow_html=True)
                with col_f3:
                    if st.button("✔️ Marcar Hecho", key=f"btn_esc_futura_{orig_idx}"):
                        sheet_escuela.update_cell(orig_idx + 2, 5, "Completada")
                        st.success("¡Completada!")
                        st.rerun()

    st.markdown("---")

    # --- CALENDARIO ESCOLAR (VISTAS MES Y AGENDA QUINCENAL) ---
    st.markdown("### 📅 Calendario de Actividades del Plantel")

    st.markdown("""
        <style>
        .fc-list-event-time {
            display: none !important;
        }
        .fc-view-harness {
            min-height: 600px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    calendar_events = []
    for _, row in df_tareas_escuela.iterrows():
        f_ini_raw = str(row["Fecha Inicio"]).split("T")[0]
        f_fin_raw = str(row["Fecha Fin"]).split("T")[0] if row["Fecha Fin"] else f_ini_raw
        
        try:
            f_ini_dt = pd.to_datetime(f_ini_raw).strftime("%Y-%m-%d")
            f_fin_dt = (pd.to_datetime(f_fin_raw) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        except:
            f_ini_dt = f_ini_raw
            f_fin_dt = f_fin_raw

        estado_evt = str(row["Estado"]).strip().lower()
        color_evento = "#28a745" if estado_evt == "completada" else "#3788d8"

        calendar_events.append({
            "title": f"🏫 {row['Actividad']}",
            "start": f_ini_dt,
            "end": f_fin_dt,
            "color": color_evento,
            "allDay": True
        })

    calendar_options = {
        "editable": False,
        "selectable": True,
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "listFortnight,dayGridMonth"
        },
        "views": {
            "listFortnight": {
                "type": "list",
                "duration": {"days": 15},
                "buttonText": "Agenda Quincenal"
            },
            "dayGridMonth": {
                "buttonText": "Mes"
            }
        },
        "initialView": "listFortnight",
        "locale": "es",
    }

    calendar(events=calendar_events, options=calendar_options)

else:
    st.info("No hay actividades registradas en la hoja de esta escuela.")


