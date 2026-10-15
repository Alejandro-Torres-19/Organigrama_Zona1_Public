import hashlib
import hmac
import time
from datetime import date

import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# Si es True, las actividades publicas que el admin ya movio a "Completadas"
# tambien cuentan en el total contra el que se mide el avance de cada escuela.
INCLUIR_HISTORIAL_EN_AVANCE = False

MAX_INTENTOS = 5      # intentos de login fallidos por sesion
BLOQUEO_SEGUNDOS = 60

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Portal Escolar - Zona 1", page_icon="🏫", layout="wide")


# ======================= HELPERS (sin dependencia de la UI) =======================
def es_publica(val):
    return str(val).strip().lower() in ["false", "no", "0", "f"]


def _norm_fecha(v):
    return str(v).split("T")[0].strip()


def formatear_fecha_corta(fecha_val):
    if not fecha_val or str(fecha_val).strip() == "":
        return ""
    try:
        dt = pd.to_datetime(str(fecha_val).split("T")[0])
        return dt.strftime("%d-%m-%y")
    except Exception:
        return str(fecha_val).split("T")[0]


def clave_tarea(actividad, fecha_inicio):
    """Identifica una actividad por nombre + fecha de inicio (el nombre solo puede repetirse)."""
    return f"{str(actividad).strip()}|{_norm_fecha(fecha_inicio)}"


def hash_fila(row):
    base = f"{row['Actividad']}|{row['Fecha Inicio']}|{row['Fecha Fin']}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()[:10]


def key_tarea(prefijo, row, vistos):
    h = hash_fila(row)
    n = vistos.get(h, 0)
    vistos[h] = n + 1
    return f"{prefijo}_{h}_{n}"


def verificar_password(ingresada, guardada):
    """Acepta contraseña en texto (formato actual) o hash 'pbkdf2$iteraciones$salt_hex$hash_hex'."""
    ingresada = str(ingresada).strip()
    guardada = str(guardada).strip()
    if guardada.startswith("pbkdf2$"):
        try:
            _, it, salt_hex, hash_hex = guardada.split("$")
            calc = hashlib.pbkdf2_hmac(
                "sha256", ingresada.encode("utf-8"), bytes.fromhex(salt_hex), int(it)
            ).hex()
            return hmac.compare_digest(calc, hash_hex.lower())
        except Exception:
            return False
    return hmac.compare_digest(guardada.encode("utf-8"), ingresada.encode("utf-8"))


def calcular_avance_zona_core(spreadsheet, sheet_principal, lista_ccts, incluir_historial):
    """Avance por escuela = actividades PUBLICAS completadas por la escuela / total de
    actividades publicas. Una escuela sin filas en su pestana cuenta como 0 completadas
    (antes el denominador era el numero de filas de su pestana, lo que inflaba el %)."""
    hojas = {ws.title: ws for ws in spreadsheet.worksheets()}

    publicas = []
    fuentes = [sheet_principal]
    if incluir_historial and "Completadas" in hojas:
        fuentes.append(hojas["Completadas"])
    vistas = set()
    for ws in fuentes:
        for r in ws.get_all_records():
            actividad = str(r.get("Actividad", "")).strip()
            if not actividad or not es_publica(r.get("Privado", "")):
                continue
            f_ini = _norm_fecha(r.get("Fecha Inicio", ""))
            f_fin = _norm_fecha(r.get("Fecha Fin", "")) or f_ini
            clave = (clave_tarea(actividad, f_ini), f_fin)
            if clave in vistas:
                continue
            vistas.add(clave)
            publicas.append({"Actividad": actividad, "Fecha Inicio": f_ini, "Fecha Fin": f_fin})

    avances, detalles = [], {}
    for cct in lista_ccts:
        estatus = {}
        ws = hojas.get(cct)
        if ws is not None:
            try:
                for r in ws.get_all_records():
                    estatus[clave_tarea(r.get("Actividad", ""), r.get("Fecha Inicio", ""))] = (
                        str(r.get("Estado", "Pendiente")).strip().lower()
                    )
            except Exception:
                pass
        filas = []
        for t in publicas:
            hecho = estatus.get(clave_tarea(t["Actividad"], t["Fecha Inicio"])) == "completada"
            filas.append({**t, "Estado": "Completada" if hecho else "Pendiente"})
        df_esc = pd.DataFrame(filas, columns=["Actividad", "Fecha Inicio", "Fecha Fin", "Estado"])
        total = len(df_esc)
        completadas = int((df_esc["Estado"] == "Completada").sum()) if total else 0
        porcentaje = int(round(100 * completadas / total)) if total else 100
        avances.append({"Escuela": cct, "Porcentaje": porcentaje})
        detalles[cct] = df_esc
    return avances, detalles
# ======================= FIN HELPERS =======================


# --- CONEXIÓN DIRECTA A GOOGLE SHEETS CON CACHÉ ---
@st.cache_resource
def conectar_gspread():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if "gcp_service_account" in st.secrets:
        credentials_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    else:
        st.error("No se encontraron las credenciales 'gcp_service_account' en secrets.toml")
        st.stop()
    client = gspread.authorize(creds)
    return client.open("ORGANIGRAMA_ZONA1")


try:
    spreadsheet = conectar_gspread()
    sheet_principal = spreadsheet.get_worksheet(0)  # Hoja 1 del Admin (General)
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()


# --- CARGAR USUARIOS DESDE 'INICIOS SESIÓN' CON CACHÉ (5 MINUTOS) ---
@st.cache_data(ttl=300)
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
            st.markdown(
                "<p style='text-align: center; color: gray;'>Ingresa tus credenciales para acceder</p>",
                unsafe_allow_html=True,
            )
            st.markdown("---")

            cct_input = st.text_input(
                "🏫 CCT (Clave de Centro de Trabajo)", placeholder="Ej. 15DES00114"
            ).strip().upper()
            pass_input = st.text_input(
                "🔑 Contraseña", type="password", placeholder="Ingresa tu contraseña"
            ).strip()

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Iniciar Sesión", use_container_width=True):
                restante = int(st.session_state.get("bloqueado_hasta", 0) - time.time())
                if restante > 0:
                    st.error(f"Demasiados intentos. Espera {restante} segundos.")
                elif cct_input and pass_input:
                    if (
                        not df_usuarios.empty
                        and "CCT" in df_usuarios.columns
                        and "CONTRASEÑA" in df_usuarios.columns
                    ):
                        filas = df_usuarios[df_usuarios["CCT"].astype(str).str.strip().str.upper() == cct_input]
                        valido = any(verificar_password(pass_input, p) for p in filas["CONTRASEÑA"])
                        if valido:
                            st.session_state["cct_autenticado"] = cct_input
                            st.session_state["intentos"] = 0
                            st.success("¡Acceso correcto!")
                            st.rerun()
                        else:
                            st.session_state["intentos"] = st.session_state.get("intentos", 0) + 1
                            if st.session_state["intentos"] >= MAX_INTENTOS:
                                st.session_state["bloqueado_hasta"] = time.time() + BLOQUEO_SEGUNDOS
                                st.session_state["intentos"] = 0
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
except Exception:
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
        ["📌 Actividades y Calendario", "✅ Mis Tareas Completadas", "📊 Avance de la Zona"],
    )

    st.markdown("---")
    if st.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state["cct_autenticado"] = None
        st.rerun()


# --- CARGAR TAREAS PÚBLICAS Y SINCRO CON PESTAÑA DEL CCT (CACHÉ DE 30 SEG) ---
@st.cache_data(ttl=30)
def cargar_datos_sincronizados(cct):
    columnas = ["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado", "Fila_Admin"]
    data_admin = sheet_principal.get_all_records()
    if not data_admin:
        return pd.DataFrame(columns=columnas)

    df_admin = pd.DataFrame(data_admin)
    df_admin.columns = [str(col).strip() for col in df_admin.columns]

    for col in ["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado"]:
        if col not in df_admin.columns:
            match = [c for c in df_admin.columns if col.lower().replace(" ", "") in c.lower().replace(" ", "")]
            if match:
                df_admin.rename(columns={match[0]: col}, inplace=True)
            else:
                df_admin[col] = ""

    df_publicas = df_admin[df_admin["Privado"].apply(es_publica)].copy()
    if df_publicas.empty:
        return pd.DataFrame(columns=columnas)

    df_publicas["Fila_Admin"] = df_publicas.index + 2

    df_publicas["Fecha Inicio"] = df_publicas["Fecha Inicio"].astype(str).str.split("T").str[0].str.strip()
    col_fin_real = next((c for c in df_publicas.columns if "fin" in c.lower()), "Fecha Fin")
    if col_fin_real != "Fecha Fin":
        df_publicas.rename(columns={col_fin_real: "Fecha Fin"}, inplace=True)
    df_publicas["Fecha Fin"] = df_publicas["Fecha Fin"].astype(str).str.split("T").str[0].str.strip()
    df_publicas["Fecha Fin"] = df_publicas["Fecha Fin"].replace(["", "nan", "NaT", "None"], pd.NA)
    df_publicas["Fecha Fin"] = df_publicas["Fecha Fin"].fillna(df_publicas["Fecha Inicio"])

    # Estatus de ESTA escuela, identificado por (actividad + fecha de inicio)
    estatus_map = {}
    try:
        for r in spreadsheet.worksheet(cct).get_all_records():
            estatus_map[clave_tarea(r.get("Actividad", ""), r.get("Fecha Inicio", ""))] = str(
                r.get("Estado", "Pendiente")
            ).strip()
    except Exception:
        pass

    df_publicas["Estado"] = df_publicas.apply(
        lambda r: estatus_map.get(clave_tarea(r["Actividad"], r["Fecha Inicio"]), "Pendiente"), axis=1
    )
    return df_publicas


df_tareas_escuela = cargar_datos_sincronizados(cct_usuario)


@st.cache_data(ttl=60)
def calcular_avance_zona(lista_ccts):
    return calcular_avance_zona_core(
        spreadsheet, sheet_principal, list(lista_ccts), INCLUIR_HISTORIAL_EN_AVANCE
    )


def actualizar_estado_escuela(nombre_actividad, nuevo_estado, f_inicio, f_fin):
    clave = clave_tarea(nombre_actividad, f_inicio)
    filas = sheet_escuela.get_all_values()
    for n, f in enumerate(filas[1:], start=2):
        if len(f) >= 2 and clave_tarea(f[0], f[1]) == clave:
            sheet_escuela.update_cell(n, 5, nuevo_estado)
            break
    else:
        sheet_escuela.append_row(
            [str(nombre_actividad).strip(), _norm_fecha(f_inicio), _norm_fecha(f_fin), "FALSE", nuevo_estado]
        )
    # Limpiar caché para reflejar el cambio de inmediato
    st.cache_data.clear()


def render_tarjeta_escuela(row, prefijo, etiqueta, vistos):
    f_ini_raw = _norm_fecha(row["Fecha Inicio"])
    f_fin_raw = _norm_fecha(row["Fecha Fin"]) if row["Fecha Fin"] else f_ini_raw
    f_ini_fmt = formatear_fecha_corta(f_ini_raw)
    f_fin_fmt = formatear_fecha_corta(f_fin_raw)
    rango_fechas = f"📅 Del {f_ini_fmt} al {f_fin_fmt}" if f_ini_raw != f_fin_raw else f"📅 {f_ini_fmt}"
    k = key_tarea(prefijo, row, vistos)

    with st.container(border=True):
        c1, c2, c3 = st.columns([3.5, 1, 0.8])
        with c1:
            st.markdown(
                f"**🏫 {row['Actividad']}** &nbsp;|&nbsp; *<small>{rango_fechas}</small>*",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(etiqueta, unsafe_allow_html=True)
        with c3:
            if st.button("✔️ Marcar Hecho", key=f"btn_{k}"):
                actualizar_estado_escuela(row["Actividad"], "Completada", row["Fecha Inicio"], row["Fecha Fin"])
                st.success("¡Completada!")
                st.rerun()


hoy_dt = pd.Timestamp(date.today()).normalize()


# --- FUNCIÓN PARA GENERAR GRÁFICA CIRCULAR TIPO DONA ---
def crear_grafica_dona(porcentaje, titulo_centro=""):
    completado = porcentaje
    pendiente = 100 - porcentaje

    fig = go.Figure(
        data=[
            go.Pie(
                values=[completado, pendiente if completado > 0 else 100],
                labels=["Completado", "Pendiente"],
                hole=0.6,
                marker=dict(colors=["#198754", "#dc3545"]),
                textinfo="none",
                hoverinfo="none",
            )
        ]
    )

    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=220,
        annotations=[
            dict(
                text=f"<b>{completado}%</b><br><span style='font-size:12px; color:gray;'>{titulo_centro}</span>",
                x=0.5,
                y=0.5,
                font_size=18,
                showarrow=False,
            )
        ],
    )
    return fig


# ==========================================
# SECCIÓN 1: ACTIVIDADES Y CALENDARIO
# ==========================================
if menu_portal == "📌 Actividades y Calendario":
    st.title(f"🏫 Panel de Seguimiento - {cct_usuario}")
    st.markdown(
        "Consulta tus actividades públicas asignadas por la supervisión, revisa fechas límite y marca tu progreso."
    )

    if not df_tareas_escuela.empty:
        df_tareas_escuela["Fecha_Inicio_dt"] = pd.to_datetime(
            df_tareas_escuela["Fecha Inicio"].astype(str).str.split("T").str[0], errors="coerce"
        ).dt.normalize()
        df_tareas_escuela["Fecha_Fin_dt"] = pd.to_datetime(
            df_tareas_escuela["Fecha Fin"].astype(str).str.split("T").str[0], errors="coerce"
        ).dt.normalize()
        df_tareas_escuela["Fecha_Fin_dt"] = df_tareas_escuela["Fecha_Fin_dt"].fillna(
            df_tareas_escuela["Fecha_Inicio_dt"]
        )

        no_completada = df_tareas_escuela["Estado"].str.lower() != "completada"
        atrasadas_df = df_tareas_escuela[(df_tareas_escuela["Fecha_Fin_dt"] < hoy_dt) & no_completada]
        hoy_df = df_tareas_escuela[
            (df_tareas_escuela["Fecha_Inicio_dt"] <= hoy_dt)
            & (df_tareas_escuela["Fecha_Fin_dt"] >= hoy_dt)
            & no_completada
        ]
        futuras_df = df_tareas_escuela[(df_tareas_escuela["Fecha_Inicio_dt"] > hoy_dt) & no_completada]

        if not atrasadas_df.empty:
            st.markdown("### ⚠️ Actividades Atrasadas")
            vistos = {}
            for _, row in atrasadas_df.iterrows():
                render_tarjeta_escuela(row, "atrasada", "🔴 Atrasada", vistos)

        if not hoy_df.empty:
            st.markdown("### 🔔 Actividades para Hoy")
            vistos = {}
            for _, row in hoy_df.iterrows():
                render_tarjeta_escuela(row, "hoy", "🟠 Pendiente Hoy", vistos)

        if not futuras_df.empty:
            st.markdown("### 🗓️ Próximas Actividades")
            vistos = {}
            for _, row in futuras_df.iterrows():
                render_tarjeta_escuela(row, "futura", "🔵 Programada", vistos)

        st.markdown("---")

        # --- CALENDARIO ESCOLAR ---
        st.markdown("### 📅 Calendario de Actividades del Plantel")
        st.markdown(
            """
            <style>
            .fc-list-event-time { display: none !important; }
            .fc-view-harness { min-height: 600px !important; }
            </style>
        """,
            unsafe_allow_html=True,
        )

        calendar_events = []
        for _, row in df_tareas_escuela.iterrows():
            f_ini_raw = _norm_fecha(row["Fecha Inicio"])
            f_fin_raw = _norm_fecha(row["Fecha Fin"]) if row["Fecha Fin"] else f_ini_raw
            try:
                f_ini_dt = pd.to_datetime(f_ini_raw).strftime("%Y-%m-%d")
                f_fin_dt = (pd.to_datetime(f_fin_raw) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                f_ini_dt = f_ini_raw
                f_fin_dt = f_fin_raw

            estado_evt = str(row["Estado"]).strip().lower()
            color_evento = "#28a745" if estado_evt == "completada" else "#3788d8"

            calendar_events.append(
                {
                    "title": f"🏫 {row['Actividad']}",
                    "start": f_ini_dt,
                    "end": f_fin_dt,
                    "color": color_evento,
                    "allDay": True,
                }
            )

        calendar_options = {
            "editable": False,
            "selectable": True,
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "listFortnight,dayGridMonth",
            },
            "views": {
                "listFortnight": {"type": "list", "duration": {"days": 15}, "buttonText": "Agenda Quincenal"},
                "dayGridMonth": {"buttonText": "Mes"},
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
        for _, row in completadas_escuela_df.iterrows():
            f_ini = formatear_fecha_corta(_norm_fecha(row["Fecha Inicio"]))
            f_fin = formatear_fecha_corta(_norm_fecha(row["Fecha Fin"]))
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

    lista_ccts = (
        df_usuarios["CCT"].astype(str).str.strip().unique().tolist()
        if not df_usuarios.empty and "CCT" in df_usuarios.columns
        else []
    )
    avances, _ = calcular_avance_zona(tuple(lista_ccts))
    df_avances_zona = pd.DataFrame(avances)

    mi_porcentaje = 0
    if not df_avances_zona.empty and "Escuela" in df_avances_zona.columns:
        match_actual = df_avances_zona[df_avances_zona["Escuela"] == cct_usuario]
        if not match_actual.empty:
            mi_porcentaje = match_actual["Porcentaje"].values[0]

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
        st.caption("Tu avance es: actividades públicas completadas ÷ total de actividades públicas.")

    st.markdown("---")

    # --- GALERÍA DE GRÁFICAS CIRCULARES ---
    st.markdown("### 📈 Avance de la Zona 1")
    st.markdown("Estatus de cumplimiento de todos los planteles de la zona:")

    cols = st.columns(3)
    for idx, row in df_avances_zona.iterrows():
        esc_nombre = row["Escuela"]
        with cols[idx % 3]:
            with st.container(border=True):
                titulo_etiqueta = f"⭐ {esc_nombre}" if esc_nombre == cct_usuario else esc_nombre
                fig_dona = crear_grafica_dona(row["Porcentaje"], titulo_etiqueta)
                st.plotly_chart(fig_dona, use_container_width=True, key=f"esc_dona_{idx}")
