import requests
from bs4 import BeautifulSoup
import json, re, time, os, pathlib
from datetime import datetime, date, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Load salas for name normalization
_SALAS = []
_salas_file = pathlib.Path(__file__).parent.parent / 'salas.json'
if _salas_file.exists():
    _SALAS = json.loads(_salas_file.read_text())['salas']

def normalize_sala(sala_raw):
    if not sala_raw: return sala_raw
    s = sala_raw.lower().strip()
    for sala in _SALAS:
        for kw in sala['keywords']:
            if kw.lower() in s:
                return sala['nombre']
    return sala_raw

MONTHS = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12,
    "ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,
    "jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12,
    "jan":1,"apr":4,"aug":8,"dec":12
}

def normalize(t):
    return " ".join((t or "").split()).strip()

def parse_date(text):
    if not text: return None
    t = text.lower().strip()
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
    if m: return m.group(0)
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', t)
    if m: return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r'(\d{1,2})\s+(?:de\s+)?(\w+)\s+(?:de\s+)?(\d{4})', t)
    if m:
        mon = MONTHS.get(m.group(2)[:3])
        if mon: return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    m = re.search(r'(\d{1,2})\s+(?:de\s+)?(\w+)', t)
    if m:
        mon = MONTHS.get(m.group(2)[:3])
        if mon:
            y = date.today().year
            d = int(m.group(1))
            candidate = f"{y}-{mon:02d}-{d:02d}"
            if candidate < date.today().isoformat():
                candidate = f"{y+1}-{mon:02d}-{d:02d}"
            return candidate
    return None

def parse_time(text):
    if not text: return ""
    m = re.search(r'(\d{1,2})[:\.](\d{2})', text)
    if m: return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""

def get(url, timeout=15, retries=2):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == retries - 1:
                print(f"  WARN {url[:60]}: {e}")
            time.sleep(1)
    return None

def make_event(titulo, fecha, hora, sala, url, imagen="", descripcion=""):
    return {
        "titulo": normalize(titulo),
        "fecha": fecha or "",
        "hora": hora or "",
        "sala": normalize_sala(normalize(sala)),
        "url": url or "",
        "imagen": imagen or "",
        "descripcion": normalize(descripcion),
    }

def extract_tribe(soup, sala_default, base_url):
    events = []
    articles = []
    for sel in ["article.type-tribe_events","article.tribe_events_cat",
                ".tribe-events-calendar-list__event",".tribe-events-loop article",
                "article[class*='tribe']",".events-archive article"]:
        items = soup.select(sel)
        if items: articles = items; break
    for art in articles:
        title_el = art.select_one("h2 a, h3 a, .entry-title a, .tribe-events-list-event-title a")
        # Try multiple date selectors aggressively
        date_el = art.select_one(
            "time[datetime], abbr[title], .tribe-event-date-start, "
            "[class*='tribe-event-date'], [class*='event-date'], "
            "[class*='date-start'], .entry-date, .published"
        )
        loc_el = art.select_one(".tribe-venue, [class*='tribe-venue'], [class*='venue']")
        img_el = art.select_one("img")
        link_el = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        
        # Get date from multiple sources
        fecha_raw = ""
        if date_el:
            fecha_raw = (date_el.get("datetime","") or 
                        date_el.get("title","") or 
                        date_el.get("content","") or 
                        date_el.get_text())
        
        # Also check link URL for date pattern (many WP sites have /2025/05/15/ in URL)
        if not parse_date(fecha_raw) and link_el:
            href_date = link_el.get("href","")
            m = re.search(r"/(202[0-9])/(\d{2})/(\d{2})/", href_date)
            if m:
                fecha_raw = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        
        hora_el = art.select_one("[class*='time'], .tribe-events-schedule, [class*='hora']")
        hora_raw = hora_el.get_text() if hora_el else fecha_raw
        sala = normalize(loc_el.get_text()) if loc_el else sala_default
        href = link_el["href"] if link_el else base_url
        if href and not href.startswith("http"): href = base_url.rstrip("/") + "/" + href.lstrip("/")
        img = (img_el.get("src","") or img_el.get("data-src","")) if img_el else ""
        events.append(make_event(title, parse_date(fecha_raw) or "", parse_time(hora_raw), sala or sala_default, href, img))
    return events


def scrape_generic(url, sala_name, base_url):
    r = get(url)
    if not r: return []
    soup = BeautifulSoup(r.text, "html.parser")
    evs = extract_tribe(soup, sala_name, base_url)
    if not evs:
        for art in soup.select("article, .event, [class*='event'], [class*='concierto']"):
            title_el = art.select_one("h2 a, h3 a, h4 a, .entry-title a, a")
            date_el = art.select_one(
                "time, [class*='date'], [class*='fecha'], "
                "abbr[title], [itemprop='startDate'], [class*='cuando']"
            )
            img_el = art.select_one("img")
            link_el = art.select_one("a[href]")
            title = normalize(title_el.get_text()) if title_el else ""
            if not title or len(title) < 3: continue
            fecha_raw = ""
            if date_el:
                fecha_raw = (date_el.get("datetime","") or date_el.get("title","") or
                            date_el.get("content","") or date_el.get_text())
            # Try URL date pattern
            if not parse_date(fecha_raw) and link_el:
                m = re.search(r"/(202[0-9])/(\d{2})/(\d{2})/", link_el.get("href",""))
                if m: fecha_raw = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            href = link_el["href"] if link_el else base_url
            if href and not href.startswith("http"): href = base_url.rstrip("/") + "/" + href.lstrip("/")
            evs.append(make_event(title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
                sala_name, href, img_el.get("src","") if img_el else ""))
    return evs


def scrape_zgzconciertos():
    evs = scrape_generic("https://zgzconciertos.com/agenda/lista/", "Zaragoza", "https://zgzconciertos.com")
    print(f"  zgzconciertos: {len(evs)}"); return evs

def scrape_aragonenvivo():
    """Aragón en Vivo - usando API REST de The Events Calendar."""
    import json as _json
    evs = []
    api_url = "https://aragonenvivo.com/wp-json/tribe/events/v1/events"
    evs_api = []
    for page in range(1, 4):
        r = get(api_url + f"?per_page=50&status=publish&page={page}&start_date=" + __import__('datetime').date.today().isoformat())
        if not r or len(r.text) < 100: break
        try:
            data = _json.loads(r.text)
            batch = data.get("events", [])
            if not batch: break
            evs_api.extend(batch)
            if len(batch) < 50: break
        except: break
    if evs_api:
        for ev in evs_api:
            title = ev.get("title", "").strip()
            if not title or len(title) < 3: continue
            start = ev.get("start_date", "")
            fecha = parse_date(start) or ""
            hora = parse_time(start) or ""
            venue = ev.get("venue", {})
            sala = venue.get("venue", "") if isinstance(venue, dict) else ""
            url = ev.get("url", "")
            img_data = ev.get("image", {})
            img = img_data.get("url", "") if isinstance(img_data, dict) else ""
            evs.append(make_event(title, fecha, hora, sala or "Zaragoza", url, img))
        print(f"  aragonenvivo (API): {len(evs)}")
        return evs
    for url in ["https://aragonenvivo.com/eventos/", "https://aragonenvivo.com/agenda/"]:
        batch = scrape_generic(url, "Zaragoza", "https://aragonenvivo.com")
        if batch:
            evs = batch
            break
    print(f"  aragonenvivo: {len(evs)}")
    return evs

def scrape_enjoyzaragoza():
    evs = scrape_generic("https://www.enjoyzaragoza.es/conciertos-zaragoza/", "Zaragoza", "https://www.enjoyzaragoza.es")
    print(f"  enjoyzaragoza: {len(evs)}"); return evs

def scrape_sala_lopez():
    evs = []
    for url in ["https://salalopez.com/eventos/"]:
        evs = scrape_generic(url, "Sala López", "https://salalopez.com")
        if evs: break
    print(f"  sala lopez: {len(evs)}"); return evs

def scrape_sala_oasis():
    evs = []
    for url in ["https://www.salaoasis.com/agenda-oasis/",
                "https://www.salaoasis.com/agenda/",
                "https://www.salaoasis.com/"]:
        evs = scrape_generic(url, "Sala Oasis", "https://www.salaoasis.com")
        if evs: break
    print(f"  sala oasis: {len(evs)}"); return evs

def scrape_creedence():
    evs = []
    for url in ["https://creedencesound.com/sala-creedence-conciertos-y-sesiones", "https://creedencesound.com/"]:
        evs = scrape_generic(url, "Sala Creedence", "https://creedencesound.com")
        if evs: break
    print(f"  creedence: {len(evs)}"); return evs

def scrape_lata_bombillas():
    evs = []
    for url in ["https://lalatadebombillas.es/eventos/", "https://lalatadebombillas.es/conciertos/",
                "https://lalatadebombillas.es/programacion/", "https://lalatadebombillas.es/"]:
        evs = scrape_generic(url, "La Lata de Bombillas", "https://lalatadebombillas.es")
        if evs: break
    print(f"  lata bombillas: {len(evs)}"); return evs

def scrape_rock_blues():
    evs = []
    for url in ["https://www.rockandbluescafe.com/", "https://www.rockandbluescafe.com/agenda/", "https://www.rockandbluescafe.com/eventos/"]:
        evs = scrape_generic(url, "Rock & Blues Café", "https://www.rockandbluescafe.com")
        if evs: break
    print(f"  rock&blues: {len(evs)}"); return evs

def scrape_teatro_esquinas():
    evs = []
    for url in ["https://www.teatrodelasesquinas.com/es/programacion-de-teatro-y-conciertos.html?ordre=data_propera_funcio&daterange=&filtre_espais%5B%5D=all&cf%5B9%5D%5B%5D=17&filtre_historic=0",
                "https://www.teatrodelasesquinas.com/es/programacion-de-teatro-y-conciertos.html"]:
        evs = scrape_generic(url, "Teatro de las Esquinas", "https://www.teatrodelasesquinas.com")
        if evs: break
    print(f"  teatro esquinas: {len(evs)}"); return evs

def scrape_auditorio():
    evs = []
    for url in ["https://auditoriozaragoza.com/agenda/conciertos/", "https://auditoriozaragoza.com/"]:
        evs = scrape_generic(url, "Auditorio de Zaragoza", "https://auditoriozaragoza.com")
        if evs: break
    print(f"  auditorio: {len(evs)}"); return evs

def scrape_aragonmusical():
    evs = scrape_generic("https://www.aragonmusical.com/conciertos-en-zaragoza/", "Zaragoza", "https://www.aragonmusical.com")
    evs = [e for e in evs if "zaragoza" in (e["sala"] or "").lower() or e["sala"] == "Zaragoza"]
    print(f"  aragonmusical: {len(evs)}"); return evs

def scrape_taquilla():
    evs = scrape_generic("https://www.taquilla.com/conciertos/zaragoza", "Zaragoza", "https://www.taquilla.com")
    print(f"  taquilla: {len(evs)}"); return evs

def scrape_songkick():
    events = []
    r = get("https://www.songkick.com/es/metro-areas/28809-spain-zaragoza")
    if not r: print("  songkick: 0"); return events
    soup = BeautifulSoup(r.text, "html.parser")
    for li in soup.select("li.event, .event-listings li, .concerts-list li"):
        title_el = li.select_one(".summary strong, h3, strong")
        date_el = li.select_one("time, .date")
        loc_el = li.select_one(".venue-name, .location")
        link_el = li.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"): href = "https://www.songkick.com" + href
        events.append(make_event(title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            normalize(loc_el.get_text()) if loc_el else "Zaragoza", href))
    print(f"  songkick: {len(events)}"); return events

def scrape_green_heart():
    evs = []
    for url in ["https://elcorazonverdebar.com/agenda/", "https://elcorazonverdebar.com/"]:
        evs = scrape_generic(url, "El Corazón Verde", "https://elcorazonverdebar.com")
        if evs: break
    print(f"  green heart: {len(evs)}"); return evs

def scrape_setlistfm(api_key=None):
    if not api_key:
        api_key = os.environ.get('SETLISTFM_API_KEY','')
    if not api_key:
        print('  setlist.fm: no API key'); return []
    """Setlist.fm — upcoming concerts in Zaragoza."""
    events = []
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "Accept-Language": "es"
    }
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=30)).isoformat()

    try:
        # Search upcoming events in Zaragoza
        url = "https://api.setlist.fm/rest/1.0/search/setlists"
        params = {
            "cityName": "Zaragoza",
            "countryCode": "ES",
            "p": 1
        }
        r = requests.get(url, headers=headers, params=params, timeout=12)
        if r.status_code != 200:
            print(f"  setlist.fm: HTTP {r.status_code}")
            return events
        data = r.json()
        setlists = data.get("setlist", [])
        for sl in setlists:
            # eventDate format: dd-MM-yyyy
            fecha_raw = sl.get("eventDate", "")
            if fecha_raw:
                parts = fecha_raw.split("-")
                if len(parts) == 3:
                    fecha = f"{parts[2]}-{parts[1]}-{parts[0]}"
                else:
                    continue
            else:
                continue
            # Only future events
            if fecha < today or fecha > cutoff:
                continue
            artist = sl.get("artist", {}).get("name", "")
            if not artist:
                continue
            venue = sl.get("venue", {})
            sala = venue.get("name", "Zaragoza")
            ciudad = venue.get("city", {}).get("name", "")
            if ciudad.lower() != "zaragoza":
                continue
            events.append(make_event(
                artist,
                fecha,
                "",  # setlist.fm doesn't provide time
                sala,
                sl.get("url", ""),
                "",
                ""
            ))
    except Exception as e:
        print(f"  setlist.fm error: {e}")

    print(f"  setlist.fm: {len(events)}")
    return events

def scrape_casa_loco():
    evs = []
    for url in ["https://www.locozaragozadiscoteca.com/",
                "https://www.arenarock.es/sala/la-casa-del-loco/",
                "https://lacasadelloco.es/"]:
        evs = scrape_generic(url, "La Casa del Loco", "https://www.locozaragozadiscoteca.com")
        if evs: break
    print(f"  casa del loco: {len(evs)}"); return evs

def scrape_arenarock():
    """Arenarock.es - aggregator for Zaragoza venues."""
    evs = scrape_generic("https://www.arenarock.es/eventos/", "Zaragoza", "https://www.arenarock.es")
    # Filter only Zaragoza events
    evs = [e for e in evs if not e["sala"] or "zaragoza" in e["sala"].lower()
           or e["sala"] in ["Zaragoza", "La Casa del Loco", "Sala Z", "Sala Oasis",
                             "Rock & Blues Café", "Sala Creedence"]]
    print(f"  arenarock: {len(evs)}"); return evs


def scrape_shazam():
    """Shazam events for Zaragoza."""
    events = []
    try:
        url = "https://www.shazam.com/es-es/events/zaragoza-espa%C3%B1a"
        r = get(url)
        if not r: print("  shazam: 0"); return events
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        # Shazam uses JSON-LD for events
        import json as _json
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") not in ("Event", "MusicEvent"): continue
                    title = item.get("name","")
                    fecha_raw = item.get("startDate","")
                    location = item.get("location",{})
                    sala = location.get("name","Zaragoza") if isinstance(location, dict) else "Zaragoza"
                    img = ""
                    if isinstance(item.get("image"), str): img = item["image"]
                    elif isinstance(item.get("image"), list) and item["image"]: img = item["image"][0]
                    href = item.get("url","")
                    if title and fecha_raw:
                        events.append(make_event(title, parse_date(fecha_raw) or "", parse_time(fecha_raw), sala, href, img))
            except: pass
        # Also try to find events in page data
        if not events:
            for el in soup.select("[data-testid*='event'], .event-card, [class*='EventCard']"):
                title_el = el.select_one("h2, h3, [class*='title'], [class*='name']")
                date_el = el.select_one("time, [class*='date'], [class*='Date']")
                title = normalize(title_el.get_text()) if title_el else ""
                if not title or len(title) < 2: continue
                fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
                events.append(make_event(title, parse_date(fecha_raw) or "", "", "Zaragoza", url))
    except Exception as e:
        print(f"  shazam error: {e}")
    print(f"  shazam: {len(events)}")
    return events

def scrape_auditorio_detail():
    """Auditorio Zaragoza - visit each event page to get the date."""
    events = []
    try:
        r = get("https://auditoriozaragoza.com/agenda/conciertos/")
        if not r: print("  auditorio_detail: 0"); return events
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        # Get all event links
        links = []
        for a in soup.select("a[href*='/programacion/'], a[href*='/evento/'], a[href*='/concierto/']"):
            href = a.get("href","")
            if href and href not in links:
                links.append(href)
        links = links[:30]  # Max 30 to avoid timeout
        for href in links:
            if not href.startswith("http"):
                href = "https://auditoriozaragoza.com" + href
            ev_r = get(href, timeout=8)
            if not ev_r: continue
            ev_soup = BeautifulSoup(ev_r.text, "html.parser")
            title_el = ev_soup.select_one("h1, .entry-title, [class*='title']")
            title = normalize(title_el.get_text()) if title_el else ""
            if not title or len(title) < 3: continue
            # Find date
            fecha_raw = ""
            date_el = ev_soup.select_one("time[datetime], [itemprop='startDate'], [class*='fecha'], [class*='date']")
            if date_el:
                fecha_raw = date_el.get("datetime","") or date_el.get("content","") or date_el.get_text()
            # Try meta tags
            if not parse_date(fecha_raw):
                meta = ev_soup.find("meta", {"itemprop": "startDate"}) or ev_soup.find("meta", {"property": "event:start_time"})
                if meta: fecha_raw = meta.get("content","")
            img_el = ev_soup.select_one("meta[property='og:image']")
            img = img_el.get("content","") if img_el else ""
            events.append(make_event(title, parse_date(fecha_raw) or "", "", "Auditorio de Zaragoza", href, img))
            time.sleep(0.5)
    except Exception as e:
        print(f"  auditorio_detail error: {e}")
    print(f"  auditorio_detail: {len(events)}")
    return events


def scrape_auditorio_rss():
    """Auditorio Zaragoza RSS feed - fechas fiables."""
    import xml.etree.ElementTree as ET
    events = []
    urls = [
        "https://auditoriozaragoza.com/agenda/conciertos/feed/",
        "https://auditoriozaragoza.com/feed/",
    ]
    for url in urls:
        r = get(url)
        if not r: continue
        try:
            root = ET.fromstring(r.content)
            ns = {'content': 'http://purl.org/rss/1.0/modules/content/',
                  'dc': 'http://purl.org/dc/elements/1.1/'}
            for item in root.findall('.//item'):
                title = (item.findtext('title') or '').strip()
                if not title or len(title) < 3: continue
                link = (item.findtext('link') or '').strip()
                # Try multiple date fields
                fecha_raw = (item.findtext('pubDate') or
                            item.findtext('dc:date', namespaces=ns) or
                            item.findtext('{http://purl.org/dc/elements/1.1/}date') or '')
                # pubDate format: "Mon, 16 May 2026 10:00:00 +0000"
                fecha = parse_date(fecha_raw)
                if not fecha: continue
                img_el = None
                enclosure = item.find('enclosure')
                img = enclosure.get('url','') if enclosure is not None else ''
                desc = (item.findtext('description') or '').strip()
                from bs4 import BeautifulSoup as BS
                if desc:
                    img_soup = BS(desc, 'html.parser')
                    img_tag = img_soup.find('img')
                    if img_tag and not img:
                        img = img_tag.get('src','')
                events.append(make_event(title, fecha, '', 'Auditorio de Zaragoza', link, img))
            if events: break
        except Exception as e:
            print(f"  auditorio_rss error: {e}")
            continue
    print(f"  auditorio_rss: {len(events)}")
    return events

def scrape_ibercaja_auditorio():
    """Entradas Ibercaja - Auditorio de Zaragoza."""
    evs = scrape_generic(
        "https://entradas.ibercaja.es/eventos/zaragoza/auditorio-de-zaragoza-princesa-leonor/",
        "Auditorio de Zaragoza",
        "https://entradas.ibercaja.es"
    )
    print(f"  ibercaja_auditorio: {len(evs)}")
    return evs

def scrape_taquilla_zgz():
    """Taquilla.com - conciertos en Zaragoza."""
    evs = []
    for url in [
        "https://www.taquilla.com/conciertos?t10city=Zaragoza",
        "https://www.taquilla.com/zaragoza/auditorio-de-zaragoza",
    ]:
        batch = scrape_generic(url, "Zaragoza", "https://www.taquilla.com")
        evs.extend(batch)
    # deduplicate within this source
    seen = set()
    unique = []
    for e in evs:
        k = (e["titulo"].lower()[:40], e["fecha"])
        if k not in seen:
            seen.add(k)
            unique.append(e)
    print(f"  taquilla_zgz: {len(unique)}")
    return unique


def normalize_title(t):
    """Normalize title for dedup comparison."""
    t = t.lower().strip()
    # Remove common suffixes like "+ support", "en directo", etc.
    t = re.sub(r'\s*[+&]\s*.{1,30}$', '', t)
    t = re.sub(r'\s+(en\s+directo|directo|live|tour|\d{4})\s*$', '', t)
    # Remove all non-alphanumeric
    t = re.sub(r'[^a-záéíóúüñ0-9]', '', t)
    return t[:30]

GARBAGE_TITLES = {
    "saltar al contenido", "lista", "ver todos", "entradas", "comprar",
    "más info", "agenda", "eventos", "conciertos", "programación", "inicio",
    "home", "menu", "menú", "siguiente", "anterior", "cerrar",
    "leer más", "read more", "ver más", "ver todo", "all events",
    "día", "mes", "semana", "hoy", "mañana", "week", "month", "day",
    "próximos eventos", "próximos conciertos", "próximas actuaciones",
}

GARBAGE_URL_PATTERNS = ["/eventos/hoy", "/eventos/mes", "/eventos/semana", 
                         "/agenda/hoy", "/agenda/mes", "/#content"]

def is_garbage(titulo, url=""):
    t = titulo.lower().strip()
    if t in GARBAGE_TITLES: return True
    if len(t) < 3: return True
    if t.startswith("saltar") or t.startswith("skip"): return True
    # Single common word
    if t in {"día", "mes", "hoy", "semana", "año", "lista", "todo"}: return True
    # Garbage URLs
    for pat in GARBAGE_URL_PATTERNS:
        if pat in url: return True
    return False



def deduplicate(events):
    events = [e for e in events if e["fecha"]]
    events = [e for e in events if not is_garbage(e["titulo"], e.get("url",""))]
    seen = {}
    for e in events:
        key = (e["titulo"].lower().strip()[:50], e["fecha"])
        if key not in seen:
            seen[key] = e
        else:
            ex = seen[key]
            score_new = bool(e["imagen"]) + bool(e["hora"]) + bool(e["descripcion"]) + (e["sala"] not in ["Zaragoza",""])
            score_ex  = bool(ex["imagen"]) + bool(ex["hora"]) + bool(ex["descripcion"]) + (ex["sala"] not in ["Zaragoza",""])
            if score_new > score_ex: seen[key] = e
    return list(seen.values())

def filter_future(events):
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=180)).isoformat()
    # Filter out past events and events more than 6 months away
    return [e for e in events if e["fecha"] and today <= e["fecha"] <= cutoff]

def sort_events(events):
    return sorted(events, key=lambda e: (e["fecha"] or "9999", e["hora"] or "99:99"))

def main():
    print(f"\nPinPlan scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    all_events = []
    scrapers = [
        ("ZGZ Conciertos",       scrape_zgzconciertos),
        ("Aragón en Vivo",       scrape_aragonenvivo),
        ("Enjoy Zaragoza",       scrape_enjoyzaragoza),
        ("Sala López",           scrape_sala_lopez),
        ("Sala Oasis",           scrape_sala_oasis),
        ("Sala Creedence",       scrape_creedence),
        ("La Lata de Bombillas", scrape_lata_bombillas),
        ("Rock & Blues Café",    scrape_rock_blues),
        ("Teatro Esquinas",      scrape_teatro_esquinas),
        ("Auditorio Zaragoza",   scrape_auditorio),
        ("Auditorio RSS",       scrape_auditorio_rss),
        ("Ibercaja Auditorio",  scrape_ibercaja_auditorio),
        ("Taquilla ZGZ",        scrape_taquilla_zgz),
        ("Aragón Musical",       scrape_aragonmusical),
        ("Taquilla.com",         scrape_taquilla),
        ("Songkick",             scrape_songkick),
        ("Green Heart",          scrape_green_heart),
        ("Setlist.fm",           scrape_setlistfm),
        ("La Casa del Loco",    scrape_casa_loco),
        ("Arenarock",           scrape_arenarock),
    ]
    for name, fn in scrapers:
        print(f"\n[{name}]")
        try:
            evs = fn()
            all_events.extend(evs)
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(1.5)

    print(f"\nBruto: {len(all_events)}")
    con_fecha = [e for e in all_events if e["fecha"]]
    print(f"  Con fecha: {len(con_fecha)} / Sin fecha: {len(all_events)-len(con_fecha)}")
    # Show unique titles before dedup
    titulos_con_fecha = [(e["titulo"][:40], e["fecha"]) for e in con_fecha]
    from collections import Counter
    title_counts = Counter(e["titulo"].lower().strip()[:50] for e in con_fecha)
    print(f"  Titulos unicos con fecha: {len(title_counts)}")
    print(f"  Top repetidos: {title_counts.most_common(5)}")
    deduped = deduplicate(all_events)
    print(f"Tras dedup: {len(deduped)}")
    filtered = filter_future(deduped)
    print(f"Tras filter_future: {len(filtered)}")
    # Show what got filtered out
    deduped_fechas = set(e["fecha"] for e in deduped)
    filtered_fechas = set(e["fecha"] for e in filtered)
    lost = deduped_fechas - filtered_fechas
    if lost: print(f"  Fechas eliminadas: {sorted(lost)}")
    all_events = sort_events(filtered)
    print(f"Limpio: {len(all_events)}")
    if all_events:
        fechas = sorted(set(e["fecha"] for e in all_events))
        print(f"  Fechas: {fechas[0]} → {fechas[-1]}")

    output = {"actualizado": datetime.now().isoformat(), "total": len(all_events), "eventos": all_events}
    out_path = pathlib.Path(__file__).parent.parent / 'eventos.json'
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Guardado en {out_path} ✓")

if __name__ == "__main__":
    main()
