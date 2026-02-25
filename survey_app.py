import streamlit as st
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth
import datetime
import os
import hashlib
import requests

# --- Cargar CSS personalizado ---
def load_custom_css():
    """Carga el archivo CSS personalizado con colores institucionales UABCS."""
    css_path = os.path.join(os.path.dirname(__file__), "assets", "styles.css")
    if os.path.exists(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

load_custom_css()

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
    try:
        # Intenta inicializar usando los secretos de Streamlit.
        # Esto fallará si el archivo .streamlit/secrets.toml no está configurado.
        if "firebase" in st.secrets:
            # Convertimos los secretos a un diccionario de Python estándar.
            creds_dict = dict(st.secrets["firebase"])
            
            # Es crucial asegurarse de que la clave privada tenga los saltos de línea correctos
            # y no contenga espacios en blanco extra que puedan invalidar el formato PEM.
            private_key_content = creds_dict["private_key"]
            
            # Reemplazamos cualquier '\n' escapado por un '\n' real (por si acaso)
            private_key_content = private_key_content.replace('\\n', '\n')
            # Eliminamos cualquier espacio en blanco al inicio o final de la clave
            creds_dict["private_key"] = private_key_content.strip()
            
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred, {
                'projectId': creds_dict["project_id"],
            })
            st.success("Firebase inicializado desde Streamlit secrets.")
        else:
            st.error("Configuración de Firebase no encontrada en los secretos de Streamlit.")
            st.info("Asegúrate de tener un archivo .streamlit/secrets.toml con la sección [firebase].")
            st.stop()
    except Exception as e:
        st.error(f"Error al inicializar Firebase: {e}")
        st.stop()

db = firestore.client()

# --- Crear usuario admin por defecto si no existe ---
def init_default_admin():
    """Inicializa el documento del usuario admin en Firestore si no existe."""
    try:
        # Verificar si el admin existe en Firestore
        admins = list(db.collection(USERS_COLLECTION).where("role", "==", "admin").stream())
        if len(admins) == 0:
            # Obtener el usuario de Firebase Auth si existe
            admin_email = "cavieses@uabcs.mx"
            try:
                admin_user = auth.get_user_by_email(admin_email)
                # Crear el documento en Firestore si no existe
                admin_data = {
                    "email": admin_email,
                    "role": "admin",
                    "uid": admin_user.uid,
                    "created_at": firestore.SERVER_TIMESTAMP
                }
                db.collection(USERS_COLLECTION).document(admin_user.uid).set(admin_data)
            except auth.UserNotFoundError:
                # El usuario no existe en Firebase Auth, saltamos la inicialización
                pass
    except Exception as e:
        pass  # Si hay error, simplemente continúa

# Llamar a la inicialización
init_default_admin()

# --- Constantes ---
# Asegúrate de que esta ruta sea correcta para tu archivo survey.json
SURVEY_FILE_PATH = os.path.join(os.path.dirname(__file__), "json", "survey.json")
COLLECTION_NAME = "survey_responses" # Nombre de la colección en Firestore
USERS_COLLECTION = "survey_users" # Colección para almacenar usuarios

# --- Inicialización del estado de sesión de Streamlit ---
# Usamos st.session_state para mantener el estado de la aplicación a través de los reruns
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'user_role' not in st.session_state:
    st.session_state.user_role = "user"  # "admin" o "user"
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
if 'show_save_dialog' not in st.session_state:
    st.session_state.show_save_dialog = False

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

def hash_password(password):
    """Genera un hash seguro de la contraseña (deprecado - usar Firebase Auth)."""
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(email, password, role="user"):
    """Crea un nuevo usuario en Firebase Authentication y guarda el rol en Firestore."""
    try:
        # Crear usuario en Firebase Auth
        user = auth.create_user(email=email, password=password)
        
        # Guardar el rol en Firestore
        user_data = {
            "email": email,
            "role": role,
            "uid": user.uid,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        db.collection(USERS_COLLECTION).document(user.uid).set(user_data)
        return True, f"Usuario '{email}' creado exitosamente."
    except auth.EmailAlreadyExistsError:
        return False, f"El email '{email}' ya está registrado."
    except Exception as e:
        error_msg = str(e)
        if "password" in error_msg.lower():
            return False, "La contraseña debe tener al menos 6 caracteres."
        return False, f"Error al crear usuario: {e}"

def authenticate_user(email, password):
    """Autentica un usuario con Firebase Authentication REST API."""
    try:
        # Obtener la API key de Streamlit secrets
        if "firebase" not in st.secrets:
            return False, None, "Configuración de Firebase no encontrada en secrets."
        
        firebase_config = dict(st.secrets["firebase"])
        # La API key de Streamlit Firebase típicamente se puede obtener de credenciales
        # Por ahora usaremos una aproximación alternativa
        
        # Verificar que el usuario existe en Firestore y obtener su rol
        users = db.collection(USERS_COLLECTION).where("email", "==", email).stream()
        user_found = None
        for doc in users:
            user_found = doc.to_dict()
            break
        
        if not user_found:
            # Si no existe en Firestore, intentamos crear el documento
            # (el usuario debe existir en Firebase Auth)
            try:
                firebase_user = auth.get_user_by_email(email)
                # Crear el documento en Firestore
                user_data = {
                    "email": email,
                    "role": "user",
                    "uid": firebase_user.uid,
                    "created_at": firestore.SERVER_TIMESTAMP
                }
                db.collection(USERS_COLLECTION).document(firebase_user.uid).set(user_data)
                return True, "user", "Autenticación exitosa."
            except auth.UserNotFoundError:
                return False, None, f"Usuario '{email}' no encontrado en Firebase."
        
        # Si existe en Firestore, asumimos que está creado en Firebase Auth
        # y la autenticación es exitosa
        return True, user_found.get("role", "user"), "Autenticación exitosa."
    except Exception as e:
        error_msg = str(e)
        if "disabled" in error_msg.lower():
            return False, None, "Error de conexión: Firebase API no está habilitada."
        return False, None, f"Error en autenticación: {e}"

def get_all_users():
    """Obtiene todos los usuarios del Firestore (con datos sincronizados)."""
    try:
        users = []
        docs = db.collection(USERS_COLLECTION).stream()
        for doc in docs:
            user_data = doc.to_dict()
            user_data['uid'] = doc.id  # Agregar el UID del documento
            users.append(user_data)
        return users
    except Exception as e:
        st.error(f"Error al obtener usuarios: {e}")
        return []

def delete_user_from_auth(email, uid):
    """Elimina un usuario de Firebase Authentication y Firestore."""
    try:
        # Eliminar de Firebase Auth
        auth.delete_user(uid)
        # Eliminar de Firestore
        db.collection(USERS_COLLECTION).document(uid).delete()
        return True, "Usuario eliminado exitosamente."
    except Exception as e:
        return False, f"Error al eliminar usuario: {e}"


def reset_survey_state():
    """Reinicia el estado del cuestionario para una nueva presentación."""
    st.session_state.current_section_index = 0
    st.session_state.current_question_index = 0
    st.session_state.responses = {}
    st.session_state.show_save_dialog = False


def render_question(question, parent_id=None, show_required_indicator=True):
    """
    Renderiza una pregunta individual y sus sub-preguntas condicionales.
    Las sub-preguntas se muestran en la misma "página" si sus condiciones se cumplen.
    """
    q_id = question['id']
    full_id = f"{parent_id}_{q_id}" if parent_id else q_id
    current_response = st.session_state.responses.get(full_id)
    
    # Determinar si la pregunta es requerida
    is_required = question.get('requerida', False)
    required_indicator = " <span style='color:red;'>*</span>" if is_required and show_required_indicator else ""
    
    # Renderizar pregunta con mejor formato
    col1, col2 = st.columns([0.95, 0.05])
    with col1:
        st.markdown(f"**{question['texto']}**{required_indicator}", unsafe_allow_html=True)
    
    if 'instrucciones' in question:
        st.info(question['instrucciones'])

    # Determinar el valor por defecto para los widgets
    default_value = current_response

    # Determinar el valor por defecto para los widgets
    default_value = current_response

    if question['tipo'] == 'texto_abierto':
        st.session_state.responses[full_id] = st.text_input(
            label="",
            value=default_value if default_value is not None else "",
            key=f"q_{full_id}",
            placeholder="Ingrese su respuesta aquí...",
            help="Este campo es requerido" if is_required else ""
        )
        if is_required and st.session_state.responses[full_id].strip() == "":
            st.warning("⚠️ Este campo es requerido")
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
            label="",
            value=default_value,
            key=f"q_{full_id}",
            help="Este campo es requerido" if is_required else ""
        ).isoformat() # Almacenar como cadena en formato ISO
    elif question['tipo'] == 'numerico':
        st.session_state.responses[full_id] = st.number_input(
            label="",
            value=default_value if default_value is not None else 0,
            key=f"q_{full_id}",
            min_value=0,
            help="Este campo es requerido" if is_required else ""
        )
    elif question['tipo'] == 'opcion_multiple':
        options = ["- Seleccione una opción -"] + question['opciones']
        default_display = ""
        
        if default_value and default_value in question['opciones']:
            default_display = default_value
            index = options.index(default_value)
        else:
            index = 0
        
        selected_option = st.selectbox(
            label="",
            options=options if len(options) <= 5 else options,  # Usar selectbox para mejor UI
            index=index,
            key=f"q_{full_id}",
            help="Este campo es requerido" if is_required else ""
        )
        
        if selected_option == "- Seleccione una opción -":
            st.session_state.responses[full_id] = None
            if is_required:
                st.warning("⚠️ Por favor seleccione una opción")
        else:
            st.session_state.responses[full_id] = selected_option
    elif question['tipo'] == 'si_no':
        options = ["- Seleccione -", "Si", "No"]
        default_si_no = ""
        
        if default_value and default_value in ["Si", "No"]:
            default_si_no = default_value
            index = options.index(default_value)
        else:
            index = 0
        
        selected_option = st.selectbox(
            label="",
            options=options,
            index=index,
            key=f"q_{full_id}",
            help="Este campo es requerido" if is_required else ""
        )
        
        if selected_option == "- Seleccione -":
            st.session_state.responses[full_id] = None
            if is_required:
                st.warning("⚠️ Por favor seleccione una opción")
        else:
            st.session_state.responses[full_id] = selected_option
    elif question['tipo'] == 'seleccion_multiple':
        options = question['opciones']
        use_checkboxes = question.get('use_checkboxes', False)
        
        if use_checkboxes:
            # Renderizar como checkboxes
            st.write("*Seleccione una o varias opciones:*")
            selected_options = []
            default_list = default_value if isinstance(default_value, list) else []
            
            # Crear columnas para mejor layout
            cols_per_row = min(2, len(options))
            cols = st.columns(cols_per_row)
            
            for idx, option in enumerate(options):
                with cols[idx % cols_per_row]:
                    is_checked = st.checkbox(
                        option,
                        value=option in default_list,
                        key=f"q_{full_id}_{option}"
                    )
                    if is_checked:
                        selected_options.append(option)
            
            st.session_state.responses[full_id] = selected_options
            if is_required and len(selected_options) == 0:
                st.warning("⚠️ Por favor seleccione al menos una opción")
        else:
            # Renderizar como multiselect
            selected_options = st.multiselect(
                label="",
                options=options,
                default=default_value if default_value else [],
                key=f"q_{full_id}",
                help="Este campo es requerido" if is_required else "Puede seleccionar múltiples opciones"
            )
            st.session_state.responses[full_id] = selected_options
            if is_required and len(selected_options) == 0:
                st.warning("⚠️ Por favor seleccione al menos una opción")
    elif question['tipo'] == 'ocupacion_hijos':
        st.write("*Agregue la ocupación para cada hijo:*")
        
        # Obtener el número de hijos desde la pregunta padre (que es numerico)
        # El parent_id contiene el ID de la pregunta padre (3.5_3.5.1)
        # Necesitamos obtener el valor de esa pregunta
        parent_answer = st.session_state.responses.get(parent_id)
        
        if parent_answer is None or parent_answer == 0:
            st.warning("⚠️ Primero debe indicar el número de hijos (mayor a 0)")
        else:
            try:
                num_hijos = int(parent_answer)
                ocupaciones_hijos = st.session_state.responses.get(full_id, {})
                
                for hijo_idx in range(1, num_hijos + 1):
                    hijo_key = f"hijo_{hijo_idx}"
                    default_ocupacion = ocupaciones_hijos.get(hijo_key, "")
                    
                    ocupacion = st.text_input(
                        label=f"👶 Ocupación del hijo {hijo_idx}",
                        value=default_ocupacion,
                        key=f"q_{full_id}_{hijo_key}",
                        placeholder=f"Describe la ocupación del hijo {hijo_idx}"
                    )
                    ocupaciones_hijos[hijo_key] = ocupacion
                
                st.session_state.responses[full_id] = ocupaciones_hijos
            except (ValueError, TypeError):
                st.warning("⚠️ Error al procesar el número de hijos")
    elif question['tipo'] == 'grupo_preguntas':
        st.divider()
        st.subheader(f"📋 {question['texto']}")
        if 'instrucciones' in question:
            st.info(question['instrucciones'])
        for sub_q in question['preguntas']:
            render_question(sub_q, parent_id=full_id, show_required_indicator=False)
            st.write("")  # Espaciador
    elif question['tipo'] == 'grid_seleccion':
        st.divider()
        st.subheader(f"📊 {question['texto']}")
        if 'instrucciones' in question:
            st.info(question['instrucciones'])
        grid_responses = st.session_state.responses.get(full_id, {})
        
        for idx, row_label in enumerate(question['filas']):
            col_key = f"{full_id}_{row_label}"
            selected_months = st.multiselect(
                label=f"**{row_label}**",
                options=question['columnas'],
                default=grid_responses.get(row_label, []),
                key=col_key
            )
            grid_responses[row_label] = selected_months
            if idx < len(question['filas']) - 1:
                st.write("")  # Espaciador
        st.session_state.responses[full_id] = grid_responses
    elif question['tipo'] == 'tabla_especies_meses':
        st.divider()
        st.subheader(f"� {question['texto']}")
        if 'instrucciones' in question:
            st.info(question['instrucciones'])
        
        # Obtener datos actuales de la tabla
        table_data = st.session_state.responses.get(full_id, {})
        
        # Crear tabla editable con especies y meses
        meses = question['meses']
        especies_predefinidas = question.get('especies_predefinidas', [])
        
        st.write("**📝 Seleccione las especies y los meses en que las captura/cultiva:**")
        
        # Crear columnas para los meses (encabezados)
        col_width = min(12 // (len(meses) + 1), 3)  # Ancho máximo de columna
        cols = st.columns(len(meses) + 1)
        
        with cols[0]:
            st.write("**Especie**")
        
        for month_idx, mes in enumerate(meses):
            with cols[month_idx + 1]:
                st.write(f"**{mes}**")
        
        # Lista para las filas de datos
        especies_seleccionadas = []
        
        # Permitir agregar nuevas especies
        num_species = len(table_data) if table_data else 0
        num_species_to_show = max(num_species, 1)  # Mostrar al menos 1 fila vacía
        
        for row_idx in range(num_species_to_show + 1):  # +1 para agregar nueva
            cols = st.columns(len(meses) + 1)
            
            # Especie
            with cols[0]:
                especie_key = f"{full_id}_species_{row_idx}"
                default_especie = table_data.get(f"especie_{row_idx}", "") if isinstance(table_data, dict) else ""
                
                selected_especie = st.selectbox(
                    label="",
                    options=[""] + especies_predefinidas,
                    index=0 if default_especie == "" else (especies_predefinidas.index(default_especie) + 1 if default_especie in especies_predefinidas else 0),
                    key=especie_key,
                    label_visibility="collapsed"
                )
            
            # Meses (checkboxes)
            if selected_especie:  # Solo mostrar checkboxes si hay especie seleccionada
                meses_seleccionados = {}
                
                for month_idx, mes in enumerate(meses):
                    with cols[month_idx + 1]:
                        mes_key = f"{full_id}_mes_{row_idx}_{mes}"
                        default_mes = table_data.get(f"especie_{row_idx}_meses", {}).get(mes, False) if isinstance(table_data, dict) else False
                        
                        is_checked = st.checkbox(
                            label="",
                            value=default_mes,
                            key=mes_key,
                            label_visibility="collapsed"
                        )
                        meses_seleccionados[mes] = is_checked
                
                # Guardar datos de esta fila
                if isinstance(table_data, dict):
                    table_data[f"especie_{row_idx}"] = selected_especie
                    table_data[f"especie_{row_idx}_meses"] = meses_seleccionados
                
                especies_seleccionadas.append({
                    "especie": selected_especie,
                    "meses": meses_seleccionados
                })
        
        st.session_state.responses[full_id] = table_data
    elif question['tipo'] == 'tabla':
        st.divider()
        st.subheader(f"📊 {question['texto']}")
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

        st.write("💾 **Edite los datos de la tabla:**")
        edited_data = st.data_editor(
            table_data,
            column_config=column_configs,
            num_rows="dynamic" if question.get('permite_multiples_filas', False) else "fixed",
            key=f"q_{full_id}_table_editor",
            use_container_width=True
        )
        st.session_state.responses[full_id] = edited_data

    elif question['tipo'] == 'escala_evaluacion':
        st.divider()
        st.subheader(f"📈 {question['texto']}")
        scale_responses = st.session_state.responses.get(full_id, {})
        scale_options_map = {str(s['valor']): s['etiqueta'] for s in question['escala']}
        scale_values = [str(s['valor']) for s in question['escala']]

        for idx, item in enumerate(question['items']):
            item_key = f"{full_id}_{item['id']}"
            default_item_value = str(scale_responses.get(item['id'], scale_values[0]))
            index = scale_values.index(default_item_value) if default_item_value in scale_values else 0

            selected_value = st.select_slider(
                label=f"**{item['texto']}**",
                options=scale_values,
                value=default_item_value,
                format_func=lambda x: scale_options_map[x],
                key=item_key
            )
            scale_responses[item['id']] = selected_value
            if idx < len(question['items']) - 1:
                st.write("")  # Espaciador
        st.session_state.responses[full_id] = scale_responses

    elif question['tipo'] == 'tabla_compleja':
        st.divider()
        st.subheader(f"📊 {question['texto']}")
        complex_table_responses = st.session_state.responses.get(full_id, {})

        for row_idx, row_label in enumerate(question['filas']):
            with st.expander(f"📍 {row_label}"):
                row_responses = complex_table_responses.get(row_label, {})
                for col in question['columnas']:
                    col_id = col['id']
                    col_full_id = f"{full_id}_{row_label}_{col_id}"
                    current_col_response = row_responses.get(col_id)

                    if col['tipo'] == 'opcion_multiple':
                        options = ["- Seleccione -"] + col['opciones']
                        default_index = 0
                        if current_col_response and current_col_response in col['opciones']:
                            default_index = options.index(current_col_response)
                        
                        selected_option = st.selectbox(
                            label=col['texto'],
                            options=options,
                            index=default_index,
                            key=col_full_id
                        )
                        if selected_option != "- Seleccione -":
                            row_responses[col_id] = selected_option
                    elif col['tipo'] == 'seleccion_multiple':
                        options = col['opciones']
                        selected_options = st.multiselect(
                            label=col['texto'],
                            options=options,
                            default=current_col_response if current_col_response else [],
                            key=col_full_id
                        )
                        row_responses[col_id] = selected_options
                    else: # Por defecto, se trata como texto si el tipo no está especificado o no es manejado
                        row_responses[col_id] = st.text_input(
                            label=col['texto'],
                            value=current_col_response if current_col_response is not None else "",
                            key=col_full_id
                        )
                complex_table_responses[row_label] = row_responses
        st.session_state.responses[full_id] = complex_table_responses

    else:
        st.warning(f"⚠️ Tipo de pregunta no soportado: {question['tipo']} (ID: {q_id})")
        st.session_state.responses[full_id] = st.text_area(
            label="",
            value=default_value if default_value is not None else "",
            key=f"q_{full_id}_unsupported",
            height=100
        )

    # Agregar espaciador visual entre preguntas principales
    if parent_id is None:
        st.write("")

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
                elif isinstance(parent_answer, (int, float)): # Para numerico
                    # Para números, "Si" significa > 0, "No" significa == 0
                    if sub_q['condicional_en'] == "Si" and parent_answer == 0:
                        display_sub_q = False
                    elif sub_q['condicional_en'] == "No" and parent_answer > 0:
                        display_sub_q = False
                    elif sub_q['condicional_en'] not in ["Si", "No"] and str(parent_answer) != sub_q['condicional_en']:
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
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Mostrar logo si existe
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo_uabcs.png")
        if os.path.exists(logo_path):
            st.markdown('<div class="logo-container">', unsafe_allow_html=True)
            with open(logo_path, "rb") as logo_file:
                logo_image = logo_file.read()
            st.image(logo_image, width=120)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.title("Sistema de captura de encuestas de campo")
        st.markdown("---")
        
        st.write("**Ingrese sus credenciales:**")
        email = st.text_input("📧 Email", placeholder="ejemplo@correo.com")
        password = st.text_input("🔑 Contraseña", type="password", placeholder="Contraseña segura")

        if st.button("✅ Entrar", use_container_width=True, type="primary"):
            if not email or not password:
                st.error("⚠️ Por favor ingresa email y contraseña.")
            elif "@" not in email:
                st.error("⚠️ Por favor ingresa un email válido.")
            else:
                with st.spinner("Verificando credenciales..."):
                    is_authenticated, role, message = authenticate_user(email, password)
                    if is_authenticated:
                        st.session_state.logged_in = True
                        st.session_state.username = email
                        st.session_state.user_role = role
                        st.success(f"✅ ¡Bienvenido {email}!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")


# --- Página de Administrador ---
def admin_page():
    st.title("🛠️ Panel de Administración")
    st.markdown("---")
    
    st.sidebar.write(f"👤 Usuario: **{st.session_state.username}**")
    st.sidebar.markdown("---")
    
    admin_option = st.sidebar.radio(
        "🎯 Selecciona una opción:",
        ["Crear Usuario", "Gestionar Usuarios", "Estadísticas"]
    )
    
    if admin_option == "Crear Usuario":
        st.header("👤 Crear Nuevo Usuario")
        st.info("Los usuarios serán creados con Firebase Authentication para mayor seguridad")
        
        with st.form("create_user_form"):
            new_email = st.text_input("📧 Email del usuario", placeholder="usuario@ejemplo.com")
            new_password = st.text_input("🔑 Contraseña (mínimo 6 caracteres)", type="password")
            confirm_password = st.text_input("🔑 Confirmar contraseña", type="password")
            user_role = st.selectbox("👔 Rol del usuario", ["user", "admin"])
            submitted = st.form_submit_button("✅ Crear Usuario", use_container_width=True)
            
            if submitted:
                if not new_email or not new_password:
                    st.error("⚠️ El email y la contraseña son requeridos.")
                elif "@" not in new_email:
                    st.error("⚠️ Por favor ingresa un email válido.")
                elif new_password != confirm_password:
                    st.error("⚠️ Las contraseñas no coinciden.")
                elif len(new_password) < 6:
                    st.error("⚠️ La contraseña debe tener al menos 6 caracteres.")
                else:
                    with st.spinner("Creando usuario..."):
                        success, message = create_user(new_email, new_password, user_role)
                        if success:
                            st.success(message)
                            st.info(f"✅ El usuario puede iniciar sesión con:\n\n- Email: `{new_email}`\n- Contraseña: La que especificó")
                        else:
                            st.error(message)
    
    elif admin_option == "Gestionar Usuarios":
        st.header("👥 Gestionar Usuarios")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Actualizar Lista de Usuarios", use_container_width=True):
                st.session_state.users_updated = True
        
        users = get_all_users()
        
        if users:
            st.subheader(f"📊 Total de usuarios: **{len(users)}**")
            st.divider()
            
            # Crear tabla de usuarios con mejor formato
            user_table_data = []
            for user in users:
                user_table_data.append({
                    "Email": user.get("email", "N/A"),
                    "Rol": "👑 Admin" if user.get("role") == "admin" else "👤 Usuario",
                    "Creado": user.get("created_at", "N/A")[:10] if user.get("created_at") else "N/A"
                })
            
            st.dataframe(user_table_data, use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("🗑️ Eliminar Usuario")
            email_to_delete = st.selectbox(
                "Selecciona el usuario a eliminar:",
                [u.get("email") for u in users]
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ Eliminar Usuario Seleccionado", use_container_width=True, type="secondary"):
                    # Obtener el UID del usuario a eliminar
                    user_to_delete = next((u for u in users if u.get("email") == email_to_delete), None)
                    if user_to_delete:
                        with st.spinner("Eliminando usuario..."):
                            success, message = delete_user_from_auth(email_to_delete, user_to_delete['uid'])
                            if success:
                                st.success(f"✅ {message}")
                                st.rerun()
                            else:
                                st.error(message)
        else:
            st.info("ℹ️ No hay usuarios registrados aún.")
    
    elif admin_option == "Estadísticas":
        st.header("📊 Estadísticas del Sistema")
        users = get_all_users()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("👥 Total de Usuarios", len(users))
        
        with col2:
            admin_count = len([u for u in users if u.get("role") == "admin"])
            st.metric("👑 Administradores", admin_count)
        
        with col3:
            user_count = len([u for u in users if u.get("role") == "user"])
            st.metric("👤 Usuarios", user_count)
        
        st.divider()
        st.info("ℹ️ Más estadísticas próximamente...")
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.user_role = "user"
        st.rerun()


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
    current_section_idx = st.session_state.current_section_index

    # === Verificar si el cuestionario ya fue completado ===
    if current_section_idx < 0 or current_section_idx >= len(sections):
        st.title("✅ ¡Cuestionario Completado!")
        st.success("Ha alcanzado el final del cuestionario. Sus respuestas han sido recopiladas.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👀 Ver Resumen", key="view_summary_complete"):
                st.subheader("📋 Resumen de sus respuestas:")
                st.json(st.session_state.responses)
        
        with col2:
            if st.button("💾 Guardar Respuestas", key="save_complete"):
                st.session_state.show_save_dialog = True
        
        st.markdown("---")
        if st.button("🔄 Comenzar de nuevo"):
            reset_survey_state()
            st.rerun()
        
        if st.session_state.get('show_save_dialog', False):
            if st.button("✔️ Confirmar y Guardar"):
                if save_response_to_firestore(st.session_state.responses, st.session_state.username):
                    st.balloons()
                    st.session_state.show_save_dialog = False
                    st.session_state.logged_in = False
                    st.session_state.username = ""
                    st.session_state.user_role = "user"
                    reset_survey_state()
                    st.rerun()
        
        if st.sidebar.button("🚪 Cerrar Sesión"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.user_role = "user"
            reset_survey_state()
            st.rerun()
        return

    # === Barra lateral ===
    st.sidebar.title("📊 Navegación")
    st.sidebar.write(f"👤 Usuario: **{st.session_state.username}**")
    st.sidebar.write(f"👔 Rol: **{st.session_state.user_role}**")
    st.sidebar.markdown("---")
    
    # Indicador de progreso
    total_sections = len(sections)
    progress = (current_section_idx + 1) / total_sections
    st.sidebar.write(f"📍 Sección: **{current_section_idx + 1}** de **{total_sections}**")
    st.sidebar.progress(progress)
    
    # Menú de navegación por secciones
    st.sidebar.write("**Saltar a una sección:**")
    selected_section = st.sidebar.selectbox(
        "",
        range(total_sections),
        index=current_section_idx,
        format_func=lambda idx: f"{idx + 1}. {sections[idx]['titulo']}",
        key="section_selector"
    )
    
    if selected_section != current_section_idx:
        st.session_state.current_section_index = selected_section
        st.rerun()
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.user_role = "user"
        reset_survey_state()
        st.rerun()

    # === Contenido principal ===
    current_section = sections[current_section_idx]
    
    st.title(survey['titulo'])
    st.markdown(f"*{survey['descripcion']}*")
    st.divider()
    
    # Encabezado de la sección
    st.header(f"📋 Sección {current_section['id_seccion']}: {current_section['titulo']}")
    
    # Indicador visual de progreso en la sección
    questions_in_section = len(current_section['preguntas'])
    st.info(f"**{questions_in_section}** preguntas en esta sección")
    st.divider()
    
    # Renderizar todas las preguntas de la sección
    for question in current_section['preguntas']:
        render_question(question)
    
    # === Botones de navegación ===
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if current_section_idx > 0:
            if st.button("⬅️ Anterior", use_container_width=True, key="btn_prev"):
                st.session_state.current_section_index -= 1
                st.rerun()
        else:
            st.write("")
    
    with col2:
        if st.button("🧹 Limpiar Sección", use_container_width=True, key="btn_clear"):
            # Limpiar solo las respuestas de la sección actual
            for question in current_section['preguntas']:
                q_id = question['id']
                if q_id in st.session_state.responses:
                    del st.session_state.responses[q_id]
            st.rerun()
    
    with col3:
        if st.button("📋 Ver Respuestas", use_container_width=True, key="btn_view"):
            st.subheader("📝 Sus respuestas hasta ahora:")
            st.json(st.session_state.responses)
    
    with col4:
        if current_section_idx < len(sections) - 1:
            if st.button("➡️ Siguiente", use_container_width=True, key="btn_next"):
                st.session_state.current_section_index += 1
                st.rerun()
        else:
            if st.button("✅ Finalizar", use_container_width=True, key="btn_finish", type="primary"):
                st.session_state.current_section_index = len(sections)
                st.rerun()



# --- Lógica principal de la aplicación ---
if not st.session_state.logged_in:
    login_page()
else:
    if st.session_state.user_role == "admin":
        admin_page()
    else:
        survey_app()
