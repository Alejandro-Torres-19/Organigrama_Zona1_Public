from datetime import datetime, date
import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import plotly.graph_objects as go
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
    sheet_principal = spreadsheet.get_worksheet(0) # Hoja 1 del Admin (General)
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()

# --- CARGAR USUARIOS DESDE LA PESTAÑA 'INICIOS SESIÓN' ---
def cargar_credenciales():
    try:
        sheet_cred = spreadsheet.worksheet("INICIOS SESIÓN")
        data_cred = sheet_cred.get_all_records()
        if data_cred:
            df_cred = pd.DataFrame(data_cred)
            df_cred.columns = [str(col).strip().upper() for col in df_cred.columns]
            return df_cred
    except Exception as e:
        st.error(f"No se pudo cargar la pestaña 'INICIOS SESIÓN': {e}")
    return pd.DataFrame()

df_usuarios = cargar_credenciales()

# --- SISTEMA DE LOGIN CON CCT Y CONTRASEÑA ---
if "cct_autenticado" not in st.session_state:
    st.session_state["cct_autenticado"] = None

if st.session_state["cct_autenticado"] is None:
    _, col_centro, _ = st.columns([1, 1.5, 1])
    with col_centro:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>🏫 Portal Escolar - Zona 1</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Ingresa tus credenciales para acceder</p>", unsafe_allow_html=True)
            st.markdown("---")
            
            cct_input = st.text_input("🏫 CCT (Clave de Centro de Trabajo)", placeholder="Ej. 15DES00114").strip().upper()
            pass_input = st.text_input("🔑 Contraseña", type="password", placeholder="Ingresa tu contraseña").strip()
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Iniciar Sesión", use_container_width=True):
                if cct_input and pass_input:
                    if not df_usuarios.empty and "CCT" in df_usuarios.columns and "CONTRASEÑA" in df_usuarios.columns:
                        usuario_valido = df_usuarios[
                            (df_usuarios["CCT"].astype(str).str.strip().str.upper() == cct_input) & 
                            (df_usuarios["CONTRASEÑA"].astype(str).str.strip() == pass_input)
                        ]
                        if not usuario_valido.empty:
                            st.session_state["cct_autenticado"] = cct_input
                            st.success("¡Acceso correcto!")
                            st.rerun()
                        else:
                            st.error("❌ CCT o Contraseña incorrectos. Verifica tus datos.")
                    else:
                        st.error("No se encontró la columna 'CCT' o 'CONTRASEÑA' en la hoja 'INICIOS SESIÓN'.")
                else:
                    st.warning("Por favor, completa ambos campos.")
    st.stop()

# CCT del usuario que inició sesión
cct_usuario = st.session_state["cct_autenticado"]

try:
    sheet_escuela = spreadsheet.worksheet(cct_usuario)
except Exception as e:
    st.error(f"No se encontró la pestaña '{cct_usuario}' en el archivo de Google Sheets. Por favor, verifícalo.")
    if st.button("🔄 Cerrar Sesión"):
        st.session_state["cct_autenticado"] = None
        st.rerun()
    st.stop()

# --- BARRA LATERAL: NAVEGACIÓN Y CERRAR SESIÓN ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/school.png", width=80)
    st.title("Portal Escolar")
    st.markdown(f"Plantel: **{cct_usuario}**")
    st.markdown("---")
    
    menu_portal = st.radio(
        "Navegación",
        ["📌 Actividades y Calendario", "✅ Mis Tareas Completadas", "📊 Avance de la Zona"]
    )
    
    st.markdown("---")
    if st.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state["cct_autenticado"] = None
        st.rerun()

# --- CARGAR TAREAS PÚBLICAS Y SINCRO CON PESTAÑA DEL CCT ---
def cargar_datos_sincronizados():
    data_admin = sheet_principal.get_all_records()
    if not data_admin:
        return pd.DataFrame(columns=["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado", "Fila_Admin"])
    
    df_admin = pd.DataFrame(data_admin)
    df_admin.columns = [str(col).strip() for col in df_admin.columns]
    
    for col in ["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado"]:
        if col not in df_admin.columns:
            match = [c for c in df_admin.columns if col.lower().replace(" ", "") in c.lower().replace(" ", "")]
            if match:
                df_admin.rename(columns={match[0]: col}, inplace=True)
            else:
                df_admin[col] = ""

    def es_publica(val):
        v = str(val).strip().lower()
        return v in ["false", "no", "0", "f"]

    df_publicas = df_admin[df_admin["Privado"].apply(es_publica)].copy()
    
    if df_publicas.empty:
        return pd.DataFrame(columns=["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado", "Fila_Admin"])

    df_publicas["Fila_Admin"] = df_publicas.index + 2

    data_escuela = sheet_escuela.get_all_records()
    df_escuela_registros = pd.DataFrame(data_escuela) if data_escuela else pd.DataFrame(columns=["Actividad", "Estado"])
    
    if not df_escuela_registros.empty:
        df_escuela_registros.columns = [str(col).strip() for col in df_escuela_registros.columns]
        estatus_map = {}
        for _, row_esc in df_escuela_registros.iterrows():
            act_nombre = str(row_esc.get("Actividad", "")).strip()
            est_val = str(row_esc.get("Estado", "Pendiente")).strip()
            estatus_map[act_nombre] = est_val
        
        df_publicas["Estado"] = df_publicas["Actividad"].apply(lambda x: estatus_map.get(str(x).strip(), "Pendiente"))
    else:
        df_publicas["Estado"] = "Pendiente"

    df_publicas["Fecha Inicio"] = df_publicas["Fecha Inicio"].astype(str).str.split("T").str[0].str.strip()
    col_fin_real = next((c for c in df_publicas.columns if "fin" in c.lower()), "Fecha Fin")
    if col_fin_real != "Fecha Fin":
        df_publicas.rename(columns={col_fin_real: "Fecha Fin"}, inplace=True)
    df_publicas["Fecha Fin"] = df_publicas["Fecha Fin"].astype(str).str.split("T").str[0].str.strip()
    df_publicas["Fecha Fin"] = df_publicas["Fecha Fin"].replace(["", "nan", "NaT", "None"], pd.NA)
    df_publicas["Fecha Fin"] = df_publicas["Fecha Fin"].fillna(df_publicas["Fecha Inicio"])

    return df_publicas

df_tareas_escuela = cargar_datos_sincronizados()

def actualizar_estado_escuela(nombre_actividad, nuevo_estado, f_inicio, f_fin):
    data_esc = sheet_escuela.get_all_records()
    df_esc = pd.DataFrame(data_esc) if data_esc else pd.DataFrame()
    
    encontrado = False
    if not df_esc.empty and "Actividad" in df_esc.columns:
        for idx, row in df_esc.iterrows():
            if str(row["Actividad"]).strip() == str(nombre_actividad).strip():
                sheet_escuela.update_cell(idx + 2, 5, nuevo_estado)
                encontrado = True
                break
                
    if not encontrado:
        sheet_escuela.append_row([nombre_actividad, f_inicio, f_fin, "FALSE", nuevo_estado])

def formatear_fecha_corta(fecha_val):
    if not fecha_val or str(fecha_val).strip() == "":
        return ""
    try:
        dt = pd.to_datetime(str(fecha_val).split("T")[0])
        return dt.strftime("%d-%m-%y")
    except:
        return str(fecha_val).split("T")[0]

hoy_date_obj = date.today()
hoy_dt = pd.Timestamp(hoy_date_obj).normalize()

# --- FUNCIÓN PARA GENERAR GRÁFICA CIRCULAR TIPO DONA ---
def crear_grafica_dona(porcentaje, titulo_centro=""):
    completado = porcentaje
    pendiente = 100 - porcentaje
    
    fig = go.Figure(data=[go.Pie(
        values=[completado, pendiente if completado > 0 else 100],
        labels=['Completado', 'Pendiente'],
        hole=0.6,
        marker=dict(colors=['#198754', '#dc3545']),
        textinfo='none',
        hoverinfo='none'
    )])
    
    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=220,
        annotations=[dict(
            text=f"<b>{completado}%</b><br><span style='font-size:12px; color:gray;'>{titulo_centro}</span>",
            x=0.5, y=0.5, font_size=18, showarrow=False
        )]
    )
    return fig


# ==========================================
# SECCIÓN 1: ACTIVIDADES Y CALENDARIO
# ==========================================
if menu_portal == "📌 Actividades y Calendario":
    st.title(f"🏫 Panel de Seguimiento - {cct_usuario}")
    st.markdown("Consulta tus actividades públicas asignadas por la supervisión, revisa fechas límite y marca tu progreso.")

    if not df_tareas_escuela.empty:
        df_tareas_escuela["Fecha_Inicio_dt"] = pd.to_datetime(df_tareas_escuela["Fecha Inicio"].astype(str).str.split("T").str[0], errors='coerce').dt.normalize()
        df_tareas_escuela["Fecha_Fin_dt"] = pd.to_datetime(df_tareas_escuela["Fecha Fin"].astype(str).str.split("T").str[0], errors='coerce').dt.normalize()
        df_tareas_escuela["Fecha_Fin_dt"] = df_tareas_escuela["Fecha_Fin_dt"].fillna(df_tareas_escuela["Fecha_Inicio_dt"])
        
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

        # --- ACTIVIDADES ATRASADAS ---
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
                            actualizar_estado_escuela(row["Actividad"], "Completada", row["Fecha Inicio"], row["Fecha Fin"])
                            st.success("¡Completada!")
                            st.rerun()

        # --- PENDIENTES DE HOY ---
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
                            actualizar_estado_escuela(row["Actividad"], "Completada", row["Fecha Inicio"], row["Fecha Fin"])
                            st.success("¡Completada!")
                            st.rerun()

        # --- PRÓXIMAS ACTIVIDADES ---
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
                            actualizar_estado_escuela(row["Actividad"], "Completada", row["Fecha Inicio"], row["Fecha Fin"])
                            st.success("¡Completada!")
                            st.rerun()

        st.markdown("---")

        # --- CALENDARIO ESCOLAR ---
        st.markdown("### 📅 Calendario de Actividades del Plantel")
        st.markdown("""
            <style>
            .fc-list-event-time { display: none !important; }
            .fc-view-harness { min-height: 600px !important; }
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
                "listFortnight": { "type": "list", "duration": {"days": 15}, "buttonText": "Agenda Quincenal" },
                "dayGridMonth": { "buttonText": "Mes" }
            },
            "initialView": "listFortnight",
            "locale": "es",
        }
        calendar(events=calendar_events, options=calendar_options)
    else:
        st.info("No hay actividades públicas registradas por el administrador en este momento.")


# ==========================================
# SECCIÓN 2: MIS TAREAS COMPLETADAS
# ==========================================
elif menu_portal == "✅ Mis Tareas Completadas":
    st.title(f"✅ Historial de Tareas Completadas - {cct_usuario}")
    st.markdown("Consulta todas las actividades que tu plantel ya ha concluido y reportado.")

    completadas_escuela_df = df_tareas_escuela[df_tareas_escuela["Estado"].str.lower() == "completada"]

    if not completadas_escuela_df.empty:
        for idx, row in completadas_escuela_df.iterrows():
            f_ini = formatear_fecha_corta(str(row["Fecha Inicio"]).split("T")[0])
            f_fin = formatear_fecha_corta(str(row["Fecha Fin"]).split("T")[0])
            rango = f"📅 Del {f_ini} al {f_fin}" if f_ini != f_fin else f"📅 {f_ini}"
            
            with st.container(border=True):
                col_c1, col_c2 = st.columns([3.5, 1])
                with col_c1:
                    st.markdown(f"#### ✅ {row['Actividad']}")
                    st.markdown(f"*<small>{rango}</small>*", unsafe_allow_html=True)
                with col_c2:
                    st.markdown("<br>**Estatus:** 🟢 Completada", unsafe_allow_html=True)
    else:
        st.info("Aún no tienes tareas marcadas como completadas. ¡Comienza a realizarlas desde tu panel principal!")


# ==========================================
# SECCIÓN 3: AVANCE DE LA ZONA
# ==========================================
elif menu_portal == "📊 Avance de la Zona":
    st.title("📊 Indicadores de Avance - Zona 1")
    st.markdown("Monitorea tu rendimiento y el de los demás planteles de la zona.")

    lista_ccts = df_usuarios["CCT"].astype(str).str.strip().unique().tolist() if not df_usuarios.empty and "CCT" in df_usuarios.columns else []

    avances_zona = []
    for cct_item in lista_ccts:
        porcentaje_esc = 0
        try:
            ws_tmp = spreadsheet.worksheet(cct_item)
            dat_tmp = ws_tmp.get_all_records()
            if dat_tmp:
                df_tmp = pd.DataFrame(dat_tmp)
                total_t = len(df_tmp)
                if total_t > 0 and "Estado" in df_tmp.columns:
                    comp_t = len(df_tmp[df_tmp["Estado"].str.lower() == "completada"])
                    porcentaje_esc = int((comp_t / total_t) * 100)
        except Exception:
            pass
        
        is_current = (cct_item == cct_usuario)
        avances_zona.append({"Escuela": cct_item, "Porcentaje": porcentaje_esc, "Es_Actual": is_current})

    df_avances_zona = pd.DataFrame(avances_zona)
    
    mi_porcentaje = 0
    if not df_avances_zona.empty and any(df_avances_zona["Es_Actual"]):
        mi_porcentaje = df_avances_zona[df_avances_zona["Es_Actual"]]["Porcentaje"].values[0]

    # --- GRÁFICA CIRCULAR PRINCIPAL (TU PLANTEL) ---
    st.subheader(f"🎯 Tu Progreso Actual: {cct_usuario}")
    
    col_g1, col_g2 = st.columns([1.2, 2.8])
    with col_g1:
        fig_mi_escuela = crear_grafica_dona(mi_porcentaje, "avance general")
        st.plotly_chart(fig_mi_escuela, use_container_width=True)
    with col_g2:
        st.markdown("<br>", unsafe_allow_html=True)
        if mi_porcentaje == 100:
            st.success("🎉 ¡Felicidades! Has alcanzado el 100% de cumplimiento en tus actividades asignadas.")
        elif mi_porcentaje >= 70:
            st.warning("🔥 ¡Excelente ritmo! Estás muy cerca de la meta establecida.")
        else:
            st.info("💪 ¡Aún hay tiempo! Revisa tus pendientes en el panel principal y ponte al corriente.")

    st.markdown("---")

    # --- SECCIÓN DE AVANCE DE LA ZONA 1 (GALERÍA DE GRÁFICAS CIRCULARES) ---
    st.markdown("### 📈 Avance de la Zona 1")
    st.markdown("Estatus de cumplimiento de todos los planteles de la zona:")

    cols = st.columns(3)
    for idx, row in df_avances_zona.iterrows():
        esc_nombre = row["Escuela"]
        esc_porc = row["Porcentaje"]
        
        with cols[idx % 3]:
            with st.container(border=True):
                titulo_etiqueta = f"⭐ {esc_nombre}" if esc_nombre == cct_usuario else esc_nombre
                fig_dona = crear_grafica_dona(esc_porc, titulo_etiqueta)
                st.plotly_chart(fig_dona, use_container_width=True, key=f"esc_dona_{idx}")
