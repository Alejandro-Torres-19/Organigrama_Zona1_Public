# IMPORTAR DEPENDENCIAS NECESARIAS
import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
from streamlit_calendar import calendar
import streamlit.components.v1 as components

# CONFIGURACIÓN INICIAL PÁGINA
st.set_page_config(
    page_title="CRONOGRAMA Zona 1 (Visualización)",
    page_icon="📅",
    layout="wide",
)

# SCRIPT DE JAVASCRIPT / CSS PARA FORZAR EL SALTO DE LÍNEA EN EL CALENDARIO INTERNO
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


# CONEXIÓN GOOGLE SHEETS
@st.cache_resource
def conectar_google_sheets():
  scope = [
      "https://spreadsheets.google.com/feeds",
      "https://www.googleapis.com/auth/drive",
  ]
  creds_dict = dict(st.secrets["gcp_service_account"])
  client = gspread.service_account_from_dict(creds_dict)
  sheet = client.open("ORGANIGRAMA_ZONA1").sheet1
  return sheet


st.title("📅 CRONOGRAMA ZONA 1 (Vista General) 📅")

try:
  sheet = conectar_google_sheets()
except Exception as e:
  st.error(f"Error al conectarse a Google Sheets: {e}")
  st.stop()


# OBTENER DATOS CON CACHÉ Y PROTECCIÓN CONTRA CUOTAS (TTL=2)
@st.cache_data(ttl=2)
def obtener_datos_actualizados():
  for intento in range(3):
    try:
      rows = sheet.get_all_values()
      if len(rows) > 1:
        headers = [str(h).strip() for h in rows[0]]
        data_rows = rows[1:]
        df = pd.DataFrame(data_rows, columns=headers)
        return df.loc[:, df.columns != ""]
      else:
        return pd.DataFrame(
            columns=[
                "Actividad",
                "Fecha Inicio",
                "Fecha Fin",
                "Privado",
                "Estado",
                "Color",
            ]
        )
    except gspread.exceptions.APIError:
      time.sleep(1)
  return pd.DataFrame(
      columns=["Actividad", "Fecha Inicio", "Fecha Fin", "Privado", "Estado", "Color"]
  )


df_actividades = obtener_datos_actualizados()

# ==========================================
# VISTA GENERAL (ESCLAVO)
# ==========================================

# SECCIÓN PENDIENTES HOY (Oculta las privadas para los usuarios generales)
st.subheader("📌 Pendientes de Hoy")

hoy_iso = datetime.date.today().strftime("%Y-%m-%d")

actividades_hoy = []
if not df_actividades.empty:
  for idx, row in df_actividades.iterrows():
    es_priv = str(row.get("Privado", "false")).upper() == "TRUE"
    # Si es privado, el esclavo lo ignora por completo
    if es_priv:
      continue

    f_ini = str(row.get("Fecha Inicio", ""))
    f_fin = str(row.get("Fecha Fin", ""))
    if f_ini and f_fin:
      try:
        if f_ini <= hoy_iso < f_fin:
          actividades_hoy.append((idx, row))
      except Exception:
        pass

if actividades_hoy:
  for idx, row in actividades_hoy:
    titulo = str(row.get("Actividad", "Sin nombre"))
    st.markdown(f"🟡 **{titulo}** *(Pendiente)*")
else:
  st.info("🎉 ¡No hay actividades pendientes para hoy!")

st.markdown("---")

# SECCIÓN CALENDARIO (Sincroniza colores individuales y oculta privadas)
st.subheader("📅 Vista Calendario")

eventos_calendario = []
if not df_actividades.empty:
  for idx, row in df_actividades.iterrows():
    is_private = str(row.get("Privado", "false")).upper() == "TRUE"
    if is_private:
      continue  # No muestra actividades privadas en el esclavo

    titulo_display = str(row.get("Actividad", "Sin Nombre"))

    # Recupera el color guardado de la fila de Sheets
    color_fila = str(row.get("Color", ""))
    if not color_fila.startswith("#"):
      color_fila = "#3788d8"

    evento = {
        "title": titulo_display,
        "start": str(row.get("Fecha Inicio", "")),
        "end": str(row.get("Fecha Fin", "")),
        "allDay": True,
        "backgroundColor": color_fila,
        "borderColor": color_fila,
        "textColor": "#FFFFFF",
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
    "selectable": False,  # Esclavo es solo de lectura
    "editable": False,
    "locale": "es",
    "buttonText": {
        "today": "Hoy",
        "month": "Mes",
        "week": "Semana",
        "day": "Día",
        "list": "Agenda",
    },
}

calendar(
    events=eventos_calendario,
    options=calendar_options,
    key="calendario_esclavo_fijo",
)

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

# SECCIÓN LISTA DE TAREAS (Ocultando privadas)
st.subheader("📋 Lista de Tareas")

if not df_actividades.empty:
  hay_publicas = False
  for idx, row in df_actividades.iterrows():
    is_private = str(row.get("Privado", "false")).upper() == "TRUE"
    if is_private:
      continue

    hay_publicas = True
    f_ini_raw = str(row.get("Fecha Inicio", ""))
    f_fin_raw = str(row.get("Fecha Fin", ""))
    titulo_act = str(row.get("Actividad", ""))

    try:
      f_ini_fmt = pd.to_datetime(f_ini_raw).strftime("%d-%m-%Y")
      f_fin_real = pd.to_datetime(f_fin_raw) - datetime.timedelta(days=1)
      f_fin_fmt = f_fin_real.strftime("%d-%m-%Y")

      if f_ini_fmt == f_fin_fmt:
        rango_fmt = f"**{f_ini_fmt}**"
      else:
        rango_fmt = f"**{f_ini_fmt} al {f_fin_fmt}**"
    except Exception:
      rango_fmt = f"**{f_ini_raw}**"

    c1, c2, c3 = st.columns([0.4, 0.4, 0.2])

    with c1:
      st.write(rango_fmt)
    with c2:
      st.write(titulo_act)
    with c3:
      st.markdown("🟡 **Pendiente**")
    st.divider()

  if not hay_publicas:
    st.info("No hay tareas públicas registradas")
else:
  st.info("No hay tareas registradas")



