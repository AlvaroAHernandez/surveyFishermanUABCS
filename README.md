# surveyFishermanUABCS

Aplicación web de encuesta para el proyecto de investigación **"Inclusión financiera para el desarrollo productivo del sector pesquero: un pilar estratégico de BCS, México — Acuicultura y pesca de pequeña escala"** (Clave PEE-2025-G-507 SECIHTY), desarrollado en la Universidad Autónoma de Baja California Sur (UABCS).

---

## Propósito del Proyecto

El objetivo central del proyecto es **determinar los niveles de inclusión financiera y digital** en el sector pesquero y acuícola de pequeña escala en Baja California Sur, México. La encuesta recoge información de pescadores, cooperativistas, permisionarios y productores acuícolas de diversas localidades del estado, así como de sus familias.

Con los datos obtenidos se busca:

- Identificar barreras de acceso a servicios financieros formales (cuentas bancarias, créditos, seguros, ahorro).
- Evaluar el nivel de adopción y uso de Tecnologías de la Información y Comunicación (TIC) en la actividad pesquera.
- Proponer mecanismos y acciones que reduzcan la vulnerabilidad económica de estas comunidades y favorezcan su inclusión financiera y tecnológica.

---

## Metodología

### Instrumento de recolección de datos

El cuestionario está estructurado en **8 secciones temáticas**:

| # | Sección |
|---|---------|
| 1 | Datos de Identificación |
| 2 | Información del Encuestado |
| 3 | Información Demográfica |
| 4 | Aspectos Económicos Determinantes |
| 5 | Relación con Compradores y Articulación Comercial |
| 6 | Acuicultura-Cultivo |
| 7 | Uso de Tecnologías de la Información y Comunicación en la Actividad Pesquera |
| 8 | Inclusión Financiera |

Las preguntas combinan distintos formatos: respuesta abierta, opción múltiple, selección múltiple, preguntas Sí/No con sub-preguntas condicionales, tablas de datos y escalas de evaluación. El cuestionario se define completamente en el archivo `json/survey.json`, lo que facilita su mantenimiento y actualización sin modificar el código de la aplicación.

### Aplicación web

La encuesta se implementa como una aplicación **Streamlit** (`survey_app.py`) con las siguientes características:

- **Autenticación básica**: acceso por usuario y contraseña antes de iniciar el cuestionario.
- **Navegación pregunta a pregunta**: el encuestador avanza y retrocede entre preguntas de forma secuencial, dentro de cada sección.
- **Lógica condicional**: sub-preguntas que se muestran u ocultan dinámicamente según las respuestas previas.
- **Persistencia de respuestas**: las respuestas se mantienen en el estado de sesión de Streamlit durante toda la sesión del encuestador.
- **Almacenamiento en la nube**: al finalizar la encuesta, las respuestas se guardan en **Google Firebase Firestore**, junto con el identificador del encuestador y una marca de tiempo del servidor.
- **Configuración segura de credenciales**: las credenciales de Firebase se gestionan mediante los *Secrets* de Streamlit (`secrets.toml`) para evitar exponer información sensible en el repositorio.

### Flujo de trabajo

```
Encuestador inicia sesión
        ↓
Carga de cuestionario desde survey.json
        ↓
Navegación pregunta a pregunta (con sub-preguntas condicionales)
        ↓
Revisión y confirmación de respuestas
        ↓
Guardado automático en Firebase Firestore
        ↓
Opción de iniciar una nueva encuesta
```

---

## Productos Generados

| Producto | Descripción |
|----------|-------------|
| **Aplicación web de encuesta** | Interfaz Streamlit lista para ser desplegada en Streamlit Community Cloud u otro servidor compatible con Python. |
| **Cuestionario estructurado en JSON** | Archivo `json/survey.json` que define todas las secciones, preguntas, tipos de respuesta y lógica condicional del instrumento. |
| **Base de datos de respuestas** | Colección `survey_responses` en Firebase Firestore con las respuestas de cada encuestado, su identificador y fecha/hora de registro. |
| **Datos para análisis** | Las respuestas almacenadas en Firestore pueden exportarse para su análisis estadístico, permitiendo generar indicadores de inclusión financiera y digital para el sector pesquero y acuícola de BCS. |

---

## Estructura del Repositorio

```
surveyFishermanUABCS/
├── survey_app.py        # Aplicación principal de Streamlit
├── json/
│   └── survey.json      # Definición del cuestionario
└── README.md
```

---

## Requisitos y Configuración

1. **Instalar dependencias**:
   ```bash
   pip install streamlit firebase-admin
   ```

2. **Configurar credenciales de Firebase**: Crea el archivo `.streamlit/secrets.toml` con las credenciales de tu cuenta de servicio de Firebase:
   ```toml
   [firebase]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "your-private-key-id"
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "your-client-email@your-project-id.iam.gserviceaccount.com"
   client_id = "your-client-id"
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-client-email.iam.gserviceaccount.com"
   universe_domain = "googleapis.com"
   ```

3. **Ejecutar la aplicación**:
   ```bash
   streamlit run survey_app.py
   ```

---

## Institución

**Universidad Autónoma de Baja California Sur (UABCS)**  
Proyecto PEE-2025-G-507 SECIHTY