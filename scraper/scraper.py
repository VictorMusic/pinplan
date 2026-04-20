import requests
from bs4 import BeautifulSoup
import json, re, time
from datetime import datetime, date

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

MONTHS = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    "ene":1,"abr":4,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12
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
                print(f"  WARN {url[:70]}: {e}")
            time.sleep(1)
    return None

def make_event(titulo, fecha, hora, sala, url, imagen="", descripcion=""):
    return {
        "titulo": normalize(titulo),
        "fecha": fecha or "",
        "hora": hora or "",
        "sala": normalize(sala),
        "url": url or "",
        "imagen": imagen or "",
        "descripcion": normalize(descripcion),
    }

def extract_tribe_events(soup, sala_default, base_url):
    events = []
    articles = []
    for sel in [
        "article.type-tribe_events", "article.tribe_events_cat",
        ".tribe-events-calendar-list__event", ".tribe-event-list-item",
        ".tribe-events-loop article", "article[class*='tribe']",
        ".events-archive article", ".event-list article",
    ]:
        items = soup.select(sel)
        if items:
            articles = items
            break

    for art in articles:
        title_el = art.select_one(
            ".tribe-event-url, .tribe-events-calendar-list__event-title a, "
            ".tribe-events-list-event-title a, h2 a, h3 a, .entry-title a"
        )
        date_el = art.select_one(
            "time[datetime], .tribe-event-date-start, "
            ".tribe-events-calendar-list__event-datetime, "
            ".tribe-events-schedule abbr, [class*='tribe-event-date']"
        )
        loc_el = art.select_one(".tribe-venue, [class*='tribe-venue'], [class*='venue']")
        img_el = art.select_one("img")
        link_el = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = ""
        if date_el:
            fecha_raw = date_el.get("datetime", "") or date_el.get_text()
        hora_el = art.select_one("[class*='time'], .tribe-events-schedule")
        hora_raw = hora_el.get_text() if hora_el else fecha_raw
        sala = normalize(loc_el.get_text()) if loc_el else sala_default
        if not sala or len(sala) < 2: sala = sala_default
        href = link_el["href"] if link_el else base_url
        if href and not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")
        img = ""
        if img_el:
            img = img_el.get("src", "") or img_el.get("data-src", "") or img_el.get("data-lazy-src", "")
        events.append(make_event(title, parse_date(fecha_raw) or "", parse_time(hora_raw), sala, href, img))
    return events

def scrape_generic(url, sala_name, base_url):
    events = []
    r = get(url)
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    evs = extract_tribe_events(soup, sala_name, base_url)
    if not evs:
        for art in soup.select("article, .event, [class*='event'], [class*='concierto'], [class*='show']"):
            title_el = art.select_one("h2 a, h3 a, h4 a, .entry-title a, a")
            date_el  = art.select_one("time, [class*='date'], [class*='fecha']")
            img_el   = art.select_one("img")
            link_el  = art.select_one("a[href]")
            title = normalize(title_el.get_text()) if title_el else ""
            if not title or len(title) < 3: continue
            fecha_raw = (date_el.get("datetime", "") or date_el.get_text()) if date_el else ""
            href = link_el["href"] if link_el else base_url
            if href and not href.startswith("http"):
                href = base_url.rstrip("/") + "/" + href.lstrip("/")
            evs.append(make_event(
                title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
                sala_name, href,
                img_el.get("src", "") if img_el else ""
            ))
    return evs

def scrape_ayto_zaragoza():
    events = []
    from datetime import timedelta
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=30)).isoformat()
    for url in [
        f"https://www.zaragoza.es/sede/servicio/actividad.json?rows=500&start=0&fechaInicio={today}&fechaFin={end}",
        f"https://www.zaragoza.es/sede/servicio/actividad.json?rows=500&start=0&fechaInicio={today}",
        "https://www.zaragoza.es/sede/servicio/actividad.json?rows=500&start=0",
    ]:
        r = get(url)
        if not r: continue
        try:
            data = r.json()
            results = data.get("result", [])
            if not results: continue
            for item in results:
                title = normalize(item.get("title", ""))
                if not title: continue
                fecha_raw = item.get("fechaInicio", "") or item.get("fecha", "")
                hora_raw  = item.get("horaInicio", "") or ""
                lugar = normalize(item.get("organizacion", "") or item.get("lugar", "") or "Zaragoza")
                link  = item.get("link", "") or ""
                img   = item.get("imagen", "") or ""
                desc  = normalize(item.get("descripcion", "") or "")
                events.append(make_event(
                    title,
                    parse_date(fecha_raw) or fecha_raw[:10] if fecha_raw else "",
                    parse_time(hora_raw), lugar, link, img, desc
                ))
            print(f"  ayto zaragoza: {len(events)}")
            return events
        except Exception as e:
            print(f"  ERR ayto: {e}")
    print(f"  ayto zaragoza: 0")
    return events

def scrape_zgzconciertos():
    evs = scrape_generic("https://zgzconciertos.com/agenda/lista/", "Zaragoza", "https://zgzconciertos.com")
    print(f"  zgzconciertos: {len(evs)}")
    return evs

def scrape_aragonenvivo():
    evs = []
    for url in ["https://aragonenvivo.com/eventos/", "https://aragonenvivo.com/agenda/"]:
        evs = scrape_generic(url, "Zaragoza", "https://aragonenvivo.com")
        # Filter only Zaragoza
        filtered = [e for e in evs if not e["sala"] or "zaragoza" in e["sala"].lower() or e["sala"] == "Zaragoza"]
        if not filtered: filtered = evs  # keep all if can't filter
        if filtered: break
    print(f"  aragonenvivo: {len(evs)}")
    return evs

def scrape_enjoyzaragoza():
    evs = scrape_generic("https://www.enjoyzaragoza.es/conciertos-zaragoza/", "Zaragoza", "https://www.enjoyzaragoza.es")
    print(f"  enjoyzaragoza: {len(evs)}")
    return evs

def scrape_sala_lopez():
    evs = []
    for url in ["https://salalopez.com/eventos/", "https://salalopez.com/agenda/", "https://salalopez.com/"]:
        evs = scrape_generic(url, "Sala López", "https://salalopez.com")
        if evs: break
    print(f"  sala lopez: {len(evs)}")
    return evs

def scrape_sala_oasis():
    evs = scrape_generic("https://www.salaoasis.com/agenda-oasis/", "Sala Oasis", "https://www.salaoasis.com")
    print(f"  sala oasis: {len(evs)}")
    return evs

def scrape_creedence():
    evs = []
    for url in ["https://creedencesound.com/agenda/", "https://creedencesound.com/"]:
        evs = scrape_generic(url, "Sala Creedence", "https://creedencesound.com")
        if evs: break
    print(f"  creedence: {len(evs)}")
    return evs

def scrape_lata_bombillas():
    evs = []
    for url in ["https://lalatadebombillas.es/agenda/", "https://lalatadebombillas.es/"]:
        evs = scrape_generic(url, "La Lata de Bombillas", "https://lalatadebombillas.es")
        if evs: break
    print(f"  lata bombillas: {len(evs)}")
    return evs

def scrape_rock_blues():
    evs = []
    for url in ["https://www.rockandbluescafe.com/conciertos/", "https://www.rockandbluescafe.com/agenda/", "https://www.rockandbluescafe.com/"]:
        evs = scrape_generic(url, "Rock & Blues Café", "https://www.rockandbluescafe.com")
        if evs: break
    print(f"  rock&blues: {len(evs)}")
    return evs

def scrape_teatro_esquinas():
    evs = []
    for url in [
        "https://www.teatrodelasesquinas.com/es/programacion-de-teatro-y-conciertos.html",
        "https://teatrodelasesquinas.com/programacion/",
        "https://teatrodelasesquinas.com/",
    ]:
        evs = scrape_generic(url, "Teatro de las Esquinas", "https://www.teatrodelasesquinas.com")
        if evs: break
    print(f"  teatro esquinas: {len(evs)}")
    return evs

def scrape_auditori_zaragoza():
    evs = []
    for url in [
        "https://auditoriozaragoza.com/agenda/conciertos/",
        "https://auditoriozaragoza.com/agenda/",
        "https://auditoriozaragoza.com/",
    ]:
        evs = scrape_generic(url, "Auditorio de Zaragoza", "https://auditoriozaragoza.com")
        if evs: break
    print(f"  auditori: {len(evs)}")
    return evs

def scrape_aragonmusical():
    evs = []
    for url in [
        "https://www.aragonmusical.com/conciertos-en-zaragoza/",
        "https://www.aragonmusical.com/agenda/",
        "https://www.aragonmusical.com/",
    ]:
        evs = scrape_generic(url, "Zaragoza", "https://www.aragonmusical.com")
        if evs: break
    # Filter only Zaragoza
    evs = [e for e in evs if not e["sala"] or "zaragoza" in e["sala"].lower() or e["sala"] == "Zaragoza"]
    print(f"  aragonmusical: {len(evs)}")
    return evs

def scrape_taquilla():
    events = []
    r = get("https://www.taquilla.com/conciertos/zaragoza")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in soup.select("article, .event, .concert, [class*='event'], [class*='concert'], .card"):
        title_el = art.select_one("h2 a, h3 a, h4 a, .title a, a")
        date_el  = art.select_one("time, [class*='date'], [class*='fecha'], [itemprop='startDate']")
        loc_el   = art.select_one("[class*='venue'], [class*='lugar'], [itemprop='location']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get("content","") or date_el.get_text()) if date_el else ""
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"): href = "https://www.taquilla.com" + href
        img = ""
        if img_el:
            img = img_el.get("src","") or img_el.get("data-src","") or img_el.get("data-lazy-src","")
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            normalize(loc_el.get_text()) if loc_el else "Zaragoza",
            href, img
        ))
    print(f"  taquilla.com: {len(events)}")
    return events

def scrape_green_heart():
    evs = []
    for url in ["https://elcorazonverdebar.com/agenda/", "https://elcorazonverdebar.com/"]:
        evs = scrape_generic(url, "Green Heart", "https://elcorazonverdebar.com")
        if evs: break
    print(f"  green heart: {len(evs)}")
    return evs

def scrape_pub_utopia():
    evs = []
    for url in ["https://www.pubutopia.com/agenda/", "https://www.pubutopia.com/"]:
        evs = scrape_generic(url, "Pub Utopia", "https://www.pubutopia.com")
        if evs: break
    print(f"  pub utopia: {len(evs)}")
    return evs

def scrape_songkick():
    events = []
    r = get("https://www.songkick.com/es/metro-areas/28809-spain-zaragoza")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for li in soup.select("li.event, .event-listings li, ul.event-listings > li, .concerts-list li"):
        title_el = li.select_one(".summary strong, h3, strong, .artist-name")
        date_el  = li.select_one("time, .date, p.date")
        loc_el   = li.select_one(".venue-name, .location")
        img_el   = li.select_one("img")
        link_el  = li.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime", "") or date_el.get_text()) if date_el else ""
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"): href = "https://www.songkick.com" + href
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            normalize(loc_el.get_text()) if loc_el else "Zaragoza",
            href, img_el.get("src", "") if img_el else ""
        ))
    print(f"  songkick: {len(events)}")
    return events

def deduplicate(events):
    seen = {}
    for e in events:
        key = (re.sub(r'\s+', '', e["titulo"].lower())[:35], e["fecha"])
        if key not in seen:
            seen[key] = e
        else:
            ex = seen[key]
            score_new = bool(e["imagen"]) + bool(e["hora"]) + bool(e["descripcion"]) + (e["sala"] not in ["Zaragoza", ""])
            score_ex  = bool(ex["imagen"]) + bool(ex["hora"]) + bool(ex["descripcion"]) + (ex["sala"] not in ["Zaragoza", ""])
            if score_new > score_ex:
                seen[key] = e
    return list(seen.values())

def filter_future(events):
    from datetime import timedelta
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=30)).isoformat()
    return [e for e in events if not e["fecha"] or (e["fecha"] >= today and e["fecha"] <= cutoff)]

def sort_events(events):
    return sorted(events, key=lambda e: (e["fecha"] or "9999", e["hora"] or "99:99"))

def main():
    print(f"\nPinPlan scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    all_events = []
    scrapers = [
        ("Ayto. Zaragoza",       scrape_ayto_zaragoza),
        ("ZGZ Conciertos",       scrape_zgzconciertos),
        ("Aragón en Vivo",       scrape_aragonenvivo),
        ("Enjoy Zaragoza",       scrape_enjoyzaragoza),
        ("Sala López",           scrape_sala_lopez),
        ("Sala Oasis",           scrape_sala_oasis),
        ("Sala Creedence",       scrape_creedence),
        ("La Lata de Bombillas", scrape_lata_bombillas),
        ("Rock & Blues Café",    scrape_rock_blues),
        ("Teatro Esquinas",      scrape_teatro_esquinas),
        ("Auditori Zaragoza",    scrape_auditori_zaragoza),
        ("Aragón Musical",       scrape_aragonmusical),
        ("Taquilla.com",         scrape_taquilla),
        ("Green Heart",          scrape_green_heart),
        ("Pub Utopia",           scrape_pub_utopia),
        ("Songkick",             scrape_songkick),
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

    output = {
        "actualizado": datetime.now().isoformat(),
        "total": len(all_events),
        "eventos": all_events
    }
    with open("../eventos.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Guardado en eventos.json ✓")

if __name__ == "__main__":
    main()
