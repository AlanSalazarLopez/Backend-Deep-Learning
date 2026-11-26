# Referencia del frontend (Flutter) — Proyecto 3er parcial

Base: la app `flutter_login_logout` (login, sesión segura y catálogo contra el backend de Render).
Este documento es el contexto que se pega en las sesiones de IA de T8, T9 y T10. No hace falta pegar el código de la app completa.

---

## 1. Qué existe hoy

```
lib/
├── main.dart                     # MaterialApp (Material 3, seed indigo) → LoginScreen
├── config.dart                   # const apiBaseUrl (URL de Render)
├── models/product.dart           # fromJson del producto
├── services/
│   ├── auth_service.dart         # login, getUserIdByUsername, mapRole
│   ├── session_service.dart      # flutter_secure_storage: token, rol, id
│   └── product_service.dart      # CRUD + helpers _send / _decode
├── screens/                      # login, home (catálogo), detalle, formulario
└── widgets/product_image.dart    # Image.network con spinner y respaldo
```

Dependencias (según el README; el `pubspec.yaml` no venía en el zip, **confirma versiones**):
`http`, `flutter_secure_storage`, `connectivity_plus`.

## 2. Qué se reutiliza tal cual

| Pieza | Por qué sirve |
|---|---|
| `SessionService` | Guarda y borra token/rol/id en almacenamiento seguro. Solo cambian las llaves |
| Patrón `_send` + `_decode` de `ProductService` | Timeout de 60 s (aguanta el arranque en frío de Render), decodifica UTF-8 con `bodyBytes` y extrae `detail` de los errores de FastAPI |
| Clases de excepción (`AuthException`, `NetworkException`, `ProductException`) | Se unifican en una sola jerarquía en `core/app_exceptions.dart` |
| Revisión de conectividad en login | Se conserva |
| `pushAndRemoveUntil` + `PopScope(canPop: false)` | Bloquea volver a pantallas protegidas tras cerrar sesión |
| Validadores `_required`, `_validatePrice`, `_validateUrl` | Plantilla para los validadores nuevos |
| `ProductImage` | Se reutiliza si se muestran miniaturas de videos |
| `config.dart` | Un solo lugar para la URL del backend |

## 3. Qué hay que cambiar (lo exige la rúbrica)

| Hoy | Problema | Cambio |
|---|---|---|
| La lógica vive dentro de los `State` con `setState` | **No es MVVM.** La vista, el estado y la validación están mezclados | Crear `viewmodels/` con `ChangeNotifier` y `Provider`. La vista solo dibuja y llama al ViewModel |
| `AuthService.mapRole(userId)`: ids 1 y 2 son admin | El rol lo decide la app. La rúbrica pide que lo decida el servidor | Quitar `mapRole`. El login devuelve `{token, id, username, role}` y la app solo lo usa para elegir la pantalla inicial |
| `getUserIdByUsername` consulta `GET /users` | Esa ruta sería pública y trae a todos los usuarios | Eliminar. El id y el rol vienen en la respuesta del login |
| Login solo revisa que los campos no estén vacíos | Debe indicar **qué corregir** e impedir el envío | Validadores con mensajes específicos (sección 6) |
| No se maneja el token vencido | Si expira, cada llamada falla sin explicación | `ApiClient`: ante 401 borra la sesión y manda a login con aviso |
| Un cliente promovido sigue viendo el menú de cliente | La rúbrica pide que obtenga permisos **al volver a iniciar sesión** | Tras promover, el nuevo admin cierra sesión y entra de nuevo. Mostrar mensaje claro ante 403 |
| Llave `session_cart` sin uso | Resto del catálogo | Borrarla |

Regla de seguridad: **el rol en la app solo decide qué pantallas mostrar.** El control real está en el backend, que verifica cada petición.

Formato de errores de la API: `{"detail": "mensaje"}` y, en 422, `errors: [{field, message}]`. El `ApiClient` lanza una excepción con ese `detail`, y el ViewModel decide qué mostrar y en qué campo.

## 4. Estructura objetivo (MVVM)

```
lib/
├── main.dart                     # MultiProvider + AuthGate (sesión → home según rol)
├── config.dart
├── core/
│   ├── api_client.dart           # base URL, header Bearer, timeout 60 s, UTF-8, errores, 401 → cerrar sesión
│   ├── app_exceptions.dart
│   └── validators.dart           # validadores puros reutilizables
├── models/                       # MODELO (datos)
│   ├── user.dart  niche.dart  video.dart  prediction.dart  stats.dart
├── services/                     # MODELO (acceso a datos, usan ApiClient)
│   ├── auth_service.dart  session_service.dart  channel_service.dart
│   ├── prediction_service.dart  admin_service.dart
├── viewmodels/                   # VISTAMODELO (estado + validaciones de entrada)
│   ├── auth_viewmodel.dart  channel_viewmodel.dart
│   ├── predict_viewmodel.dart  admin_viewmodel.dart
├── views/                        # VISTA (solo UI)
│   ├── login_view.dart  register_view.dart
│   ├── client/  (home, canal, nicho, predicción)
│   └── admin/   (panel, usuarios)
└── widgets/
```

Reparto de responsabilidades (lo pide el PDF):
- **Modelo:** representa los datos y gestiona su acceso (`models/` y `services/`).
- **Vista:** presenta la interfaz. No llama a la API ni valida.
- **VistaModelo:** coordina las acciones de la pantalla, guarda su estado (`loading`, `error`, datos) y aplica las validaciones de entrada. La `Form` de la vista llama a `vm.validateX` desde su `validator`.

## 5. Pantallas, ViewModels y endpoints (alineado con `C2_api.md`; si C2 cambia, se actualiza esta tabla)

| Pantalla | ViewModel | Endpoints que consume |
|---|---|---|
| Registro | `AuthViewModel` | `POST /auth/register` (el cuerpo **no** lleva `role`) |
| Login | `AuthViewModel` | `POST /auth/login` → `{token, id, username, role}` |
| Inicio del cliente (mi canal) | `ChannelViewModel` | `POST /channels` `{handle}`, `GET /channels/mine` |
| Elegir nicho | `ChannelViewModel` | `GET /niches`, `PUT /channels/mine/niche` |
| Mi canal vs. el nicho y temas | `ChannelViewModel` | `GET /niches/{id}/overview`, `GET /niches/{id}/topics` |
| Probar una idea de título | `PredictViewModel` | `POST /predict` `{niche_id, title, duration_s, publish_hour, publish_weekday?}`, `GET /predictions/mine`, `GET /predictions/{id}` |
| Panel admin (tabla + gráfica) | `AdminViewModel` | `GET /admin/stats` |
| Usuarios (promover) | `AdminViewModel` | `GET /admin/users`, `POST /admin/users/{id}/promote` |
| Modelo activo y métricas (admin) | `AdminViewModel` | `GET /admin/model` |

Si el canal registrado trae `language` distinto de `es`, la app muestra un aviso: el modelo está entrenado con títulos en español.

## 6. Validaciones en la app (antes de enviar)

Cada una indica qué corregir y bloquea el envío. El backend las repite (la rúbrica prueba con Postman).

| Campo | Regla | Mensaje de ejemplo |
|---|---|---|
| Usuario | 3 a 30 caracteres, letras, números, punto o guion bajo | "El usuario debe tener entre 3 y 30 caracteres (letras, números, . o _)" |
| Nombre (registro) | 1 a 80 caracteres | "Escribe tu nombre (máximo 80 caracteres)" |
| Contraseña (registro) | mínimo 8 caracteres, con letra y número | "Usa al menos 8 caracteres con letras y números" |
| @handle | opcional `@`, 3 a 30 caracteres `[A-Za-z0-9._-]` | "Escribe tu @handle, por ejemplo @micanal" |
| Título de la idea | 3 a 100 caracteres | "El título debe tener entre 3 y 100 caracteres" |
| Duración | número entero, de 1 a 7200 segundos | "La duración va de 1 a 7200 segundos" |
| Hora de publicación | entero, de 0 a 23 | "La hora debe estar entre 0 y 23" |
| Día de publicación (opcional) | entero, de 0 (lunes) a 6 (domingo) | "El día debe ir de 0 a 6" |
| Nicho | obligatorio | "Elige un nicho" |

## 7. Detalles para el APK

- **Permiso de internet:** en `android/app/src/main/AndroidManifest.xml` agrega `<uses-permission android:name="android.permission.INTERNET"/>`. El proyecto nuevo lo trae solo en los manifiestos de depuración, y sin él la APK de release no abre conexiones.
- Revisa el `minSdk` que exige `flutter_secure_storage` en la versión que quede en el `pubspec.yaml`.
- Compilar: `flutter build apk --release`. Instala el APK en un teléfono real **antes** del último día.
- Dependencias a agregar: `provider` y `fl_chart` (gráfica del panel).
- Primera petición lenta (Render dormido): mostrar un texto del tipo "Despertando el servidor, puede tardar hasta un minuto" mientras `loading` es verdadero, y no marcar error antes de los 60 s.
- Para no escribir la URL a mano en cada cambio: `--dart-define=API_URL=...` y leerla con `String.fromEnvironment` en `config.dart` (opcional).

## 8. Contexto mínimo por tarea (qué pegar en cada sesión de IA)

| Tarea | Pega esto |
|---|---|
| T8 Frontend base | Secciones 2, 3, 4 y 7 + el bloque de auth del contrato C2 + el código de `session_service.dart` y de `login_screen.dart` |
| T9 Frontend cliente | Secciones 4, 5 y 6 + C2 (canales, nichos, predicción) + `core/api_client.dart` ya terminado |
| T10 Frontend admin | Secciones 4 y 5 + C2 (admin) + `core/api_client.dart` + `fl_chart` en el `pubspec.yaml` |

Regla común: la IA **no** cambia el contrato de la API. Si algo no alcanza, lo avisa antes de inventar.

## 9. Pruebas de la rúbrica que toca el frontend

1. Login con ambas cuentas y con contraseña incorrecta: cada cuenta ve las funciones de su rol; el error se muestra.
2. Dato inválido en un formulario: se indica el error y no se envía.
3. Promover a un cliente: el cambio persiste y, al volver a iniciar sesión, la cuenta ve el panel de administrador.
4. Panel: la tabla y la gráfica muestran lo que devuelve `GET /admin/stats`.
5. Flujo de ML: el cliente captura su canal, pide una predicción y ve el resultado.
6. Las transacciones desde la app funcionan en el APK instalado, no solo en el emulador.
