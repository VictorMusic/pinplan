import requests
from bs4 import BeautifulSoup
import json, re, time, os, pathlib
from datetime import datetime, date, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

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
        date_el = art.select_one("time[datetime], .tribe-event-date-start, [class*='tribe-event-date']")
        loc_el = art.select_one(".tribe-venue, [class*='tribe-venue']")
        img_el = art.select_one("img")
        link_el = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        hora_el = art.select_one("[class*='time'], .tribe-events-schedule")
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
            date_el = art.select_one("time, [class*='date'], [class*='fecha']")
            img_el = art.select_one("img")
            link_el = art.select_one("a[href]")
            title = normalize(title_el.get_text()) if title_el else ""
            if not title or len(title) < 3: continue
            fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
            href = link_el["href"] if link_el else base_url
            if href and not href.startswith("http"): href = base_url.rstrip("/") + "/" + href.lstrip("/")
            evs.append(make_event(title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
                sala_name, href, img_el.get("src","") if img_el else ""))
    return evs

def scrape_zgzconciertos():
    evs = scrape_generic("https://zgzconciertos.com/agenda/lista/", "Zaragoza", "https://zgzconciertos.com")
    print(f"  zgzconciertos: {len(evs)}"); return evs

def scrape_aragonenvivo():
    evs = []
    for url in ["https://aragonenvivo.com/eventos/", "https://aragonenvivo.com/agenda/"]:
        evs = scrape_generic(url, "Zaragoza", "https://aragonenvivo.com")
        if evs: break
    print(f"  aragonenvivo: {len(evs)}"); return evs

def scrape_enjoyzaragoza():
    evs = scrape_generic("https://www.enjoyzaragoza.es/conciertos-zaragoza/", "Zaragoza", "https://www.enjoyzaragoza.es")
    print(f"  enjoyzaragoza: {len(evs)}"); return evs

def scrape_sala_lopez():
    evs = []
    for url in ["https://salalopez.com/eventos/", "https://salalopez.com/agenda/", "https://salalopez.com/"]:
        evs = scrape_generic(url, "Sala López", "https://salalopez.com")
        if evs: break
    print(f"  sala lopez: {len(evs)}"); return evs

def scrape_sala_oasis():
    evs = scrape_generic("https://www.salaoasis.com/agenda-oasis/", "Sala Oasis", "https://www.salaoasis.com")
    print(f"  sala oasis: {len(evs)}"); return evs

def scrape_creedence():
    evs = []
    for url in ["https://creedencesound.com/agenda/", "https://creedencesound.com/"]:
        evs = scrape_generic(url, "Sala Creedence", "https://creedencesound.com")
        if evs: break
    print(f"  creedence: {len(evs)}"); return evs

def scrape_lata_bombillas():
    evs = []
    for url in ["https://lalatadebombillas.es/agenda/", "https://lalatadebombillas.es/"]:
        evs = scrape_generic(url, "La Lata de Bombillas", "https://lalatadebombillas.es")
        if evs: break
    print(f"  lata bombillas: {len(evs)}"); return evs

def scrape_rock_blues():
    evs = []
    for url in ["https://www.rockandbluescafe.com/conciertos/", "https://www.rockandbluescafe.com/"]:
        evs = scrape_generic(url, "Rock & Blues Café", "https://www.rockandbluescafe.com")
        if evs: break
    print(f"  rock&blues: {len(evs)}"); return evs

def scrape_teatro_esquinas():
    evs = []
    for url in ["https://www.teatrodelasesquinas.com/es/programacion-de-teatro-y-conciertos.html",
                "https://teatrodelasesquinas.com/programacion/", "https://teatrodelasesquinas.com/"]:
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
    events = []
    headers = {"x-api-key": api_key, "Accept": "application/json", "Accept-Language": "es"}
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=30)).isoformat()
    try:
        r = requests.get("https://api.setlist.fm/rest/1.0/search/setlists",
            headers=headers, params={"cityName":"Zaragoza","countryCode":"ES","p":1}, timeout=12)
        if r.status_code != 200:
            print(f"  setlist.fm: HTTP {r.status_code}"); return events
        for sl in r.json().get("setlist", []):
            fecha_raw = sl.get("eventDate","")
            if fecha_raw:
                parts = fecha_raw.split("-")
                if len(parts) == 3: fecha = f"{parts[2]}-{parts[1]}-{parts[0]}"
                else: continue
            else: continue
            if fecha < today or fecha > cutoff: continue
            artist = sl.get("artist",{}).get("name","")
            if not artist: continue
            venue = sl.get("venue",{})
            if venue.get("city",{}).get("name","").lower() != "zaragoza": continue
            events.append(make_event(artist, fecha, "", venue.get("name","Zaragoza"), sl.get("url",""), "", ""))
    except Exception as e:
        print(f"  setlist.fm error: {e}")
    print(f"  setlist.fm: {len(events)}"); return events

def deduplicate(events):
    seen = {}
    for e in events:
        key = (re.sub(r'\s+','',e["titulo"].lower())[:35], e["fecha"])
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
    cutoff = (date.today() + timedelta(days=30)).isoformat()
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
        ("Aragón Musical",       scrape_aragonmusical),
        ("Taquilla.com",         scrape_taquilla),
        ("Songkick",             scrape_songkick),
        ("Green Heart",          scrape_green_heart),
        ("Setlist.fm",           scrape_setlistfm),
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
    all_events = deduplicate(all_events)
    all_events = filter_future(all_events)
    all_events = sort_events(all_events)
    print(f"Limpio: {len(all_events)}")

    output = {"actualizado": datetime.now().isoformat(), "total": len(all_events), "eventos": all_events}
    out_path = pathlib.Path(__file__).parent.parent / 'eventos.json'
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Guardado en {out_path} ✓")

if __name__ == "__main__":
    main()
