# Configuración de Firebase Authentication

## Pasos requeridos para que funcione la autenticación por email

### 1. Habilitar Firebase Authentication
- Ve a [Firebase Console](https://console.firebase.google.com/)
- Selecciona el proyecto `survey-central-d4d22`
- Ve a **Authentication** en el menú izquierdo
- Haz clic en **Get started**
- Selecciona el proveedor **Email/Password**
- Haz clic en **Enable**
- Guarda los cambios

### 2. Crear el usuario admin (si aún no existe)
- En Firebase Console → **Authentication** → **Users**
- Haz clic en **Add user**
- Email: `admin@survey.com`
- Contraseña: `Admin@123456` (o la que prefieras)
- Haz clic en **Create user**

### 3. Ejecutar la aplicación
```powershell
conda activate Streamlit
streamlit run survey_app.py
```

### 4. Iniciar sesión
- Email: `admin@survey.com`
- Contraseña: `Admin@123456`

## Características

### Panel de Admin
- **Crear Usuario**: Crear nuevos usuarios con email y contraseña
- **Gestionar Usuarios**: Ver, eliminar usuarios y asignar roles
- Los usuarios pueden ser `user` (encuestador) o `admin` (administrador)

### Encuestadores
- Los usuarios de tipo `user` verán las pestañas de secciones
- Pueden llenar la encuesta y guardar las respuestas en Firestore
- No pueden acceder al panel de administración

## Notas de Seguridad

⚠️ **En producción:**
- Cambiar la contraseña del admin
- Usar variables de entorno para credenciales sensibles
- Habilitar verificación de email
- Implementar restablecimiento de contraseña por email
- Usar autenticación multi-factor (MFA)

