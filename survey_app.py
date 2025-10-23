import streamlit as st
import json
import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import os

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

if not firebase_admin._apps:
    # --- Inicialización Básica de Firebase ---
    # Este método carga las credenciales directamente desde un archivo JSON.
    # Es simple y efectivo para el desarrollo local.
    FIREBASE_CREDS_PATH = os.path.join(os.path.dirname(__file__), "surver-fisherman-uabcs-firebase-adminsdk-fbsvc-90c8a5fac5.json")

    try:
        if os.path.exists(FIREBASE_CREDS_PATH):
            cred = credentials.Certificate(FIREBASE_CREDS_PATH)
            firebase_admin.initialize_app(cred)
            st.success(f"Firebase inicializado desde archivo local: {os.path.basename(FIREBASE_CREDS_PATH)}")
        else:
            st.error("Archivo de credenciales de Firebase no encontrado.")
            st.info(
                f"Asegúrate de que el archivo `{os.path.basename(FIREBASE_CREDS_PATH)}` "
                "esté en el mismo directorio que el script `survey_app.py`."
            )
            st.stop()
    except Exception as e:
        st.error(f"Error al inicializar Firebase: {e}")
        st.info("Verifica que el contenido del archivo JSON de credenciales sea válido y no esté corrupto.")
        st.stop()

db = firestore.client()

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

# --- Funciones de ayuda ---

@st.cache_data # Cacha los datos del JSON para no cargarlos en cada rerun
def load_survey_data(file_path):
    """Carga las preguntas del cuestionario desde un archivo JSON."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data['cuestionario']
    except FileNotFoundError:
        st.error(f"Error: Archivo JSON del cuestionario no encontrado en {file_path}")
        return None
    except json.JSONDecodeError:
        st.error(f"Error: No se pudo decodificar JSON desde {file_path}")
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

def go_to_next_question():
    """Navega a la siguiente pregunta principal."""
    survey = st.session_state.survey_data
    sections = survey['secciones']
    current_section = sections[st.session_state.current_section_index]
    questions = current_section['preguntas']

    if st.session_state.current_question_index < len(questions) - 1:
        st.session_state.current_question_index += 1
    else:
        # Mover a la siguiente sección
        if st.session_state.current_section_index < len(sections) - 1:
            st.session_state.current_section_index += 1
            st.session_state.current_question_index = 0 # Reiniciar índice de pregunta para la nueva sección
        else:
            # Fin del cuestionario
            st.session_state.current_section_index = -1 # Marcar como finalizado
            st.session_state.current_question_index = -1 # Marcar como finalizado

def go_to_previous_question():
    """Navega a la pregunta principal anterior."""
    if st.session_state.current_question_index > 0:
        st.session_state.current_question_index -= 1
    else:
        if st.session_state.current_section_index > 0:
            st.session_state.current_section_index -= 1
            # Ir a la última pregunta de la sección anterior
            previous_section = st.session_state.survey_data['secciones'][st.session_state.current_section_index]
            st.session_state.current_question_index = len(previous_section['preguntas']) - 1
        else:
            st.warning("Ya estás en la primera pregunta.")

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

    if question['tipo'] == 'texto_abierto':
        st.session_state.responses[full_id] = st.text_input(
            label=f"Respuesta para {q_id}",
            value=default_value if default_value is not None else "",
            key=f"q_{full_id}"
        )
    elif question['tipo'] == 'fecha':
        # Asegurarse de que default_value sea un objeto date para st.date_input
        if default_value:
            try:
                default_value = datetime.datetime.strptime(default_value, "%Y-%m-%d").date()
            except ValueError:
                default_value = datetime.date.today()
        else:
            default_value = datetime.date.today()

        st.session_state.responses[full_id] = st.date_input(
            label=f"Respuesta para {q_id}",
            value=default_value,
            key=f"q_{full_id}"
        ).isoformat() # Almacenar como cadena en formato ISO
    elif question['tipo'] == 'numerico':
        st.session_state.responses[full_id] = st.number_input(
            label=f"Respuesta para {q_id}",
            value=default_value if default_value is not None else 0,
            key=f"q_{full_id}"
        )
    elif question['tipo'] == 'opcion_multiple':
        options = question['opciones']
        index = options.index(default_value) if default_value in options else 0
        selected_option = st.radio(
            label=f"Seleccione una opción para {q_id}",
            options=options,
            index=index,
            key=f"q_{full_id}"
        )
        st.session_state.responses[full_id] = selected_option
    elif question['tipo'] == 'si_no':
        options = ["Si", "No"]
        index = options.index(default_value) if default_value in options else 0
        selected_option = st.radio(
            label=f"Respuesta para {q_id}",
            options=options,
            index=index,
            key=f"q_{full_id}"
        )
        st.session_state.responses[full_id] = selected_option
    elif question['tipo'] == 'seleccion_multiple':
        options = question['opciones']
        selected_options = st.multiselect(
            label=f"Seleccione una o varias opciones para {q_id}",
            options=options,
            default=default_value if default_value else [],
            key=f"q_{full_id}"
        )
        st.session_state.responses[full_id] = selected_options
    elif question['tipo'] == 'grupo_preguntas':
        st.subheader(f"Grupo de Preguntas: {question['texto']}")
        for sub_q in question['preguntas']:
            render_question(sub_q, parent_id=full_id)
    elif question['tipo'] == 'grid_seleccion':
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
    elif question['tipo'] == 'tabla':
        st.subheader(f"Tabla: {question['texto']}")
        table_data = st.session_state.responses.get(full_id, [])
        column_ids = [col['id'] for col in question['columnas']]

        # Inicializar table_data si está vacía
        if not table_data:
            table_data = [{col_id: "" for col_id in column_ids}] # Empezar con una fila vacía

        # Preparar la configuración de columnas para st.data_editor
        column_configs = {}
        for col in question['columnas']:
            # Por defecto, todas las columnas de tabla se tratan como texto si no se especifica un tipo
            column_configs[col['id']] = st.column_config.TextColumn(col['texto'])
            # Se podrían añadir más tipos específicos si el JSON los definiera, e.g.:
            # if col.get('tipo') == 'numerico':
            #     column_configs[col['id']] = st.column_config.NumberColumn(col['texto'])

        edited_data = st.data_editor(
            table_data,
            column_config=column_configs,
            num_rows="dynamic" if question.get('permite_multiples_filas', False) else "fixed",
            key=f"q_{full_id}_table_editor"
        )
        st.session_state.responses[full_id] = edited_data

    elif question['tipo'] == 'escala_evaluacion':
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

    elif question['tipo'] == 'tabla_compleja':
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
                    selected_option = st.radio(
                        label=f"{col['texto']} para {row_label}",
                        options=options,
                        index=index,
                        key=col_full_id
                    )
                    row_responses[col_id] = selected_option
                elif col['tipo'] == 'seleccion_multiple':
                    options = col['opciones']
                    selected_options = st.multiselect(
                        label=f"{col['texto']} para {row_label}",
                        options=options,
                        default=current_col_response if current_col_response else [],
                        key=col_full_id
                    )
                    row_responses[col_id] = selected_options
                else: # Por defecto, se trata como texto si el tipo no está especificado o no es manejado
                    row_responses[col_id] = st.text_input(
                        label=f"{col['texto']} para {row_label}",
                        value=current_col_response if current_col_response is not None else "",
                        key=col_full_id
                    )
            complex_table_responses[row_label] = row_responses
        st.session_state.responses[full_id] = complex_table_responses

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

    st.title(survey['titulo'])
    st.markdown(f"*{survey['descripcion']}*")
    st.markdown("---")

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

    # Asegurarse de que current_question_index sea válido para la sección actual
    if not (0 <= st.session_state.current_question_index < len(questions)):
        st.session_state.current_question_index = 0 # Reiniciar si está fuera de límites
        st.rerun()

    current_question = questions[st.session_state.current_question_index]

    st.header(f"Sección {current_section['id_seccion']}: {current_section['titulo']}")
    st.subheader(f"Pregunta {current_question['id']}")

    # Renderizar la pregunta actual y sus sub-preguntas activas
    render_question(current_question)

    # Botones de navegación
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        # Habilitar botón "Anterior" si no es la primera pregunta de la primera sección
        if st.session_state.current_section_index > 0 or st.session_state.current_question_index > 0:
            if st.button("Anterior"):
                go_to_previous_question()
                st.rerun()
    with col2:
        # Determinar si es la última pregunta de la última sección
        is_last_question_of_survey = (
            st.session_state.current_section_index == len(sections) - 1 and
            st.session_state.current_question_index == len(questions) - 1
        )
        if is_last_question_of_survey:
            if st.button("Finalizar Encuesta"):
                st.session_state.current_section_index = -1 # Marcar como finalizado
                st.rerun()
        else:
            if st.button("Siguiente"):
                go_to_next_question()
                st.rerun()

# --- Lógica principal de la aplicación ---
if not st.session_state.logged_in:
    login_page()
else:
    survey_app()
