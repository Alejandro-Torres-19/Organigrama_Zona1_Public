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
    sheet_principal = spreadsheet.get_worksheet(0) # Hoja 1 del Admin (General)
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
            
            opciones_escuelas = [f"ESCUELA {i}" for i in range(1, 13)]
            plantel_elegido = st.selectbox("🏫 Selecciona tu Plantel", opciones_escuelas)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Entrar al Panel", use_container_width=True):
                st.session_state["escuela_seleccionada"] = plantel_elegido
                st.rerun()
    st.stop()

# Nombre de la pestaña de la escuela seleccionada
nombre_pestana_escuela = st.session_state["escuela_seleccionada"]

try:
    sheet_escuela = spreadsheet.worksheet(nombre_pestana_escuela)
except Exception as e:
    st.error(f"No se encontró la pestaña '{nombre_pestana_escuela}' en el archivo de Google Sheets. Por favor, verifícalo.")
    if st.button("🔄 Cambiar de Plantel"):
        st.session_state["escuela_seleccionada"] = None
        st.rerun()
    st.stop()

# --- BARRA LATERAL: NAVEGACIÓN Y CAMBIO DE PLANTEL ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/school.png", width=80)
    st.title("Portal Escolar")
    st.markdown(f"Conectado a: **{nombre_pestana_escuela}**")
    st.markdown("---")
    
    menu_portal = st.radio(
        "Navegación",
        ["📌 Actividades y Calendario", "✅ Mis Tareas Completadas", "📊 Avance y Competencia Zona"]
    )
    
    st.markdown("---")
    if st.button("🔄 Cambiar de Plantel", use_container_width=True):
        st.session_state["escuela_seleccionada"] = None
        st.rerun()

# --- CARGAR TAREAS PÚBLICAS DE LA HOJA PRINCIPAL Y CRUZARLAS CON EL ESTATUS DE LA ESCUELA ---
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

# ==========================================
# SECCIÓN 1: ACTIVIDADES Y CALENDARIO
# ==========================================
if menu_portal == "📌 Actividades y Calendario":
    st.title(f"🏫 Panel de Seguimiento - {nombre_pestana_escuela}")
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
    st.title(f"✅ Historial de Tareas Completadas - {nombre_pestana_escuela}")
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
# SECCIÓN 3: AVANCE Y COMPETENCIA ZONA
# ==========================================
elif menu_portal == "📊 Avance y Competencia Zona":
    st.title("📊 Indicadores de Avance y Competencia - Zona 1")
    st.markdown("Compara tu rendimiento con el de los demás planteles y mantén el liderazgo en la zona.")

    # Calcular porcentajes de todas las escuelas en tiempo real
    avances_zona = []
    for i in range(1, 13):
        p_name = f"ESCUELA {i}"
        porcentaje_esc = 0
        try:
            ws_tmp = spreadsheet.worksheet(p_name)
            dat_tmp = ws_tmp.get_all_records()
            if dat_tmp:
                df_tmp = pd.DataFrame(dat_tmp)
                total_t = len(df_tmp)
                if total_t > 0 and "Estado" in df_tmp.columns:
                    comp_t = len(df_tmp[df_tmp["Estado"].str.lower() == "completada"])
                    porcentaje_esc = int((comp_t / total_t) * 100)
        except Exception:
            pass
        
        is_current = (p_name == nombre_pestana_escuela)
        avances_zona.append({"Escuela": p_name, "Porcentaje": porcentaje_esc, "Es_Actual": is_current})

    df_avances_zona = pd.DataFrame(avances_zona)

    # Obtener el porcentaje de la escuela actual
    mi_porcentaje = df_avances_zona[df_avances_zona["Es_Actual"]]["Porcentaje"].values[0]

    # --- MÉTRICA / TARJETA PRINCIPAL DEL PLANTEL ---
    st.subheader(f"🎯 Tu Progreso Actual: {nombre_pestana_escuela}")
    
    col_m1, col_m2 = st.columns([1.5, 2.5])
    with col_m1:
        st.metric(label="Porcentaje de Cumplimiento", value=f"{mi_porcentaje}%")
    with col_m2:
        st.progress(mi_porcentaje / 100)
        if mi_porcentaje == 100:
            st.success("🎉 ¡Felicidades! Has alcanzado el 100% de cumplimiento.")
        elif mi_porcentaje >= 70:
            st.warning("🔥 ¡Excelente ritmo! Estás muy cerca de la meta.")
        else:
            st.info("💪 ¡Aún hay tiempo! Revisa tus pendientes y ponte al corriente.")

    st.markdown("---")

    # --- SECCIÓN DE COMPETENCIA SANA (GRÁFICA DE BARRAS DE LA ZONA) ---
    st.markdown("### 🏆 Tabla de Posiciones y Avance de la Zona 1")
    st.markdown("Visualiza el estatus de cumplimiento de todos los planteles participantes:")

    # Ordenar de mayor a menor porcentaje para la competencia sana
    df_ranking = df_avances_zona.sort_values(by="Porcentaje", ascending=False).reset_index(drop=True)

    # Mostrar gráfico de barras horizontales limpio
    st.bar_chart(df_ranking.set_index("Escuela")[["Porcentaje"]], horizontal=True)

    # Tabla detallada transparente
    st.markdown("#### Detalle por Plantel")
    
    # Destacar visualmente la fila del plantel actual en la tabla
    def destacar_actual(row):
        if row["Escuela"] == nombre_pestana_escuela:
            return ['background-color: #d4edda; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(
        df_ranking[["Escuela", "Porcentaje"]].style.apply(destacar_actual, axis=1),
        use_container_width=True,
        hide_index=True
    )
