import streamlit as st
import json
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import FieldFilter
import datetime
import os
from pydantic import BaseModel, ValidationError
from typing import List, Optional, Union, Any
import hashlib
import pandas as pd

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

# --- Estilos Visuales Personalizados (Tema Azul) ---
def apply_custom_styles():
    st.markdown("""
        <style>
            /* Títulos y Encabezados en Azul Institucional */
            h1, h2, h3 {
                color: #01579B !important;
            }
            /* Ajustes para el logo en la barra lateral: Centrado y tamaño controlado */
            [data-testid="stSidebar"] img {
                display: block;
                margin-left: auto;
                margin-right: auto;
                width: 80%;
                max-width: 180px;
                margin-bottom: 20px;
                filter: drop-shadow(0px 4px 4px rgba(0,0,0,0.1)); /* Sombra suave */
            }
            /* Borde sutil para separar la barra lateral */
            [data-testid="stSidebar"] {
                border-right: 1px solid #B3E5FC;
            }
        </style>
    """, unsafe_allow_html=True)

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
if 'role' not in st.session_state:
    st.session_state.role = ""
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
if 'current_response_id' not in st.session_state:
    st.session_state.current_response_id = None # ID del documento en Firestore (para borradores)

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
    obligatoria: Optional[bool] = True
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

def save_response_to_firestore(responses, username, status="completed", doc_id=None):
    """Guarda las respuestas recolectadas en Firestore."""
    try:
        if doc_id:
            doc_ref = db.collection(COLLECTION_NAME).document(doc_id)
        else:
            doc_ref = db.collection(COLLECTION_NAME).document()
        
        # Serializar respuestas (convertir objetos date a string ISO)
        serialized_responses = {
            k: v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v 
            for k, v in responses.items()
        }
        
        responses_to_save = {
            "user_id": username,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": status,
            "responses": serialized_responses
        }
        doc_ref.set(responses_to_save, merge=True)
        
        if status == "completed":
            st.success(f"¡Respuestas guardadas con éxito en Firestore! ID: {doc_ref.id}")
        return doc_ref.id
    except Exception as e:
        st.error(f"Error al guardar respuestas en Firestore: {e}")
        return None

def hash_password(password):
    """Genera un hash SHA-256 para la contraseña."""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    """
    Autentica al usuario verificando primero st.secrets (Super Admin)
    y luego la colección 'users' en Firestore.
    Retorna (bool, role).
    """
    # Eliminar espacios, pero respetar mayúsculas y minúsculas (Case Sensitive)
    username = username.strip()

    # 1. Verificar Super Admin en st.secrets
    try:
        if "app_credentials" in st.secrets:
            if username == st.secrets["app_credentials"]["username"].strip() and \
               password == st.secrets["app_credentials"]["password"]:
                return True, "admin"
    except Exception:
        pass # Continuar si no hay secretos configurados o error

    # 2. Verificar en Firestore
    try:
        doc_ref = db.collection('users').document(username)
        doc = doc_ref.get()
        if doc.exists:
            user_data = doc.to_dict()
            if user_data.get('password') == hash_password(password):
                return True, user_data.get('role', 'user')
    except Exception as e:
        print(f"Error autenticando en Firestore: {e}")
    
    return False, None

def create_user_in_db(new_username, new_password, role):
    """Crea un nuevo usuario en la colección 'users' de Firestore."""
    try:
        new_username = new_username.strip()
        doc_ref = db.collection('users').document(new_username)
        doc_ref.set({
            "username": new_username,
            "password": hash_password(new_password),
            "role": role,
            "created_at": firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        st.error(f"Error al crear usuario: {e}")
        return False

def get_all_users():
    """Obtiene la lista de todos los usuarios registrados en Firestore."""
    try:
        docs = db.collection('users').stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        st.error(f"Error al obtener usuarios: {e}")
        return []

def delete_user_from_db(username):
    """Elimina un usuario de la base de datos."""
    try:
        username = username.strip()
        db.collection('users').document(username).delete()
        return True
    except Exception as e:
        st.error(f"Error al eliminar usuario: {e}")
        return False

def load_user_draft(username):
    """Busca si el usuario tiene una encuesta en estado 'draft'."""
    try:
        # Buscar documentos del usuario que estén en borrador
        docs = db.collection(COLLECTION_NAME).where(filter=FieldFilter("user_id", "==", username)).where(filter=FieldFilter("status", "==", "draft")).stream()
        for doc in docs:
            return doc.id, doc.to_dict() # Retornar el primero que encuentre
    except Exception:
        pass
    return None, None

def get_csv_download_link(user_filter=None, start_date=None, end_date=None):
    """Genera un DataFrame de Pandas con los datos filtrados y lo convierte a CSV."""
    query = db.collection(COLLECTION_NAME)
    
    if user_filter:
        query = query.where(filter=FieldFilter("user_id", "==", user_filter))
        
    docs = query.stream()
    data = []
    for doc in docs:
        doc_data = doc.to_dict()
        
        # Filtrado por fecha en memoria (Python)
        if start_date and end_date:
            ts = doc_data.get("timestamp")
            # Verificar si es un objeto datetime válido
            if isinstance(ts, datetime.datetime):
                if not (start_date <= ts.date() <= end_date):
                    continue # Saltar este registro si está fuera del rango
            else:
                continue # Saltar si no tiene fecha válida y se activó el filtro

        # Aplanar estructura básica
        row = {
            "id_registro": doc.id,
            "usuario": doc_data.get("user_id"),
            "fecha_registro": doc_data.get("timestamp"),
            "estado": doc_data.get("status", "completed")
        }
        # Procesar respuestas
        responses = doc_data.get("responses", {})
        for k, v in responses.items():
            # Si es lista o dict (tablas/grids), convertir a JSON string para que quepa en una celda CSV
            if isinstance(v, (list, dict)):
                row[k] = json.dumps(v, ensure_ascii=False)
            else:
                row[k] = v
        data.append(row)
    
    if not data:
        return None
        
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode('utf-8')

def reset_survey_state():
    """Reinicia el estado del cuestionario para una nueva presentación."""
    st.session_state.current_section_index = 0
    st.session_state.current_question_index = 0
    st.session_state.responses = {}
    st.session_state.current_response_id = None
    # No es necesario recargar el JSON a menos que el archivo pueda cambiar
    # st.session_state.survey_loaded = False

def auto_save_draft():
    """Función auxiliar para autoguardar el borrador actual."""
    doc_id = save_response_to_firestore(
        st.session_state.responses, 
        st.session_state.username, 
        status="draft", 
        doc_id=st.session_state.current_response_id
    )
    if doc_id:
        st.session_state.current_response_id = doc_id
        st.toast("Borrador autoguardado", icon="💾")

def check_sub_question_condition(sub_q, parent_answer, parent_full_id=None):
    """Verifica si una sub-pregunta debe activarse basada en la respuesta del padre."""
    # Verificar condición primaria ('condicional_en')
    if 'condicional_en' in sub_q:
        # Si existe 'condicion_valor', se usa ese valor para comparar.
        # Si no, se usa el valor de 'condicional_en' (comportamiento legacy/simple).
        expected_value = sub_q.get('condicion_valor', sub_q['condicional_en'])

        if parent_answer is None:
            return False
        elif isinstance(parent_answer, list):
            if expected_value not in parent_answer:
                return False
        else:
            if str(parent_answer) != str(expected_value):
                return False

    # Verificar condición secundaria ('condicion_secundaria')
    if 'condicion_secundaria' in sub_q:
        secondary_q_id = sub_q['condicion_secundaria']['pregunta_id']
        secondary_q_values = sub_q['condicion_secundaria']['valores']
        
        # Construir ID completo para la pregunta secundaria (asumiendo hermandad)
        if parent_full_id:
            full_secondary_id = f"{parent_full_id}_{secondary_q_id}"
        else:
            full_secondary_id = secondary_q_id
            
        secondary_answer = st.session_state.responses.get(full_secondary_id)
        
        # Fallback: intentar ID absoluto si no se encuentra relativo
        if secondary_answer is None and parent_full_id:
             secondary_answer = st.session_state.responses.get(secondary_q_id)

        if secondary_answer is None:
            return False
        elif isinstance(secondary_answer, list):
            if not any(val in secondary_answer for val in secondary_q_values):
                return False
        else:
            if secondary_answer not in secondary_q_values:
                return False
    return True

def validate_question_recursive(question, parent_id, errors):
    """Valida recursivamente si las preguntas obligatorias tienen respuesta."""
    q_id = question['id']
    full_id = f"{parent_id}_{q_id}" if parent_id else q_id
    
    # 1. Validar la pregunta actual si es obligatoria
    if question.get('obligatoria', True) and question.get('tipo') != 'grupo_preguntas':
        response = st.session_state.responses.get(full_id)
        
        # Criterios de "vacío"
        is_empty = False
        if response is None:
            is_empty = True
        elif isinstance(response, str) and response.strip() == "":
            is_empty = True
        elif isinstance(response, list) and len(response) == 0:
            is_empty = True
        
        if is_empty:
            errors.append(f"Pregunta {q_id}: {question['texto']}")

    # 2. Validar sub-preguntas SOLO si están activas (condiciones cumplidas)
    if 'sub_preguntas' in question:
        parent_answer = st.session_state.responses.get(full_id)
        for sub_q in question['sub_preguntas']:
            if check_sub_question_condition(sub_q, parent_answer, parent_full_id=full_id):
                validate_question_recursive(sub_q, full_id, errors)

    # 3. Validar preguntas hijas de un grupo (grupo_preguntas)
    if 'preguntas' in question:
        for child_q in question['preguntas']:
            validate_question_recursive(child_q, full_id, errors)

def clear_question_responses_recursive(question, parent_id):
    """Elimina recursivamente las respuestas de una pregunta y sus descendientes del estado."""
    q_id = question['id']
    full_id = f"{parent_id}_{q_id}" if parent_id else q_id
    
    # 1. Eliminar la respuesta de la pregunta actual si existe
    if full_id in st.session_state.responses:
        del st.session_state.responses[full_id]
        
    # 2. Recorrer y limpiar sub-preguntas
    if 'sub_preguntas' in question:
        for sub_q in question['sub_preguntas']:
            clear_question_responses_recursive(sub_q, full_id)

    # 3. Recorrer preguntas de grupo (si aplica)
    if 'preguntas' in question:
        for child_q in question['preguntas']:
            clear_question_responses_recursive(child_q, full_id)

def validate_current_section():
    """Valida todas las preguntas de la sección actual."""
    survey = st.session_state.survey_data
    current_section = survey['secciones'][st.session_state.current_section_index]
    errors = []
    for question in current_section['preguntas']:
        validate_question_recursive(question, None, errors)
    return errors

@st.dialog("⚠️ Atención: Sección Incompleta")
def show_validation_warning(errors):
    st.warning("Para avanzar, debe responder las siguientes preguntas obligatorias:")
    for err in errors:
        st.markdown(f"**• {err}**")

def go_to_next_section():
    """Navega a la siguiente sección."""
    # Validar antes de avanzar
    errors = validate_current_section()
    if errors:
        show_validation_warning(errors)
        return False # Indicar fallo

    auto_save_draft() # Autoguardar al avanzar
    survey = st.session_state.survey_data
    sections = survey['secciones']

    if st.session_state.current_section_index < len(sections) - 1:
        st.session_state.current_section_index += 1
    else:
        # Fin del cuestionario
        st.session_state.current_section_index = -1
    return True # Indicar éxito

def go_to_previous_section():
    """Navega a la sección anterior."""
    auto_save_draft() # Autoguardar al retroceder
    if st.session_state.current_section_index > 0:
        st.session_state.current_section_index -= 1
    else:
        st.warning("Ya estás en la primera sección.")

    # --- Funciones de Renderizado de Widgets (Refactorización) ---

def _render_text_input(question, full_id, default_value):
    st.session_state.responses[full_id] = st.text_input(
        label=f"Respuesta para {question['id']}" + (" *" if question.get('obligatoria', True) else ""),
        value=default_value if default_value is not None else "",
        key=f"q_{full_id}",
        autocomplete="off"
    )

def _render_date_input(question, full_id, default_value):
    if default_value:
        if isinstance(default_value, (datetime.date, datetime.datetime)):
            date_val = default_value
        elif isinstance(default_value, str):
            try:
                date_val = datetime.datetime.strptime(default_value, "%Y-%m-%d").date()
            except ValueError:
                date_val = datetime.date.today()
        else:
            date_val = datetime.date.today()
    else:
        date_val = datetime.date.today()

    selected_date = st.date_input(
        label=f"Respuesta para {question['id']}" + (" *" if question.get('obligatoria', True) else ""),
        value=date_val,
        key=f"q_{full_id}"
    )
    st.session_state.responses[full_id] = selected_date

def _render_number_input(question, full_id, default_value):
    st.session_state.responses[full_id] = st.number_input(
        label=f"Respuesta para {question['id']}" + (" *" if question.get('obligatoria', True) else ""),
        value=default_value if default_value is not None else 0,
        key=f"q_{full_id}"
    )

def _render_select_input(question, full_id, default_value):
    options = question.get('opciones', ["Si", "No"])
    index = options.index(default_value) if default_value in options else None
    selected_option = st.selectbox(
        label=f"Respuesta para {question['id']}" + (" *" if question.get('obligatoria', True) else ""),
        options=options,
        index=index,
        placeholder="Seleccione una opción...",
        key=f"q_{full_id}"
    )
    st.session_state.responses[full_id] = selected_option

def _render_radio_input(question, full_id, default_value):
    options = question.get('opciones', ["Si", "No"])
    index = options.index(default_value) if default_value in options else None
    selected_option = st.radio(
        label=f"Respuesta para {question['id']}" + (" *" if question.get('obligatoria', True) else ""),
        options=options,
        index=index,
        key=f"q_{full_id}"
    )
    st.session_state.responses[full_id] = selected_option

def _render_multiselect(question, full_id, default_value):
    options = question['opciones']
    selected_options = st.multiselect(
        label=f"Seleccione una o varias opciones para {question['id']}" + (" *" if question.get('obligatoria', True) else ""),
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
                index = options.index(current_col_response) if current_col_response in options else None
                row_responses[col_id] = st.selectbox(
                    label=f"{col['texto']} para {row_label}",
                    options=options,
                    index=index,
                    placeholder="Seleccione...",
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
                    key=col_full_id,
                    autocomplete="off"
                )
        complex_table_responses[row_label] = row_responses
    st.session_state.responses[full_id] = complex_table_responses

# Diccionario de despacho para renderizar widgets
RENDER_HANDLERS = {
    'texto_abierto': _render_text_input,
    'fecha': _render_date_input,
    'numerico': _render_number_input,
    'opcion_multiple': _render_select_input,
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
            display_sub_q = check_sub_question_condition(sub_q, parent_answer, parent_full_id=full_id)

            if display_sub_q:
                render_question(sub_q, parent_id=full_id)
            else:
                # Limpieza recursiva robusta: elimina esta pregunta y toda su descendencia
                clear_question_responses_recursive(sub_q, full_id)


# --- Página de Autenticación ---
def login_page():
    apply_custom_styles() # Aplicar estilos visuales
    
    # Cargar datos para mostrar título y descripción en el login
    survey_data = load_survey_data(SURVEY_FILE_PATH)
    
    if survey_data:
        st.title(survey_data['titulo'])
        st.markdown(f"*{survey_data['descripcion']}*")
    else:
        st.title("Iniciar Sesión en la Encuesta")

    st.markdown("---")
    username = st.text_input("Usuario", autocomplete="username")
    password = st.text_input("Contraseña", type="password", autocomplete="current-password")

    if st.button("Entrar"):
        # Eliminar espacios, pero respetar mayúsculas y minúsculas
        username = username.strip()
        
        is_valid, role = authenticate_user(username, password)
        if is_valid:
            # Verificar si hay borradores pendientes
            draft_id, draft_data = load_user_draft(username)
            
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = role
            
            if draft_id:
                st.session_state.current_response_id = draft_id
                # Cargar respuestas del borrador
                if 'responses' in draft_data:
                    # Deserializar fechas si es necesario (simple check)
                    loaded_responses = draft_data['responses']
                    # Nota: Las fechas vienen como string ISO desde Firestore, 
                    # el renderizador _render_date_input ya maneja strings ISO, así que estamos bien.
                    st.session_state.responses = loaded_responses
                
                # Cargar sección donde se quedó
                if 'current_section' in draft_data:
                    st.session_state.current_section_index = draft_data['current_section']
                
                st.toast("¡Borrador recuperado! Continuando donde lo dejaste.", icon="📂")
                st.success(f"¡Bienvenido de nuevo {username}! Sesión recuperada.")
            else:
                st.success(f"¡Bienvenido {username} ({role})!")
            
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")


# --- Aplicación Principal del Cuestionario ---
def survey_app():
    apply_custom_styles() # Aplicar estilos visuales

    # Cargar datos siempre para reflejar cambios en el JSON inmediatamente
    st.session_state.survey_data = load_survey_data(SURVEY_FILE_PATH)
    if not st.session_state.survey_data:
        return

    survey = st.session_state.survey_data
    sections = survey['secciones']

    # Barra lateral para información del usuario y cerrar sesión
    st.sidebar.title("Navegación")
    st.sidebar.write(f"Usuario: **{st.session_state.username}**")
    
    # Espacio para Logotipo Institucional
    # Si tienes un archivo 'logo.png' en la carpeta raíz, se mostrará aquí.
    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(logo_path):
        st.sidebar.image(logo_path, width="stretch")
    else:
        st.sidebar.header("🐟 SurveyFisherman")

    # --- Panel de Administrador (Solo visible para admins) ---
    if st.session_state.role == 'admin':
        st.sidebar.markdown("---")
        st.sidebar.subheader("🛠️ Panel Admin")
        
        # 1. Gestión de Usuarios
        with st.sidebar.expander("Crear Usuario"):
            new_user = st.text_input("Nuevo Usuario", autocomplete="off")
            new_pass = st.text_input("Nueva Contraseña", type="password", autocomplete="new-password")
            new_role = st.selectbox("Rol", ["user", "admin"])
            if st.button("Crear"):
                if new_user and new_pass:
                    if create_user_in_db(new_user, new_pass, new_role):
                        st.success(f"Usuario {new_user} creado.")
                    else:
                        st.error("Error al crear usuario.")
                else:
                    st.warning("Complete todos los campos.")

        # 2. Gestión de Usuarios Existentes (Ver / Borrar)
        with st.sidebar.expander("Gestionar Usuarios"):
            users = get_all_users()
            if users:
                st.caption("Lista de usuarios registrados:")
                for u in users:
                    u_name = u.get('username', 'Sin nombre')
                    u_role = u.get('role', 'user')
                    
                    col1, col2 = st.columns([3, 1])
                    col1.text(f"👤 {u_name} ({u_role})")
                    if col2.button("🗑️", key=f"del_{u_name}", help="Eliminar usuario"):
                        if delete_user_from_db(u_name):
                            st.success(f"Eliminado: {u_name}")
                            st.rerun()
            else:
                st.info("No hay usuarios registrados.")

        # 3. Descarga de Datos
        with st.sidebar.expander("Descargar Datos"):
            st.write("Filtros de descarga:")
            
            # Filtro de Usuario
            users_list = get_all_users()
            user_options = ["Todos"] + [u['username'] for u in users_list]
            selected_user = st.selectbox("Filtrar por Usuario", user_options)
            
            # Filtro de Fechas
            use_dates = st.checkbox("Filtrar por Fechas")
            start_d, end_d = None, None
            if use_dates:
                start_d = st.date_input("Desde", datetime.date.today() - datetime.timedelta(days=7))
                end_d = st.date_input("Hasta", datetime.date.today())

            if st.button("Generar CSV"):
                u_filter = selected_user if selected_user != "Todos" else None
                csv_data = get_csv_download_link(u_filter, start_d, end_d)
                
                if csv_data:
                    st.download_button(
                        label="📥 Descargar CSV Filtrado",
                        data=csv_data,
                        file_name=f"encuesta_data_{datetime.date.today()}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No se encontraron datos con esos filtros.")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.session_state.current_response_id = None
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
            if save_response_to_firestore(
                st.session_state.responses, 
                st.session_state.username, 
                status="completed", 
                doc_id=st.session_state.current_response_id
            ):
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

    # --- Barra de Progreso ---
    total_sections = len(sections)
    progress_value = (st.session_state.current_section_index + 1) / total_sections
    st.progress(progress_value, text=f"Progreso: Sección {st.session_state.current_section_index + 1} de {total_sections}")

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
                if go_to_next_section():
                    st.rerun()

# --- Lógica principal de la aplicación ---
if not st.session_state.logged_in:
    login_page()
else:
    survey_app()
