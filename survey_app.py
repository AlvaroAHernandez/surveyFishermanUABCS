import streamlit as st
import json
import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import os
from pydantic import BaseModel, ValidationError
from typing import List, Optional, Union, Any

# --- Firebase Initialization ---
# IMPORTANTE: Para mayor seguridad, es altamente recomendable usar los secretos de Streamlit
# para tu clave de cuenta de servicio de Firebase, especialmente en entornos de despliegue.
#
# Para usar secretos de Streamlit:
# 1. Crea un archivo llamado `.streamlit/secrets.toml` en la raíz de tu proyecto.
# 2. Copia el contenido de tu archivo JSON de credenciales de Firebase en `secrets.toml`
#    siguiendo la estructura que se muestra a continuación (reemplaza los valores con los tuyos):
#
#    [firebase]
#    type = "service_account"
#    project_id = "your-project-id"
#    private_key_id = "your-private-key-id"
#    private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_CONTENT\n-----END PRIVATE KEY-----\n"
#    client_email = "your-client-email@your-project-id.iam.gserviceaccount.com"
#    client_id = "your-client-id"
#    auth_uri = "https://accounts.google.com/o/oauth2/auth"
#    token_uri = "https://oauth2.googleapis.com/token"
#    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
#    client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-client-email.iam.gserviceaccount.com"
#    universe_domain = "googleapis.com"
#
# Si no usas secretos, el código intentará cargar un archivo JSON local.
# Asegúrate de que el archivo `surveyfisherman-firebase-adminsdk.json` esté en el mismo directorio
# que tu script de Streamlit si usas la opción de archivo local.

def initialize_firebase():
    """Inicializa Firebase priorizando st.secrets y usando archivo local como respaldo."""
    # Evitar inicializar múltiples veces si Streamlit recarga el script
    if firebase_admin._apps:
        return firestore.client()

    # 1. Intentar usar st.secrets (Recomendado para Producción/Nube)
    try:
        if "firebase" in st.secrets:
            # Convertir la configuración de secretos a un diccionario
            cred_dict = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            st.toast("☁️ Modo Nube: Iniciado con Secrets", icon="☁️")
            return firestore.client()
    except Exception as e:
        # Solo advertir en consola, continuar intentando con archivo local
        print(f"Advertencia: No se pudo inicializar desde st.secrets: {e}")

    # 2. Intentar usar archivo local (Respaldo para Desarrollo Local)
    local_file = "surver-fisherman-uabcs-firebase-adminsdk-fbsvc-90c8a5fac5.json"
    local_path = os.path.join(os.path.dirname(__file__), local_file)
    
    if os.path.exists(local_path):
        cred = credentials.Certificate(local_path)
        firebase_admin.initialize_app(cred)
        st.toast(f"🏠 Modo Local: Iniciado con {local_file}", icon="🏠")
        return firestore.client()

    # 3. Si falla todo
    st.error("No se encontraron credenciales de Firebase (ni en secrets.toml ni archivo local).")
    st.stop()

db = initialize_firebase()

# --- Constantes ---
# Asegúrate de que esta ruta sea correcta para tu archivo survey.json
SURVEY_FILE_PATH = os.path.join(os.path.dirname(__file__), "json", "survey.json")
COLLECTION_NAME = "survey_responses" # Nombre de la colección en Firestore

# --- Inicialización del estado de sesión de Streamlit ---
# Usamos st.session_state para mantener el estado de la aplicación a través de los reruns
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'current_section_index' not in st.session_state:
    st.session_state.current_section_index = 0
if 'current_question_index' not in st.session_state:
    st.session_state.current_question_index = 0
if 'responses' not in st.session_state:
    st.session_state.responses = {}
if 'survey_data' not in st.session_state:
    st.session_state.survey_data = None
if 'survey_loaded' not in st.session_state:
    st.session_state.survey_loaded = False

# --- Modelos Pydantic para Validación ---
class SecondaryCondition(BaseModel):
    pregunta_id: str
    valores: List[Any]

class ScaleOption(BaseModel):
    valor: Any
    etiqueta: str

class Item(BaseModel):
    id: str
    texto: str

class TableColumn(BaseModel):
    id: str
    texto: str
    tipo: Optional[str] = None
    opciones: Optional[List[str]] = None

class Question(BaseModel):
    id: str
    texto: str
    tipo: str
    instrucciones: Optional[str] = None
    opciones: Optional[List[str]] = None
    condicional_en: Optional[str] = None
    condicion_valor: Optional[str] = None
    condicion_secundaria: Optional[SecondaryCondition] = None
    filas: Optional[List[str]] = None
    columnas: Optional[Union[List[str], List[TableColumn], List[dict]]] = None
    escala: Optional[List[ScaleOption]] = None
    items: Optional[List[Item]] = None
    permite_multiples_filas: Optional[bool] = None
    sub_preguntas: Optional[List['Question']] = None
    preguntas: Optional[List['Question']] = None

# Habilitar referencias recursivas para sub_preguntas
try:
    Question.model_rebuild()
except AttributeError:
    Question.update_forward_refs() # Fallback para versiones antiguas de Pydantic

class Section(BaseModel):
    id_seccion: int
    titulo: str
    preguntas: List[Question]

class Survey(BaseModel):
    titulo: str
    descripcion: str
    secciones: List[Section]

class SurveyRoot(BaseModel):
    cuestionario: Survey

# --- Funciones de ayuda ---

@st.cache_data # Cacha los datos del JSON para no cargarlos en cada rerun
def load_survey_data(file_path):
    """Carga y valida las preguntas del cuestionario desde un archivo JSON."""
    # Se agregó comentario para invalidar caché tras cambios en modelo Pydantic
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validar con Pydantic
        validated_data = SurveyRoot(**data)
        # Retornar como diccionario, excluyendo valores None para evitar errores en bucles
        return validated_data.model_dump(exclude_none=True)['cuestionario']
    except FileNotFoundError:
        st.error(f"Error: Archivo JSON del cuestionario no encontrado en {file_path}")
        return None
    except json.JSONDecodeError:
        st.error(f"Error: No se pudo decodificar JSON desde {file_path}")
        return None
    except ValidationError as e:
        st.error(f"Error de Validación en survey.json: {e}")
        st.json(e.errors()) # Mostrar detalles del error
        return None

def save_response_to_firestore(responses, username):
    """Guarda las respuestas recolectadas en Firestore."""
    try:
        doc_ref = db.collection(COLLECTION_NAME).document()
        responses_to_save = {
            "user_id": username,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "responses": responses
        }
        doc_ref.set(responses_to_save)
        st.success(f"¡Respuestas guardadas con éxito en Firestore! ID: {doc_ref.id}")
        return True
    except Exception as e:
        st.error(f"Error al guardar respuestas en Firestore: {e}")
        return False

def reset_survey_state():
    """Reinicia el estado del cuestionario para una nueva presentación."""
    st.session_state.current_section_index = 0
    st.session_state.current_question_index = 0
    st.session_state.responses = {}
    # No es necesario recargar el JSON a menos que el archivo pueda cambiar
    # st.session_state.survey_loaded = False

def go_to_next_section():
    """Navega a la siguiente sección."""
    survey = st.session_state.survey_data
    sections = survey['secciones']

    if st.session_state.current_section_index < len(sections) - 1:
        st.session_state.current_section_index += 1
    else:
        # Fin del cuestionario
        st.session_state.current_section_index = -1

def go_to_previous_section():
    """Navega a la sección anterior."""
    if st.session_state.current_section_index > 0:
        st.session_state.current_section_index -= 1
    else:
        st.warning("Ya estás en la primera sección.")

    # --- Funciones de Renderizado de Widgets (Refactorización) ---

def _render_text_input(question, full_id, default_value):
    st.session_state.responses[full_id] = st.text_input(
        label=f"Respuesta para {question['id']}",
        value=default_value if default_value is not None else "",
        key=f"q_{full_id}"
    )

def _render_date_input(question, full_id, default_value):
    if default_value:
        try:
            date_val = datetime.datetime.strptime(default_value, "%Y-%m-%d").date()
        except ValueError:
            date_val = datetime.date.today()
    else:
        date_val = datetime.date.today()

    selected_date = st.date_input(
        label=f"Respuesta para {question['id']}",
        value=date_val,
        key=f"q_{full_id}"
    )
    st.session_state.responses[full_id] = selected_date.isoformat()

def _render_number_input(question, full_id, default_value):
    st.session_state.responses[full_id] = st.number_input(
        label=f"Respuesta para {question['id']}",
        value=default_value if default_value is not None else 0,
        key=f"q_{full_id}"
    )

def _render_radio_input(question, full_id, default_value):
    # Maneja tanto 'opcion_multiple' como 'si_no'
    options = question.get('opciones', ["Si", "No"])
    index = options.index(default_value) if default_value in options else 0
    selected_option = st.radio(
        label=f"Respuesta para {question['id']}",
        options=options,
        index=index,
        key=f"q_{full_id}"
    )
    st.session_state.responses[full_id] = selected_option

def _render_multiselect(question, full_id, default_value):
    options = question['opciones']
    selected_options = st.multiselect(
        label=f"Seleccione una o varias opciones para {question['id']}",
        options=options,
        default=default_value if default_value else [],
        key=f"q_{full_id}"
    )
    st.session_state.responses[full_id] = selected_options

def _render_group(question, full_id, default_value):
    st.subheader(f"Grupo de Preguntas: {question['texto']}")
    for sub_q in question.get('preguntas', []):
        render_question(sub_q, parent_id=full_id)

def _render_grid_selection(question, full_id, default_value):
    st.subheader(f"Grid de Selección: {question['texto']}")
    grid_responses = st.session_state.responses.get(full_id, {})
    for row_label in question['filas']:
        col_key = f"{full_id}_{row_label}"
        selected_months = st.multiselect(
            label=f"**{row_label}**: Seleccione meses",
            options=question['columnas'],
            default=grid_responses.get(row_label, []),
            key=col_key
        )
        grid_responses[row_label] = selected_months
    st.session_state.responses[full_id] = grid_responses

def _render_table(question, full_id, default_value):
    st.subheader(f"Tabla: {question['texto']}")
    table_data = st.session_state.responses.get(full_id, [])
    column_ids = [col['id'] for col in question['columnas']]

    if not table_data:
        table_data = [{col_id: "" for col_id in column_ids}]

    column_configs = {col['id']: st.column_config.TextColumn(col['texto']) for col in question['columnas']}
    
    edited_data = st.data_editor(
        table_data,
        column_config=column_configs,
        num_rows="dynamic" if question.get('permite_multiples_filas', False) else "fixed",
        key=f"q_{full_id}_table_editor"
    )
    st.session_state.responses[full_id] = edited_data

def _render_evaluation_scale(question, full_id, default_value):
    st.subheader(f"Escala de Evaluación: {question['texto']}")
    scale_responses = st.session_state.responses.get(full_id, {})
    scale_options_map = {str(s['valor']): s['etiqueta'] for s in question['escala']}
    scale_values = [str(s['valor']) for s in question['escala']]

    for item in question['items']:
        item_key = f"{full_id}_{item['id']}"
        default_item_value = str(scale_responses.get(item['id'], scale_values[0]))
        index = scale_values.index(default_item_value) if default_item_value in scale_values else 0

        selected_value = st.radio(
            label=f"**{item['texto']}**",
            options=scale_values,
            format_func=lambda x: scale_options_map[x],
            index=index,
            key=item_key
        )
        scale_responses[item['id']] = selected_value
    st.session_state.responses[full_id] = scale_responses

def _render_complex_table(question, full_id, default_value):
    st.subheader(f"Tabla Compleja: {question['texto']}")
    complex_table_responses = st.session_state.responses.get(full_id, {})

    for row_label in question['filas']:
        st.markdown(f"**{row_label}**")
        row_responses = complex_table_responses.get(row_label, {})
        for col in question['columnas']:
            col_id = col['id']
            col_full_id = f"{full_id}_{row_label}_{col_id}"
            current_col_response = row_responses.get(col_id)

            if col['tipo'] == 'opcion_multiple':
                options = col['opciones']
                index = options.index(current_col_response) if current_col_response in options else 0
                row_responses[col_id] = st.radio(
                    label=f"{col['texto']} para {row_label}",
                    options=options,
                    index=index,
                    key=col_full_id
                )
            elif col['tipo'] == 'seleccion_multiple':
                row_responses[col_id] = st.multiselect(
                    label=f"{col['texto']} para {row_label}",
                    options=col['opciones'],
                    default=current_col_response if current_col_response else [],
                    key=col_full_id
                )
            else:
                row_responses[col_id] = st.text_input(
                    label=f"{col['texto']} para {row_label}",
                    value=current_col_response if current_col_response is not None else "",
                    key=col_full_id
                )
        complex_table_responses[row_label] = row_responses
    st.session_state.responses[full_id] = complex_table_responses

# Diccionario de despacho para renderizar widgets
RENDER_HANDLERS = {
    'texto_abierto': _render_text_input,
    'fecha': _render_date_input,
    'numerico': _render_number_input,
    'opcion_multiple': _render_radio_input,
    'si_no': _render_radio_input,
    'seleccion_multiple': _render_multiselect,
    'grupo_preguntas': _render_group,
    'grid_seleccion': _render_grid_selection,
    'tabla': _render_table,
    'escala_evaluacion': _render_evaluation_scale,
    'tabla_compleja': _render_complex_table
}

def render_question(question, parent_id=None):
    """
    Renderiza una pregunta individual y sus sub-preguntas condicionales.
    Las sub-preguntas se muestran en la misma "página" si sus condiciones se cumplen.
    """
    q_id = question['id']
    full_id = f"{parent_id}_{q_id}" if parent_id else q_id
    current_response = st.session_state.responses.get(full_id)

    st.markdown(f"**{question['texto']}**")
    if 'instrucciones' in question:
        st.info(question['instrucciones'])

    # Determinar el valor por defecto para los widgets
    default_value = current_response

    # Renderizar el widget correspondiente usando el diccionario de despacho
    handler = RENDER_HANDLERS.get(question['tipo'])
    if handler:
        handler(question, full_id, default_value)
    else:
        st.warning(f"Tipo de pregunta no soportado: {question['tipo']} (ID: {q_id})")
        st.session_state.responses[full_id] = st.text_area(
            label=f"Respuesta para {q_id} (Tipo no soportado, ingrese texto)",
            value=default_value if default_value is not None else "",
            key=f"q_{full_id}_unsupported"
        )

    # Manejar sub-preguntas condicionales
    if 'sub_preguntas' in question:
        parent_answer = st.session_state.responses.get(full_id)
        for sub_q in question['sub_preguntas']:
            sub_q_full_id = f"{full_id}_{sub_q['id']}"
            display_sub_q = True # Asumir que se muestra a menos que las condiciones fallen

            # Verificar condición primaria ('condicional_en')
            if 'condicional_en' in sub_q:
                if parent_answer is None: # Si la pregunta padre no ha sido respondida, no puede cumplir la condición
                    display_sub_q = False
                elif isinstance(parent_answer, list): # Para seleccion_multiple
                    if sub_q['condicional_en'] not in parent_answer:
                        display_sub_q = False
                else: # Para opcion_multiple, si_no
                    if str(parent_answer) != sub_q['condicional_en']:
                        display_sub_q = False

            # Verificar condición secundaria ('condicion_secundaria') si la primaria se cumple
            if display_sub_q and 'condicion_secundaria' in sub_q:
                secondary_q_id = sub_q['condicion_secundaria']['pregunta_id']
                secondary_q_values = sub_q['condicion_secundaria']['valores']
                secondary_answer = st.session_state.responses.get(secondary_q_id)

                if secondary_answer is None: # Si la pregunta secundaria no ha sido respondida, no puede cumplir la condición
                    display_sub_q = False
                elif isinstance(secondary_answer, list):
                    if not any(val in secondary_answer for val in secondary_q_values):
                        display_sub_q = False
                else:
                    if secondary_answer not in secondary_q_values:
                        display_sub_q = False

            if display_sub_q:
                render_question(sub_q, parent_id=full_id)
            else:
                # Si la sub-pregunta no se muestra, eliminar su respuesta del estado de sesión.
                # Esto es crucial para evitar guardar respuestas de preguntas que no eran relevantes.
                if sub_q_full_id in st.session_state.responses:
                    del st.session_state.responses[sub_q_full_id]
                # Eliminar recursivamente las respuestas de sus sub-sub-preguntas si las hay
                if 'sub_preguntas' in sub_q:
                    for sub_sub_q in sub_q['sub_preguntas']:
                        sub_sub_q_full_id = f"{sub_q_full_id}_{sub_sub_q['id']}"
                        if sub_sub_q_full_id in st.session_state.responses:
                            del st.session_state.responses[sub_sub_q_full_id]


# --- Página de Autenticación ---
def login_page():
    # Cargar datos para mostrar título y descripción en el login
    survey_data = load_survey_data(SURVEY_FILE_PATH)
    
    if survey_data:
        st.title(survey_data['titulo'])
        st.markdown(f"*{survey_data['descripcion']}*")
    else:
        st.title("Iniciar Sesión en la Encuesta")

    st.markdown("---")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Entrar"):
        # --- Autenticación Segura usando Secretos de Streamlit ---
        # Se valida contra las credenciales definidas en .streamlit/secrets.toml
        try:
            app_username = st.secrets["app_credentials"]["username"]
            app_password = st.secrets["app_credentials"]["password"]

            if username == app_username and password == app_password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("¡Inicio de sesión exitoso!")
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
        except KeyError:
            st.error("Error de configuración: Las credenciales de la aplicación no están definidas en los secretos.")
            st.info("Asegúrate de añadir la sección [app_credentials] a tu archivo .streamlit/secrets.toml")


# --- Aplicación Principal del Cuestionario ---
def survey_app():
    if not st.session_state.survey_loaded:
        st.session_state.survey_data = load_survey_data(SURVEY_FILE_PATH)
        if st.session_state.survey_data:
            st.session_state.survey_loaded = True
        else:
            # El mensaje de error ya fue mostrado por load_survey_data
            return

    survey = st.session_state.survey_data
    sections = survey['secciones']

    # Barra lateral para información del usuario y cerrar sesión
    st.sidebar.title("Navegación")
    st.sidebar.write(f"Usuario: **{st.session_state.username}**")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        reset_survey_state() # Limpiar el estado de la encuesta al cerrar sesión
        st.rerun()
    st.sidebar.markdown("---")

    # Lógica para cuando la encuesta ha terminado
    if st.session_state.current_section_index == -1: # Indica que la encuesta ha finalizado
        st.success("¡Encuesta completada! Gracias por su participación.")
        st.subheader("Resumen de sus respuestas:")
        # Muestra las respuestas en formato JSON para revisión
        st.json(st.session_state.responses)

        if st.button("Guardar y Finalizar"):
            if save_response_to_firestore(st.session_state.responses, st.session_state.username):
                st.balloons() # Pequeña celebración visual
                reset_survey_state() # Reiniciar para una nueva encuesta
                st.rerun()
            else:
                st.error("Hubo un problema al guardar sus respuestas.")
        if st.button("Volver a empezar"):
            reset_survey_state()
            st.rerun()
        return

    current_section = sections[st.session_state.current_section_index]
    questions = current_section['preguntas']

    st.header(f"Sección {current_section['id_seccion']}: {current_section['titulo']}")
    
    # Renderizar todas las preguntas de la sección
    for question in questions:
        st.subheader(f"Pregunta {question['id']}")
        render_question(question)
        st.markdown("---")

    # Botones de navegación
    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.current_section_index > 0:
            if st.button("Anterior"):
                go_to_previous_section()
                st.rerun()
    with col2:
        is_last_section = st.session_state.current_section_index == len(sections) - 1
        
        if is_last_section:
            if st.button("Finalizar Encuesta"):
                st.session_state.current_section_index = -1 # Marcar como finalizado
                st.rerun()
        else:
            if st.button("Siguiente"):
                go_to_next_section()
                st.rerun()

# --- Lógica principal de la aplicación ---
if not st.session_state.logged_in:
    login_page()
else:
    survey_app()
