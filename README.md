# WebUserFlowAgent

WebUserFlowAgent explora interfaces web con un navegador real, construye un
mapa estructurado de sus elementos y registra transiciones entre estados. El
objetivo es utilizar ese mapa para generar, ejecutar y reparar flujos de
automatización web.

El proyecto se encuentra en desarrollo incremental. Actualmente dispone de un
Explorer Agent funcional; la generación de scripts y su verificación serán los
siguientes componentes.

## Estado actual

El explorador puede:

- abrir páginas con Chromium mediante Playwright;
- detectar enlaces, botones, campos y otros controles visibles;
- obtener nombres accesibles desde labels y atributos ARIA;
- clasificar elementos por región e importancia;
- generar selectores alternativos con puntuación y marca de unicidad;
- reparar errores comunes de codificación UTF-8;
- reconocer y resolver consentimientos de cookies comunes;
- capturar los estados anterior y posterior a una interacción;
- registrar y validar transiciones entre estados;
- producir manifiestos JSON y capturas de pantalla.

## Arquitectura prevista

```text
Aplicación web
    ↓
Explorer Agent
    ↓
Manifiesto de páginas, elementos y transiciones
    ↓
Flow Agent
    ↓
Generator Agent (Playwright/Python inicialmente)
    ↓
Verifier Agent
```

- **Explorer Agent:** descubre estados, elementos y posibles acciones.
- **Flow Agent:** convierte una intención en pasos estructurados.
- **Generator Agent:** genera scripts automatizados.
- **Verifier Agent:** ejecuta, comprueba y eventualmente repara los scripts.

## Requisitos

- Python 3.11 o posterior
- Chromium de Playwright

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,explorer]"
python -m playwright install chromium
```

## Uso

Crear un manifiesto vacío:

```powershell
webuserflow init --name demo --base-url https://example.com
```

Explorar una página en modo headless:

```powershell
webuserflow explore https://example.com --name demo
```

Mostrar el navegador durante la exploración:

```powershell
webuserflow explore https://example.com --name demo --headed
```

Ejecutar y registrar un flujo de búsqueda:

```powershell
webuserflow explore https://www.mercadolibre.cl/ `
  --name mercadolibre `
  --search "notebook" `
  --headed
```

Guardar capturas de los estados detectados:

```powershell
webuserflow explore https://example.com `
  --name demo `
  --output data/manifests/demo.json `
  --screenshot reports/demo.png
```

El explorador intenta resolver automáticamente los consentimientos de cookies
conocidos. Para conservar el estado sin intervenir:

```powershell
webuserflow explore https://example.com --name demo --keep-cookies
```

Validar un manifiesto:

```powershell
webuserflow validate data/manifests/demo.json
```

Ejecutar las pruebas:

```powershell
python -m pytest
```

## Manifiesto

El manifiesto es el contrato entre los agentes. Contiene:

- páginas o estados capturados;
- elementos interactivos por estado;
- región e importancia de cada elemento;
- selectores candidatos y su unicidad;
- transiciones observadas;
- flujos definidos por el usuario;
- metadatos de exploración.

Ejemplo de transición:

```json
{
  "from_page": "home_cookie_consent",
  "to_page": "home_ready",
  "action": "click",
  "target": "button_aceptar_cookies"
}
```

Un generador no debería utilizar un selector marcado como `unique: false` sin
combinarlo con contexto adicional.

## Estructura principal

```text
src/webuserflowagent/
  cli.py                 interfaz de línea de comandos
  manifest.py            lectura, escritura y validación
  models.py              contrato de datos
  explorer/page.py       exploración con Playwright
tests/                   pruebas unitarias
data/manifests/          manifiestos generados (ignorados por Git)
reports/                 capturas y reportes (ignorados por Git)
```

El antiguo prototipo de scraping permanece temporalmente en `src/collectors`
como referencia y no forma parte del núcleo nuevo.

## Próximos hitos

1. Construir un grafo navegable con múltiples acciones y estados.
2. Permitir reanudación manual segura ante desafíos como CAPTCHA o MFA.
3. Incorporar el Flow Agent.
4. Generar scripts Playwright/Python.
5. Ejecutar, verificar y reparar automatizaciones.

## Seguridad

Los manifiestos no deben almacenar contraseñas, tokens, cookies de sesión ni
datos personales. Los secretos de ejecución deben suministrarse externamente y
los sitios explorados deben estar dentro del alcance autorizado por el usuario.
