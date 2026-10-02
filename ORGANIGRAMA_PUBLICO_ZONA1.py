#IMPORTAR DEPENDENCIAS NECESARIAS
import streamlit as st
import pandas as pd
import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_calendar import calendar
import streamlit.components.v1 as components

#CONFIGURACION PAGINA INICIAL
st.set_page_config(
    page_title = "Cronograma Zona 1", page_icon = "📅", layout = "wide",
)

#APOYO CALENDARIO
st.markdown(
    """
    <style>
    .fc-event-title {
        white-space: normal !important;
        overflow: visible !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

#CONEXIÓN A GOOGLE SHEETS
@st.cache_resource
def conectar_google_sheets():
    scope =[
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    creds_dict = dict(st.secrets["gc_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("ORGANIGRAMA_ZONA1")
    return sheet

st.title("📅 CRONOGRAMA ZONA 1 📅")

try:
    sheet = conectar_google_sheets()
except Exception as e:
    st.error(f"Error al conectarse a Google Sheet: {e}")
    st.stop()

#OBTENER DATOS CON PROTECCIÓN Y CACHE RÁPIDO
@st.cache_data(ttl=2)
def obtener_datos_actualizados():
    for intento in range(3):
        try:
            rows = sheet.get_all_values()
            if len(rows) > 1:
                headers = [str(h).strip() for h in rows[0]]
                data_rows = rows[1:]
                df = pd.DataFrame(data_rows, columns = headers)
                return df.loc[:, df.columns != ""]
            else:
                return pd.DataFrame(
                    columns = ["Actividad", "Inicio", "Fin", "AllDay", "Privado", "Estado"]
                )
        except gspread.exceptions.APIError:
            time.sleep(1)
        return pd.DataFrame(
            columns = ["Actividad", "Inicio", "Fin", "AllDay", "Privado" "Estado"]
        )

df_actividades = obtener_datos_actualizados()

#FILTRAR ACTIVIDADES PRIVADAS
if(
    df_actividades is not None
    and not df_actividades.empty
    and "Privado" in df_actividades.columns
):
    condicion_publica = (
        df_actividades["Privado"].astype(str).str.upper() != "TRUE"
    )
    df_actividades = df_actividades[condicion_publica]

#SECCIÓN PENDIENTES HOY
st.subheader("📌 Pendientes de Hoy")

hoy_iso = pd.Timestamp.today().strftime("%Y-%m-%d")

actividades_hoy = []
if df_actividades is not None and not df_actividades.empty:
    for idx, row in df_actividades.iterrows():
        inicio_val = str(row.get("Inicio", ""))
        if inicio_val.startswith(hoy_iso):
            actividades_hoy.append((idx, row))

if actividades_hoy:
    for idx, row in actividades_hoy:
        val_est = str(row.get("Estado", row.get("Finalizada", ""))).strip().lower()
        is_finalizada = val_est in ["completada", "true"]
        titulo = str(row.get("Actividad", "Sin nombre"))

        if is_finalizada:
            st.markdown(f"~~**{titulo}**~~ (🟢 *Completada*)")
        else:
            st.markdown(f"🟡 **{titulo}** *(Pendiente)*")
else:
    st.info("🎉 ¡No hay actividades pendientes para hoy!")

st.markdown("---")

#SECCION CALENDARIO SIEMPRE VISIBLE
st.subheader("📅 Vista Calendario General📅")

eventos_calendario = []
if df_actividades is not None and not df_actividades.empty:
    for idx, row in df_actividades.iterrows():
        is_all_day = str(row.get("AllDay", "False")).upper() == "TRUE"
        val_est = str(row.get("Estado", row.get("Finalizada", ""))).strip().lower()
        is_finalizada = val_est in ["completada", "true"]

        titulo_display = str(row.get("Actividad", "Sin nombre"))
        if is_finalizada:
            titulo_display = f"✅ {titulo_display}"

        color_evento = "#28a745" if is_finalizada else "#3788d8"

        evento = {
            "title": titulo_display,
            "start": str(row.get("Inicio", "")),
            "end": str(row.get("Fin", "")),
            "allDay": is_all_day,
            "backgroundColor": color_evento,
            "borderColor": color_evento,
            "textcolor": "FFFFFF",
            "display": "block",
        }
        eventos_calendario.append(evento)

calendar_options = {
    "headerToolbar": {
        "left": "today prev,next",
        "center": "title",
        "right": "dayGridMonth,timeGridWeek,timeGridDay,listWeek",
    },
    "initialView": "dayGridMonth",
    "displayEventTime": False,
    "eventDisplay": "block",
    "dayMaxEvents": False,
    "selectable": True,
    "editable": False,
}

calendar(
    events = eventos_calendario,
    options = calendar_options,
    key = "calendario_usuario_fijo"
)

# INYECCIÓN DE JS PARA FORZAR EL SALTO DE LÍNEA EN EL DOM DEL CALENDARIO
components.html(
    """
    <script>
    const observer = new MutationObserver(() => {
        const doc = window.parent.document;
        const events = doc.querySelectorAll('.fc-event, .fc-event-main, .fc-event-title, .fc-daygrid-event');
        events.forEach(el => {
            el.style.whiteSpace = 'normal';
            el.style.overflow = 'visible';
            el.style.textOverflow = 'initial';
            el.style.height = 'auto';
        });
        const frames = doc.querySelectorAll('.fc-daygrid-day-frame');
        frames.forEach(f => {
            f.style.minHeight = '130px';
        });
    });
    observer.observe(window.parent.document.body, { childList: true, subtree: true });
    </script>
    """,
    height=0,
)

st.markdown("---")

#SECCIÓN LISTA GENERAL TAREAS
st.subheader("📋 Lista General de Tareas")

if df_actividades is not None and not df_actividades.empty:
    for idx, row in df_actividades.iterrows():
        val_est = str(row.get("Estado", row.get("Finalizada", ""))).strip().lower()
        is_finalizada = val_est in ["completada", "true"]
        inicio_raw = str(row.get("Inicio", ""))
        titulo_act = str(row.get("Actividad", ""))

        if "T" in inicio_raw:
            partes = inicio_raw.split("T")
            try:
                fecha_fmt = pd.to_datetime(partes[0]).strftime("%d/%m/%Y")
            except:
                fecha_fmt = partes[0]
            hora_fmt = partes [1][:5]
        elif "" in inicio_raw:
            partes = inicio_raw.split("")
            try:
                fecha_fmt = pd.to_datetime(partes[0]).strftime("%d/%m/%Y")
            except:
                fecha_fmt = partes[0]
            hora_fmt = partes [1][:5]
        else:
            try:
                fecha_fmt = pd.to_datetime(inicio_raw).strftime("%d/%m/%Y")
            except:
                fecha_fmt = inicio_raw
            hora_fmt = ""

        c1, c2, c3, c4 = st.columns([0.25, 0.2, 0.4, 0.15])

        with c1:
            st.write(f"**{fecha_fmt}**")
        with c2:
            st.write(hora_fmt if hora_fmt else "")
        with c3:
            st.write(titulo_act)
        with c4:
            if is_finalizada:
                st.markdown("🟢 **Completada**")
            else:
                st.markdown("🟡 **Pendiente**")
            st.divider()

    else:
        st.info("No hay tareas registradas")




