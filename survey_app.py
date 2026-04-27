import streamlit as st
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud.firestore import FieldFilter
import datetime
import os
from pydantic import BaseModel, ValidationError
from typing import List, Optional, Union, Any
import hashlib
import pandas as pd
import requests
import re

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
            
            # Verificar si existen las claves necesarias para la cuenta de servicio (Admin SDK)
            # Si solo tenemos 'web_api_key', saltamos este paso para usar el archivo local
            if "private_key" in cred_dict:
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                st.toast("☁️ Modo Nube: Iniciado con Secrets", icon="☁️")
                return firestore.client()
    except Exception as e:
        # Solo advertir en consola, continuar intentando con archivo local
        print(f"Advertencia: No se pudo inicializar desde st.secrets: {e}")

    # 2. Intentar usar archivo local (Respaldo para Desarrollo Local)
    local_file = "surver-fisherman-uabcs-firebase-adminsdk-fbsvc-5c73dae273.json"
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
OLD_SURVEY_FILE_PATH = os.path.join(os.path.dirname(__file__), "json", "survey_old.json")
COLLECTION_NAME = "survey_responses" # Nombre de la colección en Firestore
USERS_COLLECTION = "survey_users" # Colección para almacenar roles de usuario

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
if 'current_menu' not in st.session_state:
    st.session_state.current_menu = "Mis Encuestas"
if 'view_survey_data' not in st.session_state:
    st.session_state.view_survey_data = None
if 'survey_version' not in st.session_state:
    st.session_state.survey_version = "Actual"

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

def save_response_to_firestore(responses, username, status="completed", doc_id=None, survey_version=None):
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
            "survey_version": survey_version or st.session_state.get('survey_version', 'Actual'),
            "responses": serialized_responses
        }
        doc_ref.set(responses_to_save, merge=True)
        
        if status == "completed":
            st.success(f"¡Respuestas guardadas con éxito en Firestore! ID: {doc_ref.id}")
        return doc_ref.id
    except Exception as e:
        st.error(f"Error al guardar respuestas en Firestore: {e}")
        return None

def authenticate_user(username, password):
    """
    Autentica al usuario usando la API REST de Firebase Authentication.
    Retorna (bool, role).
    """
    email = username.strip() # El nombre de usuario ahora es el email

    # Obtener la Web API Key de los secretos.
    # Esta clave es diferente a la del service account.
    # Se encuentra en la configuración del proyecto de Firebase -> General -> Your apps -> Web app.
    try:
        api_key = st.secrets["firebase"]["web_api_key"]
    except KeyError:
        return False, "Configuración 'web_api_key' no encontrada en secrets.toml."

    rest_api_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = {"email": email, "password": password, "returnSecureToken": True}

    try:
        r = requests.post(rest_api_url, json=payload)
        r.raise_for_status() # Lanza un error para respuestas 4xx/5xx
        
        # Si la autenticación es exitosa, obtener el rol del usuario desde Firestore
        user_data = r.json()
        uid = user_data.get("localId")
        
        user_doc = db.collection(USERS_COLLECTION).document(uid).get()
        
        if user_doc.exists:
            role = user_doc.to_dict().get("role", "user")
        else:
            # Si el usuario existe en Auth pero no en Firestore, lo creamos con rol 'user'
            role = "user"
            db.collection(USERS_COLLECTION).document(uid).set({"email": email, "role": role})

        return True, role
    except requests.exceptions.HTTPError as err:
        error_json = err.response.json().get("error", {})
        message = error_json.get("message", "Error desconocido.")
        if message == "INVALID_LOGIN_CREDENTIALS":
            return False, "Email o contraseña incorrectos."
        return False, f"Error de autenticación: {message}"
    except Exception as e:
        return False, f"Error de conexión: {e}"

def create_user_in_db(new_email, new_password, role):
    """Crea un nuevo usuario en Firebase Auth y guarda su rol en Firestore."""
    try:
        new_email = new_email.strip()
        # 1. Crear usuario en Firebase Authentication
        user = auth.create_user(email=new_email, password=new_password)
        
        # 2. Guardar el rol y email en Firestore usando el UID del usuario como ID del documento
        db.collection(USERS_COLLECTION).document(user.uid).set({
            "email": new_email,
            "role": role,
            "created_at": firestore.SERVER_TIMESTAMP
        })
        return True
    except auth.EmailAlreadyExistsError:
        st.error(f"El email '{new_email}' ya está registrado.")
        return False
    except Exception as e:
        st.error(f"Error al crear usuario: {str(e)}")
        return False

def update_user_role(uid, new_role):
    """Actualiza el rol de un usuario en Firestore."""
    try:
        db.collection(USERS_COLLECTION).document(uid).update({"role": new_role})
        return True
    except Exception as e:
        st.error(f"Error al actualizar el rol: {e}")
        return False

def get_all_users():
    """Obtiene la lista de todos los usuarios registrados en Firestore."""
    try:
        docs = db.collection(USERS_COLLECTION).stream()
        users_list = []
        for doc in docs:
            user_data = doc.to_dict()
            user_data['uid'] = doc.id # Agregar el UID del documento
            users_list.append(user_data)
        return users_list
    except Exception as e:
        st.error(f"Error al obtener usuarios: {e}")
        return []

def delete_user_from_db(username):
    """Elimina un usuario de la base de datos."""
    email_to_delete = username.strip()
    try:
        # 1. Obtener el usuario de Firebase Auth para conseguir su UID
        user = auth.get_user_by_email(email_to_delete)
        
        # 2. Eliminar el usuario de Firebase Auth
        auth.delete_user(user.uid)
        
        # 3. Eliminar el documento del usuario en Firestore
        db.collection(USERS_COLLECTION).document(user.uid).delete()
        
        return True
    except auth.UserNotFoundError:
        st.error(f"No se encontró el usuario con email '{email_to_delete}' para eliminar.")
        return False
    except Exception as e:
        st.error(f"Error al eliminar usuario: {str(e)}")
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

def get_user_surveys(username, is_admin=False):
    """Obtiene todas las encuestas. Si es admin, trae todas; si no, solo las del usuario."""
    try:
        if is_admin:
            docs = db.collection(COLLECTION_NAME).stream()
        else:
            docs = db.collection(COLLECTION_NAME).where(filter=FieldFilter("user_id", "==", username)).stream()
        surveys = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            surveys.append(data)
        return surveys
    except Exception as e:
        st.error(f"Error al obtener encuestas: {e}")
        return []

def delete_survey_from_db(survey_id):
    """Elimina permanentemente una encuesta (borrador o completada) de Firestore."""
    try:
        db.collection(COLLECTION_NAME).document(survey_id).delete()
        return True
    except Exception as e:
        st.error(f"Error al eliminar la encuesta: {e}")
        return False

def delete_all_old_surveys():
    """Elimina TODAS las encuestas marcadas con la versión 'Antigua'."""
    try:
        docs = db.collection(COLLECTION_NAME).where(filter=FieldFilter("survey_version", "==", "Antigua")).stream()
        count = 0
        for doc in docs:
            doc.reference.delete()
            count += 1
        return count
    except Exception as e:
        st.error(f"Error al eliminar masivamente: {e}")
        return -1

def import_surveys_from_csv(uploaded_file):
    """Importa encuestas antiguas desde un archivo CSV hacia Firestore mapeando estructuras complejas."""
    try:
        # Leer archivo como texto para evitar problemas con números/fechas
        df = pd.read_csv(uploaded_file, dtype=str)
        # Reemplazar NaN con None
        df = df.where(pd.notnull(df), None)
        
        def clean_val(val):
            if val is None or str(val).strip() in ['', '*', 'No aplica', 'no respondio', 'No contesto', 'No lo sé', 'nan', 'NaN']:
                return None
            return str(val).strip()

        def check_si(val):
            v = clean_val(val)
            return v is not None and v.lower() in ['1', 'si', 'sí', 'x', 'verdadero', 'true']
            
        success_count = 0
        for index, row in df.iterrows():
            r = {}
            
            # --- 1. MAPEO DIRECTO DE VARIABLES SIMPLES ---
            mapeo_directo = {
                "1.1": 'Lugar de la encuesta',
                "old_lat": 'Latitud Y ',
                "old_lon": 'Longitud X',
                "1.2": 'Encuestador',
                "2.1": 'Nombre encuestado',
                "old_2.2": 'Organización',
                "old_2.3": 'Años trabajando',
                "old_2.4": 'Municipio de origen',
                "old_2.4.1": 'Otro estado (especifique)',
                "2.5.1": 'que Cooperativa',
                "3.4": 'Estado Civil',
                "3.3": 'Escolaridad ',
                "3.1": 'Edad',
                "3.5": 'Hijos',
                "3.8": 'Dependientes económicos',
                "3.9": 'Tipo vivienda',
                "3.9.1": 'Monto de renta',
                "3.9.2.1": 'Material de piso',
                "3.9.2.2": 'Material de pared',
                "3.9.2.3": 'Material del techo',
                "3.10": 'Acceso a energía eléctrica',
                "3.11": 'Abastecimiento de agua',
                "3.12": 'Drenaje',
                "old_3.12.1": 'Servicio telefónico',
                "old_internet_hogar": 'Servicio de internet',
                "3.13": 'Personas en el hogar',
                "3.14": 'Acceso a servicios de salud',
                "3.14.1": 'Provedor de servicio médico',
                "3.15": 'Enfermo crónico en el hogar',
                "3.15.1": 'Que enfermedad cronico degenerativa',
                "3.16": 'Horas de recreación a la semana',
                "3.17": 'Ingresos complementarios por otro integrante',
                "3.17.1": 'Actividad del ingreso',
                "3.18": 'Ingreso mensual por pesca',
                "3.19": 'Promedio mensual de ingreso otros miembros del hogar',
                "3.5.1": 'Hijos2',
                "3.6": 'Escolaridad de los hijos',
                "7.1.1": 'Por que no dispone de los bienes anteriores',
                "7.2": 'Que actividades realiza con el telefono inteligente',
                "7.3": 'que actividades realiza con la computadora',
                "old_tv_paga": 'Tiene sistema de televición de paga',
                "old_tv_servicio": 'Que servicio de televisión tiene contratado',
                "old_tv_no_paga": 'Por que no tiene televisión de paga',
                "7.4": 'Tiene conexión de internet ',
                "7.4.1": 'Que tipo de conexión',
                "7.4.0": 'Por que no tiene internet',
                "old_internet_telmex": 'Tiene conexión fija de Telmex',
                "old_internet_celular": 'Tiene conexión de celular',
                "7.6": 'Utiliza redes sociales',
                "old_no_redes": 'No utiliza redes',
                "7.7": 'Utiliza alguna herramienta para llevar sus registros',
                "7.7.1": 'Que herramienta',
                "7.9": 'Estaría interesado en participar en talleres de capacitación',
                "7.9.1": 'Por que motivo',
                "7.9.2": 'Por que no le interesa',
                "7.10": 'Conoce alguna organización brindando estos servicios',
                "7.10.1": 'Cual',
                "8.1": 'Lleva registros de sus ingresos y gastos, o un presupuesto',
                "8.3": 'Por que no tiene una cuenta formal',
                "8.5": 'Sabe que es el Buró de Crédito',
                "8.5.1": 'Conoce su situación en el Buró',
                "8.6": 'Mantiene adeudos financieros',
                "old_8.6.1": 'Conoce alguna financiera adicional ',
                "old_cual2": 'Cual2',
                "8.7": 'En algún momento ha sido financiado',
                "8.7.1": 'Cual3',
                "8.7.2": 'Por que no',
                "8.8": 'Hay banco en tu comunidad',
                "8.9": 'Usted usa aplicación del banco',
                "8.10": 'Tus ahorros estan protejidos en los bancos',
                "8.11": 'Ha tomado algun curso de aahorro yo manejo financiero'
            }
            
            for key_id, col_name in mapeo_directo.items():
                val = clean_val(row.get(col_name))
                if val is not None:
                    r[key_id] = val

            # --- 2. AGRUPACIONES DE SELECCIÓN MÚLTIPLE (LISTAS) ---
            # 7.1 Bienes tecnológicos
            bienes = []
            if check_si(row.get('Tiene teléfono inteligente')): bienes.append("Teléfono inteligente")
            if check_si(row.get('Tiene GPS')): bienes.append("GPS")
            if check_si(row.get('Tinene ecosonda')): bienes.append("Ecosonda")
            if check_si(row.get('Tiene televisor')): bienes.append("Televisor")
            if check_si(row.get('Tiene computadora')): bienes.append("Computadora")
            if check_si(row.get('Tiene tablet')): bienes.append("Tablet")
            if check_si(row.get('Tiene sonar')): bienes.append("Sonar")
            if check_si(row.get('Tiene radio')): bienes.append("Radio")
            if bienes: r["7.1"] = bienes

            # 7.5 Actividades de internet
            acts_int = []
            if check_si(row.get('Información')): acts_int.append("Información")
            if check_si(row.get('Diversión')): acts_int.append("Diversión")
            if check_si(row.get('Contacto y comunicación familia y amigos')): acts_int.append("Contacto y comunicación familia y amigos")
            if check_si(row.get('Provedores, ventas y negocio')): acts_int.append("Provedores, ventas y negocio")
            if check_si(row.get('Mareas')): acts_int.append("Mareas")
            if check_si(row.get('Estado del tiempo')): acts_int.append("Estado del tiempo")
            if acts_int: r["7.5"] = acts_int

            # 7.6.1 Redes sociales
            redes = []
            if check_si(row.get('Facebook')): redes.append("Facebook")
            if check_si(row.get('Instagram')): redes.append("Instagram")
            if check_si(row.get('Whatsapp')): redes.append("Whatsapp")
            if check_si(row.get('Business suit')): redes.append("Business suit")
            if check_si(row.get('Tik tok')): redes.append("Tik tok")
            if redes: r["7.6.1"] = redes
            
            # 7.8 Herramientas de registro
            herramientas = []
            if check_si(row.get('Programa o App')): herramientas.append("Programa o App")
            if check_si(row.get('GPS localización precisa')): herramientas.append("GPS localización precisa")
            if check_si(row.get('Sonar para dancos de peces y profundidad')): herramientas.append("Sonar para dancos de peces y profundidad")
            if check_si(row.get('App para gestión de capturas')): herramientas.append("App para gestión de capturas")
            if check_si(row.get('Comunicación satelital')): herramientas.append("Comunicación satelital")
            if check_si(row.get('Registros de la Unidad Económica')): herramientas.append("Registros de la Unidad Económica")
            if herramientas: r["7.8"] = herramientas
            
            # 8.2.1 Cuentas financieras
            cuentas = []
            if check_si(row.get('Cuenta con ONG')): cuentas.append("Cuenta con ONG")
            if check_si(row.get('Cuenta del Bienestar')): cuentas.append("Cuenta del Bienestar")
            if check_si(row.get('Cuenta con prestamista ')): cuentas.append("Cuenta con prestamista")
            if check_si(row.get('Cuenta en Banco')): cuentas.append("Cuenta en Banco")
            if check_si(row.get('Cuenta con apoyo de familiares')): cuentas.append("Cuenta con apoyo de familiares")
            if check_si(row.get('Microfinancieras')): cuentas.append("Microfinancieras")
            if check_si(row.get('Sociedades de credito')): cuentas.append("Sociedades de crédito")
            if cuentas: r["8.2.1"] = cuentas

            # --- 3. MATRIZ COMPLEJA 8.14 (PRÉSTAMOS) ---
            matriz_prestamos = {}
            filas_matriz = {
                "Organización no gubernamental (ONG)": ['en ONG', 'en ONG3', 'En ONG2', 'ONG'],
                "Apoyo Gubernamental (Bienestar)": ['Bienestar y gobierno', 'Prestamo gobierno', 'Gobierno', 'Gobierno2'],
                "Prestamista informal": ['Prestamista informal', 'Prestamista informal4', 'Prestamista informal2', 'Prestamista informal3'],
                "Prestamista formal (banco/institucion financiera)": ['Prestamista formal (banco/institución financiera)', 'Prestamista formal', 'Banco', 'Banco2'],
                "Amigos o familiares": ['Amigos o familiares', 'Amigos o familia', 'Amigos o familiares3', 'Amigos o familiares2'],
                "Microfinanzas o préstamos grupales": ['Microfinanciera', 'Micro financiera', 'Microfinanciera2', 'Microfinanciera3'],
                "Grupos informales de crédito/ahorro (sociedades funerarias, cundinas, etc.)": ['Sociedades de crédito', 'Sociedades financieras', 'Sociedades de crédito2', 'Sociedades2']
            }

            for nombre_fila, columnas_excel in filas_matriz.items():
                fila_data = {}
                v1, v2, v3, v4 = [clean_val(row.get(c)) for c in columnas_excel]
                if v1: fila_data["8.14.1"] = v1
                if v2: fila_data["8.14.2"] = v2
                if v3: fila_data["8.14.3"] = [v3]
                if v4: fila_data["8.14.4"] = [v4]
                if fila_data: matriz_prestamos[nombre_fila] = fila_data
                    
            if matriz_prestamos:
                r["8.14"] = matriz_prestamos

            # --- 4. GUARDAR EN FIREBASE ---
            if r:
                # Guardar directo en Firebase marcándolo como "Antigua"
                save_response_to_firestore(
                    r, 
                    st.session_state.username, 
                    status="completed",
                    survey_version="Antigua"
                )
                success_count += 1
        return success_count
    except Exception as e:
        st.error(f"Error en la importación: {e}")
        return -1

def _render_readonly_question(q, responses, parent_id=""):
    """Renderiza recursivamente una pregunta y su respuesta en modo solo lectura."""
    q_id = q['id']
    full_id = f"{parent_id}_{q_id}" if parent_id else q_id
    
    # Comprobar si esta pregunta tiene respuesta
    if full_id in responses:
        ans = responses[full_id]
        st.markdown(f"**{q['texto']}**")
        
        if isinstance(ans, list):
            if len(ans) > 0 and isinstance(ans[0], dict):
                # Respuesta tipo tabla dinámica
                st.dataframe(ans, use_container_width=True)
            else:
                # Respuesta de selección múltiple normal
                st.write(", ".join(map(str, ans)) if ans else "*Sin respuesta*")
        elif isinstance(ans, dict):
            # Tablas complejas, grid o escalas
            for k, v in ans.items():
                if isinstance(v, list):
                    st.write(f"- **{k}**: {', '.join(map(str, v)) if v else 'Ninguno'}")
                elif isinstance(v, dict):
                    st.write(f"- **{k}**:")
                    for sub_k, sub_v in v.items():
                        st.write(f"  - *{sub_k}*: {sub_v}")
                else:
                    st.write(f"- **{k}**: {v}")
        else:
            # Respuestas escalares (texto, número, fecha, etc)
            st.write(str(ans) if ans is not None and str(ans).strip() != "" else "*Sin respuesta*")
            
    # Procesar sub-preguntas (independientemente de si el padre tuvo respuesta para no perder nada)
    if 'sub_preguntas' in q:
        for sub_q in q['sub_preguntas']:
            _render_readonly_question(sub_q, responses, full_id)
            
    # Procesar grupos de preguntas
    if 'preguntas' in q:
        for child_q in q['preguntas']:
            _render_readonly_question(child_q, responses, full_id)

def render_readonly_view():
    """Renderiza la página completa de detalle de una encuesta completada."""
    survey_record = st.session_state.get('view_survey_data')
    if not survey_record:
        st.warning("No hay encuesta seleccionada.")
        if st.button("Volver a Mis Encuestas"):
            st.session_state.current_menu = "Mis Encuestas"
            st.rerun()
        return
        
    col1, col2 = st.columns([3, 1])
    with col1:
        st.header("📄 Detalle de Encuesta")
        st.write(f"**ID de Registro:** `{survey_record['id']}` | **Fecha:** {str(survey_record.get('timestamp', ''))[:16]}")
    with col2:
        if st.button("⬅️ Volver", use_container_width=True):
            st.session_state.current_menu = "Mis Encuestas"
            st.session_state.view_survey_data = None
            st.rerun()
            
    st.divider()
    
    responses = survey_record.get("responses", {})
    survey_schema = st.session_state.survey_data
    
    if survey_schema:
        for section in survey_schema['secciones']:
            st.subheader(f"Sección {section['id_seccion']}: {section['titulo']}")
            
            skip_key = f"skip_section_{section['id_seccion']}"
            if responses.get(skip_key, False):
                st.info("⏭️ Esta sección fue omitida por el encuestado (Sin respuesta).")
            else:
                for q in section['preguntas']:
                    _render_readonly_question(q, responses)
            st.divider()

def render_user_surveys_view():
    """Renderiza la vista de lista de encuestas del usuario (Dashboard)."""
    is_admin = st.session_state.role == 'admin'
    
    st.header("📋 Todas las Encuestas" if is_admin else "📋 Mis Encuestas")
    st.write("Aquí puedes consultar el historial de todas las encuestas capturadas." if is_admin else "Aquí puedes consultar el historial de las encuestas que has capturado.")
    
    with st.spinner("Cargando encuestas..."):
        surveys = get_user_surveys(st.session_state.username, is_admin)
    
    if not surveys:
        st.info("Aún no has capturado ninguna encuesta o no hay borradores guardados.")
        return

    # --- Filtro por Localidad y Contador ---
    localidades = set()
    for survey in surveys:
        resp = survey.get("responses", {})
        loc = resp.get("1.1")
        if loc and str(loc).strip() != "":
            localidades.add(str(loc).strip())
            
    localidades_lista = ["Todas"] + sorted(list(localidades))
    
    col_filtro, col_metric = st.columns([3, 1])
    with col_filtro:
        filtro_localidad = st.selectbox("🌍 Filtrar por Localidad (Lugar de la encuesta):", localidades_lista)
        
    surveys_filtradas = []
    for survey in surveys:
        if filtro_localidad == "Todas":
            surveys_filtradas.append(survey)
        else:
            resp = survey.get("responses", {})
            loc = resp.get("1.1")
            if loc and str(loc).strip() == filtro_localidad:
                surveys_filtradas.append(survey)
                
    with col_metric:
        st.metric(label="📊 Total de encuestas", value=len(surveys_filtradas))
        
    st.divider()
    
    if not surveys_filtradas:
        st.warning(f"No se encontraron encuestas para la localidad: {filtro_localidad}")
        return

    for survey in surveys_filtradas:
        status = survey.get("status", "desconocido")
        status_icon = "✅" if status == "completed" else "📝"
        status_text = "Completada" if status == "completed" else "Borrador"
        date_str = str(survey.get("timestamp", "Fecha desconocida"))[:16]
        user_info = f" | 👤 {survey.get('user_id', 'Desconocido')}" if is_admin else ""
        
        with st.expander(f"{status_icon} ID: {survey['id']} | {status_text} | {date_str}{user_info}"):
            st.write("Seleccione una opción para interactuar con este registro.")
            
            col1, col2 = st.columns(2)
            with col1:
                is_owner = survey.get("user_id") == st.session_state.username
                
                # Permitir continuar el borrador solo si el usuario es el creador del mismo
                if status == "draft" and is_owner:
                    if st.button("✏️ Continuar Borrador", key=f"edit_{survey['id']}"):
                        st.session_state.current_response_id = survey['id']
                        st.session_state.responses = survey.get("responses", {})
                        st.session_state.current_menu = "Nueva Encuesta"
                        st.rerun()
                
                # Mostrar el botón de detalle si está completada o si el usuario es admin (para ver borradores ajenos)
                if status == "completed" or is_admin:
                    if st.button("👀 Ver Detalle", key=f"view_{survey['id']}"):
                        st.session_state.view_survey_data = survey
                        st.session_state.current_menu = "Ver Encuesta"
                        st.rerun()
            with col2:
                # Eliminar exclusivo para administradores
                if is_admin:
                    # Agregamos type="primary" pero advertimos visualmente, en un futuro se puede agregar un confirm dialog
                    if st.button("🗑️ Eliminar", key=f"del_survey_{survey['id']}"):
                        if delete_survey_from_db(survey['id']):
                            st.toast(f"Registro {survey['id']} eliminado.", icon="🗑️")
                            st.rerun()

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
            "estado": doc_data.get("status", "completed"),
            "version": doc_data.get("survey_version", "Actual")
        }
        # Procesar respuestas
        responses = doc_data.get("responses", {})
        for k, v in responses.items():
            if isinstance(v, dict):
                # Aplanar diccionarios (Ej. escalas, grids)
                for sub_k, sub_v in v.items():
                    flat_key = f"{k}_{sub_k}"
                    if isinstance(sub_v, dict):
                        # Aplanar un nivel más (Ej. tablas complejas)
                        for sub_sub_k, sub_sub_v in sub_v.items():
                            flat_sub_key = f"{flat_key}_{sub_sub_k}"
                            if isinstance(sub_sub_v, list):
                                row[flat_sub_key] = ", ".join(map(str, sub_sub_v))
                            else:
                                row[flat_sub_key] = sub_sub_v
                    elif isinstance(sub_v, list):
                        row[flat_key] = ", ".join(map(str, sub_v))
                    else:
                        row[flat_key] = sub_v
            elif isinstance(v, list):
                if len(v) > 0 and isinstance(v[0], dict):
                    # Tablas simples (lista de dicts): dejamos como JSON para evitar columnas infinitas
                    row[k] = json.dumps(v, ensure_ascii=False)
                else:
                    # Listas simples de selección múltiple -> separados por comas
                    row[k] = ", ".join(map(str, v))
            else:
                row[k] = v
        data.append(row)

    if not data:
        return None
        
    df = pd.DataFrame(data)
    
    # --- Ordenar las columnas de manera lógica ---
    def sort_col(col_name):
        metadata_cols = ["id_registro", "usuario", "fecha_registro", "estado", "version"]
        if col_name in metadata_cols:
            return (0, metadata_cols.index(col_name), str(col_name))
        elif str(col_name).startswith("skip_section_"):
            try:
                num = int(str(col_name).split("_")[-1])
                return (1, [num], str(col_name))
            except ValueError:
                return (1, [999], str(col_name))
        else:
            # Extraer números para ordenamiento natural (ej. '1.2' se alinea antes que '1.10')
            nums = [int(n) for n in re.findall(r'\d+', str(col_name))]
            return (2, nums, str(col_name))
            
    sorted_columns = sorted(df.columns, key=sort_col)
    df = df[sorted_columns]
    
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
    
    skip_key = f"skip_section_{current_section['id_seccion']}"
    if st.session_state.responses.get(skip_key, False):
        return [] # Retornar sin errores si la sección entera está marcada como omitida
        
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
    username = st.text_input("Email", autocomplete="username", placeholder="tu@email.com")
    password = st.text_input("Contraseña", type="password", autocomplete="current-password")

    if st.button("Entrar"):
        # Eliminar espacios, pero respetar mayúsculas y minúsculas
        username = username.strip()
        
        is_valid, result = authenticate_user(username, password)
        if is_valid:
            # Verificar si hay borradores pendientes
            draft_id, draft_data = load_user_draft(username)
            
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = result # El rol viene en el resultado
            
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
                st.success(f"¡Bienvenido {username} ({result})!")
            
            st.rerun()
        else:
            st.error(result) # Mostrar el mensaje de error devuelto por la función


# --- Aplicación Principal del Cuestionario ---
def survey_app():
    apply_custom_styles() # Aplicar estilos visuales

    # Determinar qué JSON cargar según la versión seleccionada
    current_path = SURVEY_FILE_PATH if st.session_state.survey_version == "Actual" else OLD_SURVEY_FILE_PATH
    
    st.session_state.survey_data = load_survey_data(current_path)
    
    if not st.session_state.survey_data:
        if st.session_state.survey_version != "Actual":
            st.error("⚠️ Archivo 'survey_old.json' no encontrado. Por favor cree este archivo en la carpeta 'json/'.")
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

    # --- Menú de Navegación del Usuario ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Menú Principal")
    
    if st.sidebar.button(
        "Mis Encuestas", 
        use_container_width=True,
        type="primary" if st.session_state.current_menu in ["Mis Encuestas", "Ver Encuesta"] else "secondary"
    ):
        st.session_state.current_menu = "Mis Encuestas"
        st.rerun()
        
    if st.sidebar.button(
        "Nueva Encuesta", 
        use_container_width=True,
        type="primary" if st.session_state.current_menu == "Nueva Encuesta" else "secondary"
    ):
        st.session_state.current_menu = "Nueva Encuesta"
        reset_survey_state() # Limpiar el estado para iniciar una encuesta en blanco
        st.rerun()
        
    # Selector de Versión de Encuesta (Solo visible al crear Nueva Encuesta)
    if st.session_state.current_menu == "Nueva Encuesta":
        st.sidebar.markdown("---")
        new_version = st.sidebar.radio("Versión a Capturar", ["Actual", "Antigua"], index=0 if st.session_state.survey_version == "Actual" else 1)
        if new_version != st.session_state.survey_version:
            st.session_state.survey_version = new_version
            reset_survey_state() # Reiniciar estado para evitar conflictos entre JSONs
            st.rerun()

    # --- Panel de Administrador (Solo visible para admins) ---
    if st.session_state.role == 'admin':
        st.sidebar.markdown("---")
        st.sidebar.subheader("🛠️ Panel Admin")
        
        # 1. Gestión de Usuarios
        with st.sidebar.expander("Crear Usuario"):
            new_user = st.text_input("Nuevo Email de Usuario", autocomplete="off")
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
                st.caption("Gestionar roles y eliminar usuarios:")
                for i, user_data in enumerate(users):
                    email = user_data.get('email', 'Sin email')
                    current_role = user_data.get('role', 'user')
                    uid = user_data.get('uid')

                    # No permitir que el admin actual se degrade a sí mismo o se elimine
                    is_current_user = (email == st.session_state.username)

                    col1, col2, col3 = st.columns([2, 1.5, 0.8])
                    
                    with col1:
                        st.write(email)
                    
                    with col2:
                        roles = ["admin", "user"]
                        # Deshabilitar el cambio de rol para el usuario actual
                        new_role = st.selectbox(
                            "Rol", 
                            roles, 
                            index=roles.index(current_role), 
                            key=f"role_{uid}",
                            label_visibility="collapsed",
                            disabled=is_current_user
                        )
                        if new_role != current_role:
                            if update_user_role(uid, new_role):
                                st.toast(f"Rol de {email} actualizado a {new_role}")
                                st.rerun() # Recargar para reflejar el cambio
                    
                    with col3:
                        if st.button("🗑️", key=f"del_{uid}", help="Eliminar usuario", disabled=is_current_user):
                            if delete_user_from_db(email):
                                st.toast(f"Usuario {email} eliminado.")
                                st.rerun()
            else:
                st.info("No hay usuarios registrados.")

        # 3. Descarga de Datos
        with st.sidebar.expander("Descargar Datos"):
            st.write("Filtros de descarga:")
            
            # Filtro de Usuario
            users_list = get_all_users()
            user_options = ["Todos"] + [u.get('email', 'N/A') for u in users_list]
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
                
        # 4. Importador Masivo (CSV)
        with st.sidebar.expander("⬆️ Importar CSV Antiguo"):
            st.write("Sube tu archivo `.csv` con las encuestas viejas. Recuerda que los encabezados de las columnas deben ser los IDs (ej. `1.1`, `old_lat`).")
            uploaded_csv = st.file_uploader("Seleccionar CSV", type=['csv'])
            if uploaded_csv is not None:
                if st.button("Subir a Firebase"):
                    with st.spinner("Importando encuestas..."):
                        count = import_surveys_from_csv(uploaded_csv)
                        if count > 0:
                            st.success(f"¡Se importaron {count} encuestas exitosamente!")
                            
        # 5. Deshacer Importación (Peligro)
        with st.sidebar.expander("⚠️ Deshacer Importación"):
            st.warning("Esto eliminará TODAS las encuestas en la base de datos que estén marcadas como 'Antigua'.")
            if st.button("Borrar Encuestas Antiguas"):
                with st.spinner("Eliminando registros..."):
                    del_count = delete_all_old_surveys()
                    if del_count >= 0:
                        st.success(f"¡Se eliminaron {del_count} encuestas antiguas exitosamente!")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.session_state.current_response_id = None
        st.session_state.current_menu = "Mis Encuestas"
        reset_survey_state() # Limpiar el estado de la encuesta al cerrar sesión
        st.rerun()
    st.sidebar.markdown("---")

    # Enrutar a la vista correspondiente
    if st.session_state.current_menu == "Mis Encuestas":
        render_user_surveys_view()
        return
    elif st.session_state.current_menu == "Ver Encuesta":
        render_readonly_view()
        return

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
                st.session_state.current_menu = "Mis Encuestas"
                st.rerun()
            else:
                st.error("Hubo un problema al guardar sus respuestas.")
        if st.button("Volver a empezar"):
            reset_survey_state()
            st.session_state.current_menu = "Mis Encuestas"
            st.rerun()
        return

    current_section = sections[st.session_state.current_section_index]
    questions = current_section['preguntas']

    # --- Barra de Progreso ---
    total_sections = len(sections)
    progress_value = (st.session_state.current_section_index + 1) / total_sections
    st.progress(progress_value, text=f"Progreso: Sección {st.session_state.current_section_index + 1} de {total_sections}")

    st.header(f"Sección {current_section['id_seccion']}: {current_section['titulo']}")
    
    # --- Opción para omitir la sección completa ---
    skip_key = f"skip_section_{current_section['id_seccion']}"
    is_skipped_default = st.session_state.responses.get(skip_key, False)
    
    is_skipped = st.checkbox("⏭️ **Marcar toda la sección como 'Sin respuesta' (Omitir)**", value=is_skipped_default, key=f"chk_{skip_key}")
    st.session_state.responses[skip_key] = is_skipped

    if not is_skipped:
        # Renderizar todas las preguntas de la sección
        for question in questions:
            st.subheader(f"Pregunta {question['id']}")
            render_question(question)
            st.markdown("---")
    else:
        st.info("ℹ️ Sección omitida. Se ignorará la validación obligatoria y puede continuar a la siguiente sección.")
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
