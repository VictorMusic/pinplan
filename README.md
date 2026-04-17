# PinPlan · Zaragoza

Agenda automática de conciertos en Zaragoza. Muestra hoy por defecto, navega por días, abre ficha con Google Maps y compartir.

## Arquitectura

```
GitHub Actions (2x/día)       GitHub Pages
  scraper/scraper.py  →  web/eventos.json  →  web/index.html
```

## Fuentes de datos

| Fuente | URL |
|--------|-----|
| Ayuntamiento Zaragoza | zaragoza.es (API open data) |
| ZGZ Conciertos | zgzconciertos.com |
| Aragón en Vivo | aragonenvivo.com |
| Sala Oasis | salaoasis.com |
| Sala López | salalopez.com |
| Rock & Blues Café | rockandbluescafe.com |
| Enjoy Zaragoza | enjoyzaragoza.es |
| Songkick | songkick.com |
| Conciertos.club | conciertos.club |

## Puesta en marcha

1. Crear repo en GitHub y subir este código
2. Settings → Pages → Source: carpeta `web/`, rama `main`
3. Settings → Actions → Workflow permissions → "Read and write"
4. Actions → "Actualizar eventos" → Run workflow (primera carga)

URL: `https://TU-USUARIO.github.io/REPO/`

## Desarrollo local

```bash
pip install requests beautifulsoup4 lxml
cd scraper && python scraper.py
cd ../web && python -m http.server 8080
# Abrir http://localhost:8080
```
