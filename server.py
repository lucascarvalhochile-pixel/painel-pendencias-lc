#!/usr/bin/env python3
"""
Painel de Pendências LC Turismo
Backend Flask — scraping Reservame + LCX por data
"""
import os, re, json, time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
import requests as http_requests
from bs4 import BeautifulSoup

app = Flask(__name__, static_folder="static")

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
RESERVAME_BASE = "https://zerandoochile.reservame.cl"
LCX_BASE = "https://app.lucascarvalhoturismo.com.br"

RSV_USER = os.environ.get("RSV_USER", "palvimlc")
RSV_PASS = os.environ.get("RSV_PASS", "LC@0410")
LCX_EMAIL = os.environ.get("LCX_EMAIL", "paulinhalvim@gmail.com")
LCX_PASS = os.environ.get("LCX_PASS", "Lcx@0410")

DESTINOS_RSV = [
    "Santiago", "Atacama", "Lima", "Cusco",
    "San Andres", "Cartagena das Indias",
    "Buenos Aires", "Bariloche"
]

LCX_USER_MAP = {
    "cmmazklvs000ulb04lkj6u98j": "Renata Naves",
    "cml9miqpg0000l50443y2lzu2": "Samirah Bueno",
    "cml9nep5a000fl704yu2gmhtx": "Marcela Pedon",
    "cml9df9dv000fjv049u40tcti": "Paulinha",
    "cmm29lpje0006ky04368bmxw5": "Amabilly Cardoso",
    "cmnkiciaq0010ie044jwas9hp": "Caroline Garcia",
    "cml9lk6q10000ld04tfv23ofc": "Isabelle Padilha",
    "cmnkircmw0006l104dok1z5ju": "Anna Karen Silva",
    "cml9lhvdv000al504bs9cbkib": "Isabela Chiquito",
    "cmnkj3lyv000mju04cdrdzxn9": "Maria Júlia Teixeira",
    "cmnkit7ko0006ju04i82os9qm": "Cláudia Araújo",
    "cml9mkrzd0005l504kj6c20sm": "Sergyane Santos",
    "cmnjjivzd0006kt049ylqi8w5": "Thaisa Neves",
    "cml9lxvuf000kl5041d97otwm": "Nayara Soares",
    "cml9mxts20000jr04u9r0mns6": "Giovanna Braga",
    "cml9mtioi0005l7041wtab367": "Thais Zerbieti",
}

# ═══════════════════════════════════════════════════════════════════
# SESSIONS (mantém login ativo)
# ═══════════════════════════════════════════════════════════════════
rsv_session = None
lcx_session = None

def get_rsv_session():
    global rsv_session
    if rsv_session is None:
        rsv_session = http_requests.Session()
        rsv_session.headers.update({"User-Agent": "Mozilla/5.0"})
    # Login
    rsv_session.post(f"{RESERVAME_BASE}/index.php",
        data={"user": RSV_USER, "pass": RSV_PASS, "log": "1", "button": "Entrar"},
        allow_redirects=True, timeout=30)
    return rsv_session

def get_lcx_session():
    global lcx_session
    if lcx_session is None:
        lcx_session = http_requests.Session()
        lcx_session.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        r = lcx_session.get(f"{LCX_BASE}/api/auth/csrf", timeout=20)
        csrf = r.json().get("csrfToken", "")
        lcx_session.post(f"{LCX_BASE}/api/auth/callback/credentials", data={
            "email": LCX_EMAIL, "password": LCX_PASS, "csrfToken": csrf,
            "callbackUrl": f"{LCX_BASE}/dashboard/logistica", "json": "true"
        }, allow_redirects=True, timeout=30)
    except:
        pass
    return lcx_session

def fix_encoding(s):
    if not s: return s
    try:
        return s.encode('latin-1').decode('utf-8')
    except:
        return s

# ═══════════════════════════════════════════════════════════════════
# RESERVAME SCRAPING
# ═══════════════════════════════════════════════════════════════════

def scrape_rsv_date(fecha_str):
    """Scrape Reservame para uma data (YYYY-MM-DD). Retorna lista de reservas."""
    rsv = get_rsv_session()
    today = datetime.now().date()
    all_rows = []
    seen_ids = set()

    for destino in DESTINOS_RSV:
        # Set destination in session
        rsv.get(f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&d={destino}", timeout=20)
        time.sleep(0.15)

        try:
            r = rsv.get(
                f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&fecha1={fecha_str}&grab=1",
                timeout=30
            )
            if "index.php" in r.url:
                rsv = get_rsv_session()
                rsv.get(f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&d={destino}", timeout=20)
                r = rsv.get(f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&fecha1={fecha_str}&grab=1", timeout=30)

            soup = BeautifulSoup(r.text, "html.parser")

            for table in soup.find_all("table"):
                trs = table.find_all("tr")
                if len(trs) < 5:
                    continue
                row3 = trs[3]
                r3_cells = [td.get_text(strip=True) for td in row3.find_all("td")]
                if len(r3_cells) < 10 or "#" not in r3_cells[0]:
                    continue

                tour_info = trs[0].get_text(strip=True)
                tour_name = tour_info
                m = re.search(r'(.+?)\s*-\s*(\w+)\s+(\d{2})-(\d{2})', tour_info)
                if m:
                    tour_name = m.group(1).strip()

                for tr in trs[4:]:
                    tds = tr.find_all("td")
                    if len(tds) < 10:
                        continue
                    cells = [td.get_text(strip=True) for td in tds]
                    if "TOTAL" in cells[0].upper() or "Exportar" in cells[0]:
                        continue

                    rid = cells[3] if len(cells) > 3 else ""
                    if rid in seen_ids:
                        continue
                    seen_ids.add(rid)

                    viaje_num = ""
                    for a in tr.find_all("a"):
                        href = a.get("href", "")
                        if "modificar" in href:
                            vm = re.search(r'VIAJE=(\d+)', href)
                            if vm: viaje_num = vm.group(1)
                    for i_tag in tr.find_all("i"):
                        oc = i_tag.get("onclick", "")
                        vm = re.search(r'VIAJE=(\d+)', oc)
                        if vm: viaje_num = vm.group(1)

                    hotel = cells[6] if len(cells) > 6 else ""
                    telefone = cells[7] if len(cells) > 7 else ""
                    vendedor = cells[8] if len(cells) > 8 else ""
                    valor = cells[9] if len(cells) > 9 else ""
                    pendiente = cells[10] if len(cells) > 10 else ""

                    hotel_ok = bool(hotel and hotel.strip().lower() not in ["", "-", "n/a", "sin hotel", "no", "não", "sem hotel"])
                    tel_ok = bool(telefone and len(telefone.strip()) > 5)
                    fin_ok = not bool(pendiente and any(x in pendiente.lower() for x in ["pend", "debe", "falt"]))

                    # Busca obs
                    obs = ""
                    if viaje_num:
                        try:
                            r2 = rsv.get(f"{RESERVAME_BASE}/modificar.php?VIAJE={viaje_num}", timeout=20)
                            s2 = BeautifulSoup(r2.text, "html.parser")
                            ta = s2.find("textarea", {"name": "obs"})
                            obs = ta.get_text(strip=True) if ta else ""
                        except:
                            pass

                    all_rows.append({
                        "sistema": "Reservame",
                        "destino": destino,
                        "tour": tour_name,
                        "hora": cells[2] if len(cells) > 2 else "",
                        "id": rid,
                        "nome": cells[4] if len(cells) > 4 else "",
                        "pax": cells[5] if len(cells) > 5 else "",
                        "hotel": hotel,
                        "hotelOk": hotel_ok,
                        "telefone": telefone,
                        "telefoneOk": tel_ok,
                        "vendedor": vendedor,
                        "valor": valor,
                        "pendiente": pendiente,
                        "financeiroOk": fin_ok,
                        "obs": obs[:300],
                    })

        except Exception as e:
            print(f"  RSV error {destino} {fecha_str}: {e}")

        time.sleep(0.1)

    return all_rows


# ═══════════════════════════════════════════════════════════════════
# LCX SCRAPING
# ═══════════════════════════════════════════════════════════════════

def scrape_lcx_date(fecha_str):
    """Scrape LCX para uma data (YYYY-MM-DD). Retorna lista de itens."""
    lcx = get_lcx_session()
    items_out = []

    try:
        headers = {
            "Next-Action": "40006e83e282ff0cf7497b47c24ea7331fabda1a0c",
            "Content-Type": "text/plain;charset=UTF-8",
        }
        r = lcx.post(f"{LCX_BASE}/dashboard/logistica",
            headers=headers, data=json.dumps([fecha_str]), timeout=30)

        items = []
        for line in r.text.split("\n"):
            if line.startswith("1:"):
                data = json.loads(line[2:])
                if isinstance(data, dict) and data.get("success"):
                    items = data.get("data", [])
                break

        for item in items:
            sale = item.get("sale", {}) or {}
            customer = sale.get("customer", {}) or {}
            logistics = item.get("logistics", {}) or {}
            voucher = item.get("voucher", {}) or {}

            hotel = fix_encoding(logistics.get("hotel", "") or sale.get("meetingPoint", "") or "")
            telefone = customer.get("whatsapp", "") or sale.get("customerWhatsapp", "") or ""
            vendedor = sale.get("sellerName", "") or ""

            if not vendedor:
                history = sale.get("history", [])
                if history:
                    uid = history[0].get("userId", "")
                    vendedor = LCX_USER_MAP.get(uid, uid[:15])
            if not vendedor:
                uid = customer.get("createdById", "")
                vendedor = LCX_USER_MAP.get(uid, "")

            pay_status = sale.get("status", "")
            hotel_ok = bool(hotel and hotel.strip().lower() not in ["", "-", "n/a"])
            tel_ok = bool(telefone and len(telefone.strip()) > 5)
            fin_ok = pay_status.upper() in ["CONFIRMED", "PAID", "PAGO"]

            items_out.append({
                "sistema": "LCX",
                "destino": fix_encoding(item.get("city", item.get("country", ""))),
                "tour": fix_encoding(item.get("tourName", "")),
                "hora": "",
                "id": sale.get("saleNumber", str(item.get("saleId", ""))),
                "nome": fix_encoding(customer.get("name", sale.get("customerName", ""))),
                "pax": str(item.get("numberOfPeople", "")),
                "hotel": hotel,
                "hotelOk": hotel_ok,
                "telefone": telefone,
                "telefoneOk": tel_ok,
                "vendedor": vendedor,
                "valor": str(item.get("price", "")),
                "pendiente": "",
                "financeiroOk": fin_ok,
                "contrato": bool(item.get("contractSigned")),
                "voucher": voucher.get("status", "sem voucher") if voucher else "sem voucher",
                "obs": fix_encoding((sale.get("notes", "") or "")[:300]),
            })
    except Exception as e:
        print(f"  LCX error {fecha_str}: {e}")

    return items_out


# ═══════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    resp = send_from_directory("static", "index.html")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

@app.route("/api/buscar", methods=["POST"])
def buscar():
    """Busca pendências para uma data ou range de datas."""
    body = request.get_json() or {}
    fecha = body.get("data")  # YYYY-MM-DD
    fecha_fim = body.get("dataFim")  # YYYY-MM-DD (opcional)

    if not fecha:
        return jsonify({"error": "Informe a data"}), 400

    # Se range, gera lista de datas
    datas = [fecha]
    if fecha_fim:
        d = datetime.strptime(fecha, "%Y-%m-%d").date()
        df = datetime.strptime(fecha_fim, "%Y-%m-%d").date()
        datas = []
        while d <= df:
            datas.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)

    all_reservame = []
    all_lcx = []

    for dt in datas:
        rsv_rows = scrape_rsv_date(dt)
        lcx_rows = scrape_lcx_date(dt)
        all_reservame.extend(rsv_rows)
        all_lcx.extend(lcx_rows)

    all_data = all_reservame + all_lcx

    # Stats
    n_hotel = sum(1 for r in all_data if not r.get("hotelOk"))
    n_tel = sum(1 for r in all_data if not r.get("telefoneOk"))
    n_fin = sum(1 for r in all_data if not r.get("financeiroOk"))

    return jsonify({
        "success": True,
        "data": all_data,
        "stats": {
            "total": len(all_data),
            "reservame": len(all_reservame),
            "lcx": len(all_lcx),
            "hotelPend": n_hotel,
            "telPend": n_tel,
            "finPend": n_fin,
        },
        "datas": datas,
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    app.run(host="0.0.0.0", port=port, debug=False)
#!/usr/bin/env python3
"""
Painel de PendÃªncias LC Turismo
Backend Flask â scraping Reservame + LCX por data
"""
import os, re, json, time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
import requests as http_requests
from bs4 import BeautifulSoup

app = Flask(__name__, static_folder="static")

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CONFIG
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
RESERVAME_BASE = "https://zerandoochile.reservame.cl"
LCX_BASE = "https://app.lucascarvalhoturismo.com.br"

RSV_USER = os.environ.get("RSV_USER", "palvimlc")
RSV_PASS = os.environ.get("RSV_PASS", "LC@0410")
LCX_EMAIL = os.environ.get("LCX_EMAIL", "paulinhalvim@gmail.com")
LCX_PASS = os.environ.get("LCX_PASS", "Lcx@0410")

DESTINOS_RSV = [
    "Santiago", "Atacama", "Lima", "Cusco",
    "San Andres", "Cartagena das Indias",
    "Buenos Aires", "Bariloche"
]

LCX_USER_MAP = {
    "cmmazklvs000ulb04lkj6u98j": "Renata Naves",
    "cml9miqpg0000l50443y2lzu2": "Samirah Bueno",
    "cml9nep5a000fl704yu2gmhtx": "Marcela Pedon",
    "cml9df9dv000fjv049u40tcti": "Paulinha",
    "cmm29lpje0006ky04368bmxw5": "Amabilly Cardoso",
    "cmnkiciaq0010ie044jwas9hp": "Caroline Garcia",
    "cml9lk6q10000ld04tfv23ofc": "Isabelle Padilha",
    "cmnkircmw0006l104dok1z5ju": "Anna Karen Silva",
    "cml9lhvdv000al504bs9cbkib": "Isabela Chiquito",
    "cmnkj3lyv000mju04cdrdzxn9": "Maria JÃºlia Teixeira",
    "cmnkit7ko0006ju04i82os9qm": "ClÃ¡udia AraÃºjo",
    "cml9mkrzd0005l504kj6c20sm": "Sergyane Santos",
    "cmnjjivzd0006kt049ylqi8w5": "Thaisa Neves",
    "cml9lxvuf000kl5041d97otwm": "Nayara Soares",
    "cml9mxts20000jr04u9r0mns6": "Giovanna Braga",
    "cml9mtioi0005l7041wtab367": "Thais Zerbieti",
}

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# SESSIONS (mantÃ©m login ativo)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
rsv_session = None
lcx_session = None

def get_rsv_session():
    global rsv_session
    if rsv_session is None:
        rsv_session = http_requests.Session()
        rsv_session.headers.update({"User-Agent": "Mozilla/5.0"})
    # Login
    rsv_session.post(f"{RESERVAME_BASE}/index.php",
        data={"user": RSV_USER, "pass": RSV_PASS, "log": "1", "button": "Entrar"},
        allow_redirects=True, timeout=30)
    return rsv_session

def get_lcx_session():
    global lcx_session
    if lcx_session is None:
        lcx_session = http_requests.Session()
        lcx_session.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        r = lcx_session.get(f"{LCX_BASE}/api/auth/csrf", timeout=20)
        csrf = r.json().get("csrfToken", "")
        lcx_session.post(f"{LCX_BASE}/api/auth/callback/credentials", data={
            "email": LCX_EMAIL, "password": LCX_PASS, "csrfToken": csrf,
            "callbackUrl": f"{LCX_BASE}/dashboard/logistica", "json": "true"
        }, allow_redirects=True, timeout=30)
    except:
        pass
    return lcx_session

def fix_encoding(s):
    if not s: return s
    try:
        return s.encode('latin-1').decode('utf-8')
    except:
        return s

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# RESERVAME SCRAPING
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def scrape_rsv_date(fecha_str):
    """Scrape Reservame para uma data (YYYY-MM-DD). Retorna lista de reservas."""
    rsv = get_rsv_session()
    today = datetime.now().date()
    all_rows = []
    seen_ids = set()

    for destino in DESTINOS_RSV:
        # Set destination in session
        rsv.get(f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&d={destino}", timeout=20)
        time.sleep(0.15)

        try:
            r = rsv.get(
                f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&fecha1={fecha_str}&grab=1",
                timeout=30
            )
            if "index.php" in r.url:
                rsv = get_rsv_session()
                rsv.get(f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&d={destino}", timeout=20)
                r = rsv.get(f"{RESERVAME_BASE}/admin.php?page=ProximosViajes&fecha1={fecha_str}&grab=1", timeout=30)

            soup = BeautifulSoup(r.text, "html.parser")

            for table in soup.find_all("table"):
                trs = table.find_all("tr")
                if len(trs) < 5:
                    continue
                row3 = trs[3]
                r3_cells = [td.get_text(strip=True) for td in row3.find_all("td")]
                if len(r3_cells) < 10 or "#" not in r3_cells[0]:
                    continue

                tour_info = trs[0].get_text(strip=True)
                tour_name = tour_info
                m = re.search(r'(.+?)\s*-\s*(\w+)\s+(\d{2})-(\d{2})', tour_info)
                if m:
                    tour_name = m.group(1).strip()

                for tr in trs[4:]:
                    tds = tr.find_all("td")
                    if len(tds) < 10:
                        continue
                    cells = [td.get_text(strip=True) for td in tds]
                    if "TOTAL" in cells[0].upper() or "Exportar" in cells[0]:
                        continue

                    rid = cells[3] if len(cells) > 3 else ""
                    if rid in seen_ids:
                        continue
                    seen_ids.add(rid)

                    viaje_num = ""
                    for a in tr.find_all("a"):
                        href = a.get("href", "")
                        if "modificar" in href:
                            vm = re.search(r'VIAJE=(\d+)', href)
                            if vm: viaje_num = vm.group(1)
                    for i_tag in tr.find_all("i"):
                        oc = i_tag.get("onclick", "")
                        vm = re.search(r'VIAJE=(\d+)', oc)
                        if vm: viaje_num = vm.group(1)

                    hotel = cells[6] if len(cells) > 6 else ""
                    telefone = cells[7] if len(cells) > 7 else ""
                    vendedor = cells[8] if len(cells) > 8 else ""
                    valor = cells[9] if len(cells) > 9 else ""
                    pendiente = cells[10] if len(cells) > 10 else ""

                    hotel_ok = bool(hotel and hotel.strip().lower() not in ["", "-", "n/a", "sin hotel", "no", "nÃ£o", "sem hotel"])
                    tel_ok = bool(telefone and len(telefone.strip()) > 5)
                    fin_ok = not bool(pendiente and any(x in pendiente.lower() for x in ["pend", "debe", "falt"]))

                    # Busca obs
                    obs = ""
                    if viaje_num:
                        try:
                            r2 = rsv.get(f"{RESERVAME_BASE}/modificar.php?VIAJE={viaje_num}", timeout=20)
                            s2 = BeautifulSoup(r2.text, "html.parser")
                            ta = s2.find("textarea", {"name": "obs"})
                            obs = ta.get_text(strip=True) if ta else ""
                        except:
                            pass

                    all_rows.append({
                        "sistema": "Reservame",
                        "destino": destino,
                        "tour": tour_name,
                        "hora": cells[2] if len(cells) > 2 else "",
                        "id": rid,
                        "nome": cells[4] if len(cells) > 4 else "",
                        "pax": cells[5] if len(cells) > 5 else "",
                        "hotel": hotel,
                        "hotelOk": hotel_ok,
                        "telefone": telefone,
                        "telefoneOk": tel_ok,
                        "vendedor": vendedor,
                        "valor": valor,
                        "pendiente": pendiente,
                        "financeiroOk": fin_ok,
                        "obs": obs[:300],
                    })

        except Exception as e:
            print(f"  RSV error {destino} {fecha_str}: {e}")

        time.sleep(0.1)

    return all_rows


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# LCX SCRAPING
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def scrape_lcx_date(fecha_str):
    """Scrape LCX para uma data (YYYY-MM-DD). Retorna lista de itens."""
    lcx = get_lcx_session()
    items_out = []

    try:
        headers = {
            "Next-Action": "40006e83e282ff0cf7497b47c24ea7331fabda1a0c",
            "Content-Type": "text/plain;charset=UTF-8",
        }
        r = lcx.post(f"{LCX_BASE}/dashboard/logistica",
            headers=headers, data=json.dumps([fecha_str]), timeout=30)

        items = []
        for line in r.text.split("\n"):
            if line.startswith("1:"):
                data = json.loads(line[2:])
                if isinstance(data, dict) and data.get("success"):
                    items = data.get("data", [])
                break

        for item in items:
            sale = item.get("sale", {}) or {}
            customer = sale.get("customer", {}) or {}
            logistics = item.get("logistics", {}) or {}
            voucher = item.get("voucher", {}) or {}

            hotel = fix_encoding(logistics.get("hotel", "") or sale.get("meetingPoint", "") or "")
            telefone = customer.get("whatsapp", "") or sale.get("customerWhatsapp", "") or ""
            vendedor = sale.get("sellerName", "") or ""

            if not vendedor:
                history = sale.get("history", [])
                if history:
                    uid = history[0].get("userId", "")
                    vendedor = LCX_USER_MAP.get(uid, uid[:15])
            if not vendedor:
                uid = customer.get("createdById", "")
                vendedor = LCX_USER_MAP.get(uid, "")

            pay_status = sale.get("status", "")
            hotel_ok = bool(hotel and hotel.strip().lower() not in ["", "-", "n/a"])
            tel_ok = bool(telefone and len(telefone.strip()) > 5)
            fin_ok = pay_status.upper() in ["CONFIRMED", "PAID", "PAGO"]

            items_out.append({
                "sistema": "LCX",
                "destino": fix_encoding(item.get("city", item.get("country", ""))),
                "tour": fix_encoding(item.get("tourName", "")),
                "hora": "",
                "id": sale.get("saleNumber", str(item.get("saleId", ""))),
                "nome": fix_encoding(customer.get("name", sale.get("customerName", ""))),
                "pax": str(item.get("numberOfPeople", "")),
                "hotel": hotel,
                "hotelOk": hotel_ok,
                "telefone": telefone,
                "telefoneOk": tel_ok,
                "vendedor": vendedor,
                "valor": str(item.get("price", "")),
                "pendiente": "",
                "financeiroOk": fin_ok,
                "contrato": bool(item.get("contractSigned")),
                "voucher": voucher.get("status", "sem voucher") if voucher else "sem voucher",
                "obs": fix_encoding((sale.get("notes", "") or "")[:300]),
            })
    except Exception as e:
        print(f"  LCX error {fecha_str}: {e}")

    return items_out


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# API ROUTES
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/buscar", methods=["POST"])
def buscar():
    """Busca pendÃªncias para uma data ou range de datas."""
    body = request.get_json() or {}
    fecha = body.get("data")  # YYYY-MM-DD
    fecha_fim = body.get("dataFim")  # YYYY-MM-DD (opcional)

    if not fecha:
        return jsonify({"error": "Informe a data"}), 400

    # Se range, gera lista de datas
    datas = [fecha]
    if fecha_fim:
        d = datetime.strptime(fecha, "%Y-%m-%d").date()
        df = datetime.strptime(fecha_fim, "%Y-%m-%d").date()
        datas = []
        while d <= df:
            datas.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)

    all_reservame = []
    all_lcx = []

    for dt in datas:
        rsv_rows = scrape_rsv_date(dt)
        lcx_rows = scrape_lcx_date(dt)
        all_reservame.extend(rsv_rows)
        all_lcx.extend(lcx_rows)

    all_data = all_reservame + all_lcx

    # Stats
    n_hotel = sum(1 for r in all_data if not r.get("hotelOk"))
    n_tel = sum(1 for r in all_data if not r.get("telefoneOk"))
    n_fin = sum(1 for r in all_data if not r.get("financeiroOk"))

    return jsonify({
        "success": True,
        "data": all_data,
        "stats": {
            "total": len(all_data),
            "reservame": len(all_reservame),
            "lcx": len(all_lcx),
            "hotelPend": n_hotel,
            "telPend": n_tel,
            "finPend": n_fin,
        },
        "datas": datas,
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# MAIN
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    app.run(host="0.0.0.0", port=port, debug=False)
