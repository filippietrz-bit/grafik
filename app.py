import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from github import Github
from io import StringIO
from fpdf import FPDF

# --- KONFIGURACJA ZESPOŁU ---

FIXED_DOCTORS = [
    "Jakub Sz.", "Gerard", "Tomasz", "Rafał", "Marcin", "Weronika", "Daniel"
]

ROTATION_DOCTORS = [
    "Jędrzej", "Filip", "Ihab", "Kacper", "Jakub", "Tymoteusz"
]

# Lekarze objęci limitem 48h (Bez Opt-Out)
NO_OPTOUT_DOCTORS = [
    "Jędrzej", "Filip", "Ihab", "Jakub", "Tymoteusz"
]

# Lekarze z regułą: Dyżur Sobota -> Wolny Poniedziałek
SATURDAY_RULE_DOCTORS = ["Daniel", "Kacper"]

ALL_DOCTORS = FIXED_DOCTORS + ROTATION_DOCTORS

STATUS_AVAILABLE = "Chcę dyżur (Dostępny)"
STATUS_RELUCTANT = "Mogę (Niechętnie)"
STATUS_UNAVAILABLE = "Niedostępny"
STATUS_FIXED = "Sztywny Dyżur (Już ustalony)"

REASONS = ["", "Urlop", "Kurs", "Inne"]
DATA_FILE = "data.csv"
DAY_GROUPS_LIST = ["Poniedziałki", "Wtorki/Środy", "Czwartki", "Piątki", "Soboty", "Niedziele"]

# --- INFRASTRUKTURA (GITHUB & DATA) ---

@st.cache_resource
def get_repo():
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        user = g.get_user()
        # Szukamy repozytorium po nazwie lub bierzemy pierwsze dostępne
        for repo in user.get_repos():
             if any(x in repo.name.lower() for x in ["grafik", "urologia", "dyzury"]): return repo
        return user.get_repos()[0]
    except Exception as e:
        st.error(f"Błąd połączenia z GitHubem: {e}")
        return None

@st.cache_data(ttl=60)
def load_data():
    repo = get_repo()
    if not repo: return pd.DataFrame(columns=["Data", "Lekarz", "Status", "Przyczyna"])
    try:
        c = repo.get_contents(DATA_FILE)
        df = pd.read_csv(StringIO(c.decoded_content.decode("utf-8"))).astype({'Data': str})
        if 'Przyczyna' not in df.columns: df['Przyczyna'] = ""
        return df.fillna("")
    except: return pd.DataFrame(columns=["Data", "Lekarz", "Status", "Przyczyna"])

def save_data(df):
    repo = get_repo()
    if not repo: return False
    if 'Przyczyna' not in df.columns: df['Przyczyna'] = ""
    try:
        c = repo.get_contents(DATA_FILE)
        repo.update_file(c.path, "Aktualizacja grafiku", df.to_csv(index=False), c.sha)
        st.cache_data.clear() # Wymuś odświeżenie cache po zapisie
        return True
    except:
        try: repo.create_file(DATA_FILE, "Inicjalizacja", df.to_csv(index=False)); st.cache_data.clear(); return True
        except: return False

# --- LOGIKA KALENDARZA & ŚWIĄT ---

@st.cache_data(ttl=3600)
def get_polish_holidays(year):
    # Algorytm obliczania Wielkanocy
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = datetime.date(year, month, day)
    
    holidays = {
        datetime.date(year, 1, 1): "Nowy Rok",
        datetime.date(year, 1, 6): "Trzech Króli",
        easter: "Wielkanoc",
        easter + datetime.timedelta(days=1): "Poniedziałek Wielkanocny",
        datetime.date(year, 5, 1): "Święto Pracy",
        datetime.date(year, 5, 3): "Święto Konstytucji 3 Maja",
        easter + datetime.timedelta(days=49): "Zielone Świątki",
        easter + datetime.timedelta(days=60): "Boże Ciało",
        datetime.date(year, 8, 15): "Wniebowzięcie NMP",
        datetime.date(year, 11, 1): "Wszystkich Świętych",
        datetime.date(year, 11, 11): "Święto Niepodległości",
        datetime.date(year, 12, 25): "Boże Narodzenie (1)",
        datetime.date(year, 12, 26): "Boże Narodzenie (2)",
    }
    return holidays

def is_red_day(date_obj):
    if date_obj.weekday() >= 5: return True 
    holidays = get_polish_holidays(date_obj.year)
    return date_obj in holidays

def get_day_description(date_obj):
    days_pl = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"]
    day_name = days_pl[date_obj.weekday()]
    holidays = get_polish_holidays(date_obj.year)
    if date_obj in holidays: return f"🔴 {day_name} ({holidays[date_obj]})"
    elif date_obj.weekday() >= 5: return f"🔴 {day_name}"
    return day_name

def get_settlement_period_info(year, month):
    start_month = month if month % 2 != 0 else month - 1
    start_date = datetime.date(year, start_month, 1)
    day_names = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
    return start_date, day_names[start_date.weekday()]

def get_period_dates(year, start_month):
    dates = []
    for i in range(2):
        curr = start_month + i
        if curr <= 12:
            nd = calendar.monthrange(year, curr)[1]
            dates.extend([datetime.date(year, curr, d) for d in range(1, nd + 1)])
    return dates

def get_week_key(date_obj):
    p_start, _ = get_settlement_period_info(date_obj.year, date_obj.month)
    days = (date_obj - p_start).days
    return f"{date_obj.year}_M{p_start.month}_W{days // 7}"

def get_day_group(date_obj):
    wd = date_obj.weekday()
    if wd == 0: return "Poniedziałki"
    if wd in [1, 2]: return "Wtorki/Środy"
    if wd == 3: return "Czwartki"
    if wd == 4: return "Piątki"
    if wd == 5: return "Soboty"
    return "Niedziele"

# --- PDF GENERATOR ---

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Grafik Dyzurów - Urologia', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Strona {self.page_no()}', 0, 0, 'C')

def remove_pl_chars(text):
    if not isinstance(text, str): return str(text)
    replacements = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z',
        '🔴': ' ', '⚠️': '!', '✅': 'OK'
    }
    for k, v in replacements.items(): text = text.replace(k, v)
    try: return text.encode('latin-1', 'replace').decode('latin-1')
    except: return "?"

def create_pdf_bytes(dataframe, title):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    safe_title = remove_pl_chars(title)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, safe_title, 0, 1, 'L')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 10, 'Data', 1)
    pdf.cell(60, 10, 'Dzien', 1)
    pdf.cell(80, 10, 'Lekarz', 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=10)
    for _, row in dataframe.iterrows():
        d_str = row['Data'].strftime('%Y-%m-%d')
        day_str = remove_pl_chars(row['Info'])
        doc_str = remove_pl_chars(str(row['Dyżurny']))
        fill = True if row['_is_red'] else False
        if fill: pdf.set_fill_color(240, 240, 240)
        
        pdf.cell(40, 10, d_str, 1, 0, 'L', fill)
        pdf.cell(60, 10, day_str, 1, 0, 'L', fill)
        pdf.cell(80, 10, doc_str, 1, 1, 'L', fill)
    return pdf.output(dest='S').encode('latin-1', 'replace')

def create_daily_pdf_bytes(dataframe, title):
    pdf = PDF(orientation='L')
    pdf.add_page()
    pdf.set_font("Arial", size=8)
    safe_title = remove_pl_chars(title)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, safe_title, 0, 1, 'L')
    pdf.ln(5)
    
    cols = list(dataframe.columns)
    if "_is_red" in cols: cols.remove("_is_red")
    
    page_width = pdf.w - 20
    date_w = 20
    day_w = 25
    doc_w = (page_width - date_w - day_w) / (len(cols) - 2)
    
    pdf.set_font("Arial", 'B', 8)
    for col in cols:
        w = date_w if col == "Data" else (day_w if col == "Dzień" else doc_w)
        pdf.cell(w, 8, remove_pl_chars(col), 1, 0, 'C')
    pdf.ln()
    
    pdf.set_font("Arial", size=7)
    for _, row in dataframe.iterrows():
        fill = row.get('_is_red', False)
        if fill: pdf.set_fill_color(240, 240, 240)
        for col in cols:
            val = row[col]
            txt = val.strftime('%Y-%m-%d') if col == "Data" else remove_pl_chars(str(val))
            w = date_w if col == "Data" else (day_w if col == "Dzień" else doc_w)
            pdf.cell(w, 6, txt, 1, 0, 'C', fill)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- SILNIK GRAFIKU (CORE) ---

def _generate_single_schedule(dates, prefs_map, target_limits, last_duty_prev_period):
    schedule = {} 
    stats = {doc: {'Total': 0, "Poniedziałki": 0, "Wtorki/Środy": 0, "Czwartki": 0, "Piątki": 0, "Soboty": 0, "Niedziele": 0} for doc in ALL_DOCTORS}
    weekly_counts = {}
    debug_info = {}
    
    # 1. FIXED (PRIORYTET NADRZĘDNY)
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        day_prefs = prefs_map.get(d_str, {})
        assigned = None
        
        # Najpierw grupa Fixed
        for doc in FIXED_DOCTORS:
            if day_prefs.get(doc, {}).get('Status') == STATUS_FIXED:
                assigned = doc; break
        # Potem rotacyjni (jeśli ktoś z nich ma fixed)
        if not assigned:
            for doc in ROTATION_DOCTORS:
                if day_prefs.get(doc, {}).get('Status') == STATUS_FIXED:
                    assigned = doc; break
        
        if assigned:
            schedule[d_str] = assigned
            stats[assigned]['Total'] += 1
            stats[assigned][get_day_group(d)] += 1
            wk = get_week_key(d)
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][assigned] = weekly_counts[wk].get(assigned, 0) + 1

    # 2. ROTACJA
    days_to_fill = [d for d in dates if d.strftime('%Y-%m-%d') not in schedule]
    
    # Sortowanie: najpierw trudne dni (mało dostępnych lekarzy)
    def count_availability(day_obj):
        d_s = day_obj.strftime('%Y-%m-%d')
        return sum(1 for doc in ROTATION_DOCTORS if prefs_map.get(d_s, {}).get(doc, {}).get('Status') != STATUS_UNAVAILABLE)

    days_to_fill.sort(key=lambda x: (count_availability(x), random.random()))
    
    for d in days_to_fill:
        d_str = d.strftime('%Y-%m-%d')
        wk = get_week_key(d)
        group = get_day_group(d)
        candidates = []
        rej = {}
        prev = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        next_d = (d + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        prev_duty_doc = last_duty_prev_period if d == dates[0] else schedule.get(prev)

        for doc in ROTATION_DOCTORS:
            if stats[doc]['Total'] >= target_limits.get(doc, 0): rej[doc] = "Limit"; continue
            if prefs_map.get(d_str, {}).get(doc, {}).get('Status') == STATUS_UNAVAILABLE: rej[doc] = "ND"; continue
            if prev_duty_doc == doc: rej[doc] = "Po"; continue
            if schedule.get(next_d) == doc: rej[doc] = "Przed"; continue
            if weekly_counts.get(wk, {}).get(doc, 0) >= 2: rej[doc] = "Max2"; continue

            w = 10 if prefs_map.get(d_str, {}).get(doc, {}).get('Status') == STATUS_AVAILABLE else 1
            # Sortowanie: chcemy wyrównać grupę dni. Mniej ma w tej grupie -> wyżej na liście.
            candidates.append({'name': doc, 'w': w, 'gc': stats[doc][group], 'tc': stats[doc]['Total']})

        if candidates:
            # Wagi sortowania: Waga > Grupa Dni > Total > Random
            candidates.sort(key=lambda x: (-x['w'], x['gc'], x['tc'], random.random()))
            chosen = candidates[0]['name']
            schedule[d_str] = chosen
            stats[chosen]['Total'] += 1
            stats[chosen][group] += 1
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][chosen] = weekly_counts[wk].get(chosen, 0) + 1
        else:
            schedule[d_str] = "BRAK"
            debug_info[d_str] = rej

    return schedule, stats, debug_info

def generate_optimized(dates, df, limits, last_duty_prev, attempts=500):
    best_res = None
    best_score = -float('inf')
    prefs_map = {}
    if not df.empty:
        for r in df.to_dict('records'):
            if r['Data'] not in prefs_map: prefs_map[r['Data']] = {}
            prefs_map[r['Data']][r['Lekarz']] = {'Status': r['Status'], 'Przyczyna': r.get('Przyczyna', '')}

    for _ in range(attempts):
        sch, sts, dbg = _generate_single_schedule(dates, prefs_map, limits, last_duty_prev)
        
        # Scoring System
        score = 0
        filled_days = sum(1 for v in sch.values() if v != "BRAK")
        score += filled_days * 1_000_000 
        
        # Sprawiedliwość (Wariancja w grupach dni)
        total_variance_penalty = 0
        for g in DAY_GROUPS_LIST:
            cnts = [sts[d][g] for d in ROTATION_DOCTORS]
            if cnts:
                diff = max(cnts) - min(cnts)
                total_variance_penalty += diff * 1000 
        score -= total_variance_penalty
        
        # Preferencje
        pref_score = 0
        for d_str, doc in sch.items():
            if doc in ROTATION_DOCTORS and doc != "BRAK":
                s = prefs_map.get(d_str, {}).get(doc, {}).get('Status', STATUS_AVAILABLE)
                if s == STATUS_AVAILABLE: pref_score += 10
                elif s == STATUS_RELUCTANT: pref_score += 1
        score += pref_score

        if score > best_score:
            best_score = score
            best_res = (sch, sts, dbg, score)
    
    return best_res

# --- HARMONOGRAM DZIENNY ---

def generate_daily_work(dates, duty_schedule, preferences_df, last_duty_prev):
    daily_doctors = [d for d in ALL_DOCTORS if d != "Jakub Sz."]
    schedule_map = {d.strftime('%Y-%m-%d'): {doc: "" for doc in daily_doctors} for d in dates}
    prefs_lookup = {}
    if not preferences_df.empty:
        for r in preferences_df.to_dict('records'):
            d = r['Data']; doc = r['Lekarz']
            if d not in prefs_lookup: prefs_lookup[d] = {}
            prefs_lookup[d][doc] = {'Status': r['Status'], 'Przyczyna': r.get('Przyczyna', '')}

    def set_status(date_obj, doc, status): schedule_map[date_obj.strftime('%Y-%m-%d')][doc] = status
    def get_status(date_obj, doc): return schedule_map[date_obj.strftime('%Y-%m-%d')][doc]

    weeks = {}
    for d in dates:
        wk = get_week_key(d)
        if wk not in weeks: weeks[wk] = []
        weeks[wk].append(d)

    norma = 7 + (35/60)

    for wk, week_dates in weeks.items():
        daily_staff_count = {d.strftime('%Y-%m-%d'): 0 for d in week_dates}
        doc_shift_hours = {doc: 0.0 for doc in daily_doctors}

        for d in week_dates:
            d_s = d.strftime('%Y-%m-%d')
            prev_d_s = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            is_red = is_red_day(d)
            duty = duty_schedule.get(d_s)
            duty_prev = last_duty_prev if d == dates[0] else duty_schedule.get(prev_d_s)

            for doc in daily_doctors:
                user_prefs = prefs_lookup.get(d_s, {}).get(doc, {})
                status_pref = user_prefs.get('Status')
                reason = user_prefs.get('Przyczyna')
                
                if status_pref == STATUS_UNAVAILABLE and reason in ["Urlop", "Kurs"]: set_status(d, doc, reason)
                elif duty == doc: 
                    set_status(d, doc, "DYŻUR 24h")
                    doc_shift_hours[doc] += 24.0
                elif duty_prev == doc: set_status(d, doc, "ZEJŚCIE")
                elif is_red: set_status(d, doc, "Wolne")
                elif doc in SATURDAY_RULE_DOCTORS and d.weekday() == 0: 
                    last_sat = d - datetime.timedelta(days=2)
                    if duty_schedule.get(last_sat.strftime('%Y-%m-%d')) == doc: set_status(d, doc, "Wolne (za sobotę)")
                    else: set_status(d, doc, "TBD")
                else: set_status(d, doc, "TBD")

        for d in week_dates:
            count = sum(1 for doc in daily_doctors if get_status(d, doc) == "TBD")
            daily_staff_count[d.strftime('%Y-%m-%d')] = count

        for doc in NO_OPTOUT_DOCTORS:
            if doc not in daily_doctors: continue
            remaining = 48.0 - doc_shift_hours[doc]
            max_days = int(remaining // norma)
            candidates = [d for d in week_dates if get_status(d, doc) == "TBD"]
            if len(candidates) <= max_days:
                for d in candidates: set_status(d, doc, "7:30 - 15:05")
            else:
                candidates.sort(key=lambda x: daily_staff_count[x.strftime('%Y-%m-%d')], reverse=True)
                num_to_drop = len(candidates) - max_days
                for d in candidates[:num_to_drop]:
                    set_status(d, doc, "Wolne (48h)"); daily_staff_count[d.strftime('%Y-%m-%d')] -= 1
                for d in candidates[num_to_drop:]: set_status(d, doc, "7:30 - 15:05")

        for doc in daily_doctors:
            for d in week_dates:
                if get_status(d, doc) == "TBD": set_status(d, doc, "7:30 - 15:05")

    final_data = []
    for d in dates:
        row = {"Data": d, "Dzień": get_day_description(d), "_is_red": is_red_day(d)}
        for doc in daily_doctors: row[doc] = schedule_map[d.strftime('%Y-%m-%d')][doc]
        final_data.append(row)
    return pd.DataFrame(final_data)

# --- UI ---
st.set_page_config(page_title="Grafik Urologia", layout="wide", page_icon="🏥")
st.title("🏥 Grafik Dyżurowy - Urologia")

with st.sidebar:
    st.header("Ustawienia")
    periods = ["Styczeń - Luty", "Marzec - Kwiecień", "Maj - Czerwiec", "Lipiec - Sierpień", "Wrzesień - Październik", "Listopad - Grudzień"]
    today = datetime.date.today()
    default_idx = (today.month - 1) // 2
    sel_period_name = st.selectbox("Okres", periods, index=default_idx)
    sel_year = st.number_input("Rok", 2025, 2030, today.year)
    start_m = {"Styczeń - Luty": 1, "Marzec - Kwiecień": 3, "Maj - Czerwiec": 5, "Lipiec - Sierpień": 7, "Wrzesień - Październik": 9, "Listopad - Grudzień": 11}[sel_period_name]
    
    p_start, p_day = get_settlement_period_info(sel_year, start_m)
    st.info(f"Start: {p_start} ({p_day}).")
    attempts_count = st.slider("Próby AI", 100, 1000, 300)

with st.expander("ℹ️ Instrukcja obsługi i zasady (Kliknij, aby zwinąć)", expanded=True):
    st.markdown(f"""
    ### Witaj w systemie planowania pracy Oddziału Urologii!
    #### 👨‍⚕️ Jak korzystać?
    **KROK 1: Zakładka '📝 Dostępność'**
    1. Wybierz swoje nazwisko.
    2. **Lekarze 'Fixed' ({', '.join(FIXED_DOCTORS)}):** Dodaj tylko dni dyżurowe (+).
    3. **Lekarze 'Rotacyjni' ({', '.join(ROTATION_DOCTORS)}):** Wypełnij kalendarz. Zaznacz 'Urlop/Kurs' jeśli dotyczy.
    
    **KROK 2: Zakładka '🧮 Grafik'**
    1. Wybierz dyżurnego z dnia poprzedniego.
    2. Zweryfikuj limity.
    3. Kliknij `🚀 GENERUJ`.
    """)

tab1, tab2 = st.tabs(["📝 Dostępność", "🧮 Grafik"])

with tab1:
    st.subheader(f"Dostępność: {sel_period_name} {sel_year}")
    current_user = st.selectbox("Lekarz:", ALL_DOCTORS, index=2)
    dates = get_period_dates(sel_year, start_m)
    df_db = load_data()
    is_fixed_mode = current_user in FIXED_DOCTORS
    
    # Uniwersalna konfiguracja edytora
    if is_fixed_mode:
        st.info("Tryb Fixed. Dodaj tylko dni dyżurowe.")
        # Filtruj dane
        mask_user = (df_db['Lekarz'] == current_user)
        clean_data = []
        if not df_db.empty:
            for _, r in df_db[mask_user].iterrows():
                if r['Status'] == STATUS_FIXED:
                    try:
                        d = pd.to_datetime(r['Data']).date()
                        if d in dates: clean_data.append({"Data": d, "Status": STATUS_FIXED})
                    except: pass
        
        # Przygotuj DataFrame
        data_to_edit = pd.DataFrame(clean_data if clean_data else [], columns=["Data", "Status"])
        column_conf = {
            "Data": st.column_config.DateColumn(format="DD.MM.YYYY", required=True),
            "Status": st.column_config.SelectboxColumn(disabled=True, default=STATUS_FIXED, options=[STATUS_FIXED])
        }
        num_rows_mode = "dynamic"
    else:
        # Rotation mode
        data_rows = []
        for d in dates:
            d_s = d.strftime('%Y-%m-%d')
            s = STATUS_AVAILABLE; r_val = ""
            if not df_db.empty:
                e = df_db[(df_db['Lekarz'] == current_user) & (df_db['Data'] == d_s)]
                if not e.empty: s = e.iloc[0]['Status']; r_val = e.iloc[0].get('Przyczyna', '')
            data_rows.append({"Data": d, "Info": get_day_description(d), "Status": s, "Przyczyna": r_val})
        
        data_to_edit = pd.DataFrame(data_rows)
        column_conf = {
            "Data": st.column_config.DateColumn(disabled=True, format="DD.MM.YYYY"),
            "Info": st.column_config.TextColumn(disabled=True),
            "Status": st.column_config.SelectboxColumn(options=[STATUS_AVAILABLE, STATUS_RELUCTANT, STATUS_FIXED, STATUS_UNAVAILABLE], required=True),
            "Przyczyna": st.column_config.SelectboxColumn(options=REASONS)
        }
        num_rows_mode = "fixed"

    # Wyświetl edytor
    edited = st.data_editor(data_to_edit, column_config=column_conf, num_rows=num_rows_mode, use_container_width=True, hide_index=True)

    if st.button(f"💾 Zapisz ({current_user})", type="primary"):
        with st.spinner("Zapisywanie..."):
            period_strs = [d.strftime('%Y-%m-%d') for d in dates]
            new_records = []
            
            for _, r in edited.iterrows():
                try:
                    d_val = pd.to_datetime(r['Data']).strftime('%Y-%m-%d')
                    if is_fixed_mode:
                        # W trybie fixed tylko valid daty z okresu
                        if d_val in period_strs: 
                            new_records.append({"Data": d_val, "Lekarz": current_user, "Status": STATUS_FIXED, "Przyczyna": ""})
                    else:
                        # W trybie rotacyjnym wszystkie daty + czyszczenie przyczyny
                        final_reason = r['Przyczyna'] if r['Status'] == STATUS_UNAVAILABLE else ""
                        new_records.append({"Data": d_val, "Lekarz": current_user, "Status": r['Status'], "Przyczyna": final_reason})
                except: continue
            
            new_df = pd.DataFrame(new_records)
            
            # Łączenie z bazą
            if not df_db.empty:
                # Usuń stare wpisy usera w tym okresie
                mask_rm = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(period_strs))
                df_clean = df_db[~mask_rm]
                final_df = pd.concat([df_clean, new_df], ignore_index=True)
            else:
                final_df = new_df
                
            if save_data(final_df): st.success("Zapisano!"); load_data.clear()

with tab2:
    st.header("Generator")
    all_prefs = load_data()
    dates_gen = get_period_dates(sel_year, start_m)
    
    prev_day_date = dates_gen[0] - datetime.timedelta(days=1)
    last_duty_prev = st.selectbox(f"Kto dyżurował {prev_day_date.strftime('%d.%m.%Y')}?", ["Nikt"] + ALL_DOCTORS, index=0)
    real_last_duty = None if last_duty_prev == "Nikt" else last_duty_prev
    
    # Licznik fixed
    fixed_counts = {doc: 0 for doc in ALL_DOCTORS}
    if not all_prefs.empty:
        d_strs = [d.strftime('%Y-%m-%d') for d in dates_gen]
        p_data = all_prefs[all_prefs['Data'].isin(d_strs)]
        for doc in ALL_DOCTORS:
            fixed_counts[doc] = len(p_data[(p_data['Lekarz'] == doc) & (p_data['Status'] == STATUS_FIXED)])

    total_days = len(dates_gen)
    
    # 1. FIXED
    st.subheader("1. Dyżury Ustalone (Fixed)")
    fixed_df = pd.DataFrame([{"Lekarz": d, "Liczba Dyżurów": fixed_counts[d]} for d in FIXED_DOCTORS])
    ed_fixed = st.data_editor(fixed_df, column_config={"Lekarz": st.column_config.TextColumn(disabled=True)}, hide_index=True, use_container_width=True)
    
    sum_fixed = ed_fixed["Liczba Dyżurów"].sum() + sum(fixed_counts[d] for d in ROTATION_DOCTORS)
    pool = total_days - sum_fixed
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Wszystkie dni", total_days)
    col2.metric("Zajęte (Fixed)", sum_fixed)
    col3.metric("Dla Rotacji", max(0, pool))
    
    # 2. ROTACJA
    st.subheader("2. Limity Rotacyjne")
    ts = len(ROTATION_DOCTORS)
    base = max(0, pool) // ts if ts else 0
    rot_df = pd.DataFrame([{"Lekarz": d, "Limit": base} for d in ROTATION_DOCTORS])
    ed_rot = st.data_editor(rot_df, column_config={"Limit": st.column_config.NumberColumn(step=1)}, hide_index=True, use_container_width=True)
    
    planned = ed_rot["Limit"].sum() + sum_fixed
    
    if planned == total_days:
        st.success("Bilans zgodny.")
        if st.button("🚀 GENERUJ GRAFIKI", type="primary"):
            limits = {}
            for _, r in ed_rot.iterrows(): limits[r['Lekarz']] = r['Limit']
            for _, r in ed_fixed.iterrows(): limits[r['Lekarz']] = r['Liczba Dyżurów']
            
            with st.spinner(f"Optymalizacja (analiza {attempts_count} wariantów)..."):
                sch, stats, dbg, sc = generate_optimized(dates_gen, all_prefs, limits, real_last_duty, attempts_count)
            
            # WYNIKI
            res, fails = [], []
            for d in dates_gen:
                d_s = d.strftime('%Y-%m-%d')
                ass = sch.get(d_s, "BRAK")
                res.append({"Data": d, "Info": get_day_description(d), "Dyżurny": ass, "_is_red": is_red_day(d)})
                if ass == "BRAK":
                    reason = ", ".join([f"**{k}**: {v}" for k,v in dbg[d_s].items()]) if d_s in dbg else "Brak chętnych"
                    fails.append(f"🔴 **{d.strftime('%d.%m')}:** {reason}")

            df_res = pd.DataFrame(res)
            if fails:
                st.error("⚠️ Błędy obsady:")
                for f in fails: st.write(f)
            else: st.balloons()
            
            # Styles
            def style_dyzur(r):
                if r['Dyżurny'] == "BRAK": return ['background-color: #ffcccc; color: red; font-weight: bold'] * len(r)
                return ['color: #D81B60; font-weight: bold'] * len(r) if r['_is_red'] else [''] * len(r)

            st.dataframe(df_res.style.apply(style_dyzur, axis=1).format({"Data": lambda t: t.strftime("%Y-%m-%d")}), use_container_width=True, height=500, column_config={"_is_red": None})
            
            # PDF Dyżury
            try:
                pdf = create_pdf_bytes(df_res, f"Grafik {sel_period_name}")
                st.download_button("📥 PDF (Dyżury)", pdf, "grafik.pdf", "application/pdf")
            except: pass

            # STATYSTYKI
            st.write("---")
            s_rows = []
            for d in ROTATION_DOCTORS:
                row = {"Lekarz": d, "Cel": limits.get(d,0), "Wynik": int(stats[d]['Total'])}
                for k,v in stats[d].items(): 
                    if k!='Total': row[k] = int(v)
                s_rows.append(row)
            st.dataframe(pd.DataFrame(s_rows).fillna("-"), hide_index=True)

            # HARMONOGRAM PRACY
            st.markdown("---")
            st.markdown(f"### 🏢 Tabela 2: Harmonogram Pracy (Bez {FIXED_DOCTORS[0]})")
            df_daily = generate_daily_work(dates_gen, sch, all_prefs, real_last_duty)
            
            def style_daily(val):
                if val == "ZEJŚCIE": return 'background-color: #e0e0e0; color: #555'
                if "DYŻUR" in str(val): return 'background-color: #d1ecf1; color: #0c5460; font-weight: bold'
                if "Wolne (48h)" in str(val): return 'background-color: #f8d7da; color: #721c24'
                if val in ["Wolne", "Urlop", "Kurs"]: return 'color: #D81B60'
                return ''

            st.dataframe(df_daily.style.applymap(style_daily).format({"Data": lambda t: t.strftime("%Y-%m-%d")}), use_container_width=True, height=600, column_config={"_is_red": None})
            
            try:
                pdf_daily = create_daily_pdf_bytes(df_daily.drop(columns=["_is_red"]), f"Harmonogram {sel_period_name}")
                st.download_button("📥 PDF (Harmonogram)", pdf_daily, "harmonogram.pdf", "application/pdf")
            except Exception as e: st.error(f"Błąd PDF: {e}")

    else:
        diff = total_days - planned
        st.warning(f"⚠️ Bilans się nie zgadza! Suma ({planned}) < Dni ({total_days}). Brakuje: {diff}. Dodaj je w tabeli Rotacyjnej.")
