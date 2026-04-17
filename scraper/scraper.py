import requests
from bs4 import BeautifulSoup
import json, re, time
from datetime import datetime, date

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MONTHS = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    "ene":1,"abr":4,"ago":8
}

def normalize(t):
    return " ".join((t or "").split()).strip()

def parse_date(text):
    if not text: return None
    t = text.lower().strip()
    # ISO yyyy-mm-dd
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
    if m: return m.group(0)
    # dd/mm/yyyy
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', t)
    if m: return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # dd de mes [de] yyyy
    m = re.search(r'(\d{1,2})\s+(?:de\s+)?(\w+)\s+(?:de\s+)?(\d{4})', t)
    if m:
        mon = MONTHS.get(m.group(2)[:3])
        if mon: return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    # dd mes (current year)
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

def get(url, timeout=14):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  WARN {url[:60]}: {e}")
        return None

def make_event(titulo, fecha, hora, sala, fuente, url, imagen="", descripcion=""):
    return {
        "titulo": normalize(titulo),
        "fecha": fecha or "",
        "hora": hora or "",
        "sala": normalize(sala),
        "fuente": fuente,
        "url": url or "",
        "imagen": imagen or "",
        "descripcion": normalize(descripcion),
    }

def dedup_articles(soup, selectors):
    """Try multiple CSS selectors, return first that gives results."""
    for sel in selectors:
        items = soup.select(sel)
        if items: return items
    return []

# ── SCRAPERS ─────────────────────────────────────────────────────────────────

def scrape_ayto_zaragoza():
    events = []
    today = date.today().isoformat()
    url = f"https://www.zaragoza.es/sede/servicio/actividad.json?tematica=3&rows=200&start=0&fechaInicio={today}"
    r = get(url)
    if not r: return events
    try:
        data = r.json()
        for item in data.get("result", []):
            title = normalize(item.get("title",""))
            if not title: continue
            fecha_raw = item.get("fechaInicio","") or item.get("fecha","")
            hora_raw  = item.get("horaInicio","") or ""
            lugar = normalize(item.get("organizacion","") or item.get("lugar","") or "Zaragoza")
            link  = item.get("link","") or ""
            img   = item.get("imagen","") or ""
            desc  = normalize(item.get("descripcion","") or "")
            events.append(make_event(title, parse_date(fecha_raw) or fecha_raw[:10], parse_time(hora_raw), lugar, "Ayto. Zaragoza", link, img, desc))
    except Exception as e:
        print(f"  ERR ayto json: {e}")
    print(f"  ayto: {len(events)}")
    return events

def scrape_zgzconciertos():
    """zgzconciertos.com/agenda/lista/ — buena fuente local"""
    events = []
    r = get("https://zgzconciertos.com/agenda/lista/")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in soup.select(".tribe-events-calendar-list__event, article.type-tribe_events, .tribe_events_cat"):
        title_el = art.select_one(".tribe-event-url, .tribe-events-calendar-list__event-title a, h2 a, h3 a")
        date_el  = art.select_one("time, .tribe-event-date-start, [class*='date']")
        loc_el   = art.select_one(".tribe-venue, .tribe-events-schedule, [class*='venue'], [class*='lugar']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        events.append(make_event(
            title,
            parse_date(fecha_raw) or "",
            parse_time(fecha_raw),
            normalize(loc_el.get_text()) if loc_el else "Zaragoza",
            "zgzconciertos.com",
            link_el["href"] if link_el else "https://zgzconciertos.com",
            img_el.get("src","") if img_el else ""
        ))
    print(f"  zgzconciertos: {len(events)}")
    return events

def scrape_aragonenvivo():
    """aragonenvivo.com/eventos/"""
    events = []
    r = get("https://aragonenvivo.com/eventos/")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in dedup_articles(soup, [".tribe-events-calendar-list__event","article.type-tribe_events","article"]):
        title_el = art.select_one("h2 a, h3 a, .entry-title a, a")
        date_el  = art.select_one("time,[class*='date'],[class*='fecha']")
        loc_el   = art.select_one("[class*='venue'],[class*='lugar'],[class*='location']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        # Filter only Zaragoza events
        loc_txt = normalize(loc_el.get_text()) if loc_el else ""
        if loc_txt and "zaragoza" not in loc_txt.lower() and "zgz" not in loc_txt.lower():
            continue
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            loc_txt or "Zaragoza", "aragonenvivo.com",
            link_el["href"] if link_el else "https://aragonenvivo.com",
            img_el.get("src","") if img_el else ""
        ))
    print(f"  aragonenvivo: {len(events)}")
    return events

def scrape_sala_oasis():
    events = []
    r = get("https://www.salaoasis.com/agenda-oasis/")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in dedup_articles(soup, [".tribe-events-calendar-list__event","article.type-tribe_events","article",".event"]):
        title_el = art.select_one("h2 a, h3 a, .tribe-event-url, a")
        date_el  = art.select_one("time,[class*='date'],[class*='fecha']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            "Sala Oasis", "salaoasis.com",
            link_el["href"] if link_el else "https://www.salaoasis.com",
            img_el.get("src","") if img_el else ""
        ))
    print(f"  sala oasis: {len(events)}")
    return events

def scrape_sala_lopez():
    events = []
    for url in ["https://salalopez.com/eventos/", "https://salalopez.com/agenda/"]:
        r = get(url)
        if r: break
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in dedup_articles(soup, [".tribe-events-calendar-list__event","article.type-tribe_events","article",".event"]):
        title_el = art.select_one("h2 a, h3 a, .tribe-event-url, a")
        date_el  = art.select_one("time,[class*='date'],[class*='fecha']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            "Sala López", "salalopez.com",
            link_el["href"] if link_el else "https://salalopez.com",
            img_el.get("src","") if img_el else ""
        ))
    print(f"  sala lopez: {len(events)}")
    return events

def scrape_rock_blues():
    events = []
    r = get("https://www.rockandbluescafe.com/conciertos/")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in dedup_articles(soup, ["article",".event",".concierto","[class*='event']"]):
        title_el = art.select_one("h2,h3,h4,a")
        date_el  = art.select_one("time,[class*='date'],[class*='fecha']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            "Rock & Blues Café", "rockandbluescafe.com",
            link_el["href"] if link_el else "https://www.rockandbluescafe.com",
            img_el.get("src","") if img_el else ""
        ))
    print(f"  rock&blues: {len(events)}")
    return events

def scrape_enjoyzaragoza():
    events = []
    r = get("https://www.enjoyzaragoza.es/conciertos-zaragoza/")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in dedup_articles(soup, ["article",".event","[class*='event']",".post"]):
        title_el = art.select_one("h2 a,h3 a,a")
        date_el  = art.select_one("time,[class*='date'],[class*='fecha']")
        loc_el   = art.select_one("[class*='venue'],[class*='lugar'],[class*='location']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            normalize(loc_el.get_text()) if loc_el else "Zaragoza",
            "enjoyzaragoza.es",
            link_el["href"] if link_el else "https://www.enjoyzaragoza.es",
            img_el.get("src","") if img_el else ""
        ))
    print(f"  enjoyzaragoza: {len(events)}")
    return events

def scrape_songkick():
    """Songkick Zaragoza metro area"""
    events = []
    r = get("https://www.songkick.com/es/metro-areas/28809-spain-zaragoza")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for li in soup.select("li.event, .event-listings li, ul.event-listings > li"):
        title_el = li.select_one(".summary strong, .event-details .title, h3, strong")
        date_el  = li.select_one("time, .date, p.date")
        loc_el   = li.select_one(".venue-name, .location")
        img_el   = li.select_one("img")
        link_el  = li.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"): href = "https://www.songkick.com" + href
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            normalize(loc_el.get_text()) if loc_el else "Zaragoza",
            "songkick.com",
            href,
            img_el.get("src","") if img_el else ""
        ))
    print(f"  songkick: {len(events)}")
    return events

def scrape_conciertos_club():
    events = []
    r = get("https://conciertos.club/zaragoza")
    if not r: return events
    soup = BeautifulSoup(r.text, "html.parser")
    for art in dedup_articles(soup, ["article",".event","[class*='concert']","[class*='event']"]):
        title_el = art.select_one("h2,h3,h4,a")
        date_el  = art.select_one("time,[class*='date'],[class*='fecha']")
        loc_el   = art.select_one("[class*='venue'],[class*='lugar']")
        img_el   = art.select_one("img")
        link_el  = art.select_one("a[href]")
        title = normalize(title_el.get_text()) if title_el else ""
        if not title or len(title) < 3: continue
        fecha_raw = (date_el.get("datetime","") or date_el.get_text()) if date_el else ""
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"): href = "https://conciertos.club" + href
        events.append(make_event(
            title, parse_date(fecha_raw) or "", parse_time(fecha_raw),
            normalize(loc_el.get_text()) if loc_el else "Zaragoza",
            "conciertos.club",
            href,
            img_el.get("src","") if img_el else ""
        ))
    print(f"  conciertos.club: {len(events)}")
    return events

# ── CONSOLIDATION ─────────────────────────────────────────────────────────────

def deduplicate(events):
    seen = {}
    for e in events:
        key = (re.sub(r'\s+','',e["titulo"].lower())[:35], e["fecha"])
        if key not in seen:
            seen[key] = e
        else:
            ex = seen[key]
            # Prefer entry with more data
            score_new = bool(e["imagen"]) + bool(e["hora"]) + bool(e["descripcion"]) + bool(e["sala"] != "Zaragoza")
            score_ex  = bool(ex["imagen"]) + bool(ex["hora"]) + bool(ex["descripcion"]) + bool(ex["sala"] != "Zaragoza")
            if score_new > score_ex:
                seen[key] = e
    return list(seen.values())

def filter_future(events):
    today = date.today().isoformat()
    return [e for e in events if not e["fecha"] or e["fecha"] >= today]

def sort_events(events):
    return sorted(events, key=lambda e: (e["fecha"] or "9999", e["hora"] or "99:99"))

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nPinPlan scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    all_events = []

    scrapers = [
        ("Ayto. Zaragoza",   scrape_ayto_zaragoza),
        ("ZGZ Conciertos",   scrape_zgzconciertos),
        ("Aragón en Vivo",   scrape_aragonenvivo),
        ("Sala Oasis",       scrape_sala_oasis),
        ("Sala López",       scrape_sala_lopez),
        ("Rock & Blues",     scrape_rock_blues),
        ("Enjoy Zaragoza",   scrape_enjoyzaragoza),
        ("Songkick",         scrape_songkick),
        ("Conciertos.club",  scrape_conciertos_club),
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
    with open("../web/eventos.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Guardado en web/eventos.json ✓")

if __name__ == "__main__":
    main()
