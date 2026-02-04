import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from github import Github
from io import StringIO
from fpdf import FPDF # Biblioteka do PDF

# --- KONFIGURACJA ZESPOŁU ---

# Grupa PRIORYTETOWA (Fixed) - Ich "Sztywny Dyżur" nadpisuje wszystko inne
FIXED_DOCTORS = [
    "Jakub Sz.", 
    "Gerard", 
    "Tomasz", 
    "Rafał", 
    "Marcin", 
    "Weronika",
    "Daniel"
]

# Grupa ROTACYJNA - Biorą udział w losowaniu, ich "Fixed" jest ważny tylko gdy grupa wyżej nie zajęła dnia
ROTATION_DOCTORS = [
    "Jędrzej", 
    "Filip", 
    "Ihab", 
    "Kacper", 
    "Jakub", 
    "Tymoteusz"
]

ALL_DOCTORS = FIXED_DOCTORS + ROTATION_DOCTORS

# Statusy
STATUS_AVAILABLE = "Chcę dyżur (Dostępny)"
STATUS_RELUCTANT = "Mogę (Niechętnie)"
STATUS_UNAVAILABLE = "Niedostępny"
STATUS_FIXED = "Sztywny Dyżur (Już ustalony)"

DATA_FILE = "data.csv"

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
    for k, v in replacements.items():
        text = text.replace(k, v)
    try:
        return text.encode('latin-1', 'replace').decode('latin-1')
    except:
        return "Tekst nieczytelny"

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
        if row['_is_red']:
            pdf.set_fill_color(240, 240, 240)
            fill = True
        else:
            fill = False
        pdf.cell(40, 10, d_str, 1, 0, 'L', fill)
        pdf.cell(60, 10, day_str, 1, 0, 'L', fill)
        pdf.cell(80, 10, doc_str, 1, 1, 'L', fill)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- CACHE I OPTYMALIZACJA ---

@st.cache_data(ttl=3600)
def get_polish_holidays(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) // 7
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
    if date_obj in holidays:
        return f"🔴 {day_name} ({holidays[date_obj]})"
    elif date_obj.weekday() >= 5:
        return f"🔴 {day_name}"
    return day_name

# --- OBSŁUGA GITHUBA ---

@st.cache_resource
def get_repo():
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        user = g.get_user()
        for repo in user.get_repos():
             if any(x in repo.name.lower() for x in ["grafik", "urologia", "dyzury"]):
                 return repo
        return user.get_repos()[0]
    except Exception as e:
        st.error(f"Błąd GitHub: {e}")
        return None

@st.cache_data(ttl=60)
def load_data():
    repo = get_repo()
    if not repo: return pd.DataFrame(columns=["Data", "Lekarz", "Status"])
    try:
        contents = repo.get_contents(DATA_FILE)
        csv_content = contents.decoded_content.decode("utf-8")
        df = pd.read_csv(StringIO(csv_content))
        df['Data'] = df['Data'].astype(str)
        return df
    except:
        return pd.DataFrame(columns=["Data", "Lekarz", "Status"])

def save_data(df):
    repo = get_repo()
    if not repo: return False
    csv_content = df.to_csv(index=False)
    try:
        contents = repo.get_contents(DATA_FILE)
        repo.update_file(contents.path, "Update data", csv_content, contents.sha)
        return True
    except:
        try:
            repo.create_file(DATA_FILE, "Init data", csv_content)
            return True
        except: return False

# --- LOGIKA KALENDARZA ---

def get_settlement_period_info(year, month):
    start_month = month if month % 2 != 0 else month - 1
    start_date = datetime.date(year, start_month, 1)
    day_names_pl = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
    return start_date, day_names_pl[start_date.weekday()]

def get_period_dates(year, start_month):
    dates = []
    for i in range(2):
        curr_m = start_month + i
        if curr_m <= 12:
            num_days = calendar.monthrange(year, curr_m)[1]
            dates.extend([datetime.date(year, curr_m, d) for d in range(1, num_days + 1)])
    return dates

def get_week_key(date_obj):
    period_start_date, _ = get_settlement_period_info(date_obj.year, date_obj.month)
    days_diff = (date_obj - period_start_date).days
    week_index = days_diff // 7
    return f"{date_obj.year}_M{period_start_date.month}_W{week_index}"

def get_day_group(date_obj):
    wd = date_obj.weekday()
    if wd == 0: return "Poniedziałki"
    if wd in [1, 2]: return "Wtorki/Środy"
    if wd == 3: return "Czwartki"
    if wd == 4: return "Piątki"
    if wd == 5: return "Soboty"
    if wd == 6: return "Niedziele"
    return "Inne"

# --- SILNIK GRAFIKU (CORE) ---

def _generate_single_schedule(dates, prefs_map, target_limits):
    schedule = {} 
    stats = {doc: {'Total': 0, "Poniedziałki": 0, "Wtorki/Środy": 0, "Czwartki": 0, "Piątki": 0, "Soboty": 0, "Niedziele": 0} for doc in ALL_DOCTORS}
    weekly_counts = {}
    debug_info = {}
    
    # 1. SZTYWNE DYŻURY (Fixed)
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        day_prefs = prefs_map.get(d_str, {})
        assigned_fixed = None
        
        # Priorytet dla Fixed
        for doc in FIXED_DOCTORS:
            if day_prefs.get(doc) == STATUS_FIXED:
                assigned_fixed = doc
                break
        if not assigned_fixed:
            for doc in ROTATION_DOCTORS:
                if day_prefs.get(doc) == STATUS_FIXED:
                    assigned_fixed = doc
                    break
        
        if assigned_fixed:
            schedule[d_str] = assigned_fixed
            stats[assigned_fixed]['Total'] += 1
            stats[assigned_fixed][get_day_group(d)] += 1
            wk = get_week_key(d)
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][assigned_fixed] = weekly_counts[wk].get(assigned_fixed, 0) + 1

    # 2. ROTACJA
    days_to_fill = [d for d in dates if d.strftime('%Y-%m-%d') not in schedule]
    
    # Heurystyka: najpierw dni trudne (mało dostępnych)
    def count_availability(day_obj):
        d_s = day_obj.strftime('%Y-%m-%d')
        return sum(1 for doc in ROTATION_DOCTORS if prefs_map.get(d_s, {}).get(doc) != STATUS_UNAVAILABLE)

    days_to_fill.sort(key=lambda x: (count_availability(x), random.random()))
    
    for d in days_to_fill:
        d_str = d.strftime('%Y-%m-%d')
        wk = get_week_key(d)
        group = get_day_group(d)
        candidates = []
        daily_rejections = {}

        prev_day = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        next_day = (d + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        for doc in ROTATION_DOCTORS:
            if stats[doc]['Total'] >= target_limits.get(doc, 0):
                daily_rejections[doc] = f"Limit({stats[doc]['Total']})"
                continue
            
            status = prefs_map.get(d_str, {}).get(doc, STATUS_AVAILABLE)
            if status == STATUS_UNAVAILABLE: 
                daily_rejections[doc] = "Niedostępny"
                continue
            
            if schedule.get(prev_day) == doc: 
                daily_rejections[doc] = "Po dyżurze"
                continue
            
            if schedule.get(next_day) == doc: 
                daily_rejections[doc] = "Przed dyżurem"
                continue
            
            if weekly_counts.get(wk, {}).get(doc, 0) >= 2: 
                daily_rejections[doc] = "Limit tyg."
                continue

            weight = 10 if status == STATUS_AVAILABLE else 1
            candidates.append({
                'name': doc, 'weight': weight, 'group_count': stats[doc][group], 'total_count': stats[doc]['Total']
            })

        if candidates:
            candidates.sort(key=lambda x: (-x['weight'], x['group_count'], x['total_count'], random.random()))
            chosen = candidates[0]['name']
            schedule[d_str] = chosen
            stats[chosen]['Total'] += 1
            stats[chosen][group] += 1
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][chosen] = weekly_counts[wk].get(chosen, 0) + 1
        else:
            schedule[d_str] = "BRAK"
            debug_info[d_str] = daily_rejections

    return schedule, stats, debug_info

def generate_optimized_schedule(dates, preferences_df, target_limits, attempts=50):
    best_result = None
    best_score = -float('inf')
    
    prefs_map = {}
    if not preferences_df.empty:
        for row in preferences_df.to_dict('records'):
            d_str = str(row['Data'])
            if d_str not in prefs_map: prefs_map[d_str] = {}
            prefs_map[d_str][row['Lekarz']] = row['Status']

    for _ in range(attempts):
        sch, sts, dbg = _generate_single_schedule(dates, prefs_map, target_limits)
        
        score = 0
        filled_days = sum(1 for v in sch.values() if v != "BRAK")
        score += filled_days * 1000 
        
        for d_str, doc in sch.items():
            if doc in ROTATION_DOCTORS and doc != "BRAK":
                status = prefs_map.get(d_str, {}).get(doc, STATUS_AVAILABLE)
                if status == STATUS_AVAILABLE: score += 10
                elif status == STATUS_RELUCTANT: score += 1
        
        for group in ["Piątki", "Soboty", "Niedziele"]:
            counts = [sts[doc][group] for doc in ROTATION_DOCTORS]
            if counts: score -= (max(counts) - min(counts)) * 5

        if score > best_score:
            best_score = score
            best_result = (sch, sts, dbg, score)
    
    return best_result

# --- UI ---
st.set_page_config(page_title="Grafik Urologia", layout="wide", page_icon="🏥")
st.title("🏥 Grafik Dyżurowy - Urologia")

with st.sidebar:
    st.header("Ustawienia")
    periods = ["Styczeń - Luty", "Marzec - Kwiecień", "Maj - Czerwiec", "Lipiec - Sierpień", "Wrzesień - Październik", "Listopad - Grudzień"]
    today = datetime.date.today()
    default_idx = (today.month - 1) // 2
    sel_period_name = st.selectbox("Okres Rozliczeniowy", periods, index=default_idx)
    sel_year = st.number_input("Rok", 2025, 2030, today.year)
    start_m = {"Styczeń - Luty": 1, "Marzec - Kwiecień": 3, "Maj - Czerwiec": 5, "Lipiec - Sierpień": 7, "Wrzesień - Październik": 9, "Listopad - Grudzień": 11}[sel_period_name]
    
    p_start, p_day = get_settlement_period_info(sel_year, start_m)
    st.info(f"Początek okresu: {p_start} ({p_day}).")
    attempts_count = st.slider("Liczba prób (AI)", 10, 200, 50)

tab1, tab2 = st.tabs(["📝 Dostępność", "🧮 Grafik"])

# --- TAB 1 ---
with tab1:
    st.subheader(f"Dostępność: {sel_period_name} {sel_year}")
    current_user = st.selectbox("Lekarz:", ALL_DOCTORS, index=2)
    dates = get_period_dates(sel_year, start_m)
    df_db = load_data()
    is_fixed_mode = current_user in FIXED_DOCTORS
    
    if is_fixed_mode:
        st.info("👋 Tryb 'Fixed' (Nadrzędny). Kliknij '+', aby dodać dzień.")
        mask_user = (df_db['Lekarz'] == current_user)
        clean_data = []
        if not df_db.empty:
            user_entries = df_db[mask_user]
            for _, r in user_entries.iterrows():
                if r['Status'] == STATUS_FIXED:
                    try:
                        d_obj = pd.to_datetime(r['Data']).date()
                        if d_obj in dates: clean_data.append({"Data": d_obj, "Status": STATUS_FIXED})
                    except: pass
        
        editor_df = pd.DataFrame(clean_data if clean_data else [], columns=["Data", "Status"])
        edited_jakub = st.data_editor(
            editor_df,
            column_config={"Data": st.column_config.DateColumn("Data Dyżuru", format="DD.MM.YYYY", required=True), "Status": st.column_config.SelectboxColumn(disabled=True, default=STATUS_FIXED, options=[STATUS_FIXED])},
            num_rows="dynamic", use_container_width=True, hide_index=True
        )
        
        if st.button(f"💾 Zapisz ({current_user})", type="primary"):
            with st.spinner("Zapisywanie..."):
                period_strs = [d.strftime('%Y-%m-%d') for d in dates]
                new_rows = []
                for _, row in edited_jakub.iterrows():
                    try:
                        d_val = pd.to_datetime(row['Data']).strftime('%Y-%m-%d')
                        if d_val in period_strs: new_rows.append({"Data": d_val, "Lekarz": current_user, "Status": STATUS_FIXED})
                    except: continue
                final_new = pd.DataFrame(new_rows)
                if df_db.empty: final_db = final_new
                else:
                    mask_remove = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(period_strs))
                    df_cleaned = df_db[~mask_remove]
                    final_db = pd.concat([df_cleaned, final_new], ignore_index=True)
                if save_data(final_db): 
                    st.success("Zapisano!")
                    load_data.clear()
    else:
        t_data = []
        for d in dates:
            d_str = d.strftime('%Y-%m-%d')
            status = STATUS_AVAILABLE
            if not df_db.empty:
                entry = df_db[(df_db['Lekarz'] == current_user) & (df_db['Data'] == d_str)]
                if not entry.empty: status = entry.iloc[0]['Status']
            day_desc = get_day_description(d)
            m_name = "Msc 1" if d.month == start_m else "Msc 2"
            t_data.append({"Data": d, "Miesiąc": m_name, "Info": day_desc, "Status": status})
        
        edited_df = st.data_editor(pd.DataFrame(t_data), column_config={"Data": st.column_config.DateColumn(disabled=True, format="DD.MM.YYYY"), "Miesiąc": st.column_config.TextColumn(disabled=True), "Info": st.column_config.TextColumn(disabled=True, width="medium"), "Status": st.column_config.SelectboxColumn("Decyzja", options=[STATUS_AVAILABLE, STATUS_RELUCTANT, STATUS_FIXED, STATUS_UNAVAILABLE], required=True)}, hide_index=True, height=500, use_container_width=True)
        
        if st.button(f"💾 Zapisz ({current_user})", type="primary"):
            with st.spinner("Zapisywanie..."):
                period_strs = [d.strftime('%Y-%m-%d') for d in dates]
                new_rows = []
                for _, row in edited_df.iterrows():
                    try:
                        d_val = pd.to_datetime(row['Data']).strftime('%Y-%m-%d')
                        new_rows.append({"Data": d_val, "Lekarz": current_user, "Status": row['Status']})
                    except: continue
                final_new = pd.DataFrame(new_rows)
                if df_db.empty: final_db = final_new
                else:
                    mask_remove = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(period_strs))
                    df_cleaned = df_db[~mask_remove]
                    final_db = pd.concat([df_cleaned, final_new], ignore_index=True)
                if save_data(final_db): 
                    st.success("Zapisano!")
                    load_data.clear()

# --- TAB 2: GENERATOR ---
with tab2:
    st.header("Generator Grafiku")
    all_prefs = load_data()
    dates_gen = get_period_dates(sel_year, start_m)
    
    fixed_counts_map = {doc: 0 for doc in ALL_DOCTORS}
    if not all_prefs.empty:
        d_strs = [d.strftime('%Y-%m-%d') for d in dates_gen]
        period_data = all_prefs[all_prefs['Data'].isin(d_strs)]
        for doc in ALL_DOCTORS:
            cnt = len(period_data[(period_data['Lekarz'] == doc) & (period_data['Status'] == STATUS_FIXED)])
            fixed_counts_map[doc] = cnt

    total_days = len(dates_gen)
    
    st.subheader("Dyżury Ustalone (Fixed)")
    fixed_table_data = []
    # POPRAWKA: Tylko jedna kolumna "Liczba Dyżurów" dla lekarzy Fixed
    for doc in FIXED_DOCTORS:
        fixed_table_data.append({"Lekarz": doc, "Liczba Dyżurów": fixed_counts_map[doc]})
    
    edited_fixed_table = st.data_editor(
        pd.DataFrame(fixed_table_data),
        column_config={
            "Lekarz": st.column_config.TextColumn(disabled=True),
            "Liczba Dyżurów": st.column_config.NumberColumn(min_value=0, max_value=31, step=1)
        },
        hide_index=True, 
        use_container_width=True
    )
    
    # Aktualizacja sumy
    sum_fixed_table = edited_fixed_table["Liczba Dyżurów"].sum()
    sum_fixed_rotational = sum(fixed_counts_map[d] for d in ROTATION_DOCTORS)
    total_consumed = sum_fixed_table + sum_fixed_rotational
    rem_days = total_days - total_consumed
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Dni w okresie", total_days)
    col2.metric("Zajęte (Fixed)", total_consumed)
    col3.metric("Do podziału", max(0, rem_days))
    
    st.subheader("Limity Rotacyjne")
    st.caption("Domyślnie dzielę dni równo. Jeśli zostaną resztki, musisz dodać je ręcznie wybranym lekarzom, aż bilans się zgodzi.")
    
    team_size = len(ROTATION_DOCTORS)
    # POPRAWKA: Równy podział w dół, bez zgadywania kto dostaje +1
    base = max(0, rem_days) // team_size if team_size else 0
    
    lim_data = []
    for i, doc in enumerate(ROTATION_DOCTORS):
        sugg = base 
        existing = fixed_counts_map[doc]
        lim_data.append({"Lekarz": doc, "Limit": sugg + existing})
        
    edited_limits = st.data_editor(pd.DataFrame(lim_data), column_config={"Limit": st.column_config.NumberColumn(min_value=0, max_value=31, step=1)}, hide_index=True, use_container_width=True)
    
    current_rot_sum = edited_limits["Limit"].sum()
    total_planned = current_rot_sum + sum_fixed_table
    
    if total_planned == total_days:
        st.success("Bilans się zgadza.")
        if st.button("🚀 GENERUJ", type="primary"):
            targets = {}
            for _, r in edited_limits.iterrows(): targets[r['Lekarz']] = r['Limit']
            # POPRAWKA: Pobieramy cel z nowej kolumny "Liczba Dyżurów"
            for _, r in edited_fixed_table.iterrows(): targets[r['Lekarz']] = r['Liczba Dyżurów']
            
            with st.spinner(f"Symulacja {attempts_count} wariantów..."):
                sch, stats, dbg, score = generate_optimized_schedule(dates_gen, all_prefs, targets, attempts_count)
            
            res_rows = []
            fails = []
            for d in dates_gen:
                is_free = is_red_day(d)
                d_s = d.strftime('%Y-%m-%d')
                assigned = sch.get(d_s, "BRAK")
                res_rows.append({
                    "Data": d, "Info": get_day_description(d), 
                    "Dyżurny": assigned, "_is_red": is_free
                })
                if assigned == "BRAK":
                    if d_s in dbg and dbg[d_s]:
                        reason_str = ", ".join([f"**{k}**: {v}" for k,v in dbg[d_s].items()])
                        fails.append(f"🔴 **{d.strftime('%d.%m')} ({get_day_description(d)}):** {reason_str}")
                    else:
                        fails.append(f"🔴 **{d.strftime('%d.%m')}:** Brak dostępnych lekarzy rotacyjnych.")

            df_res = pd.DataFrame(res_rows)
            
            if fails:
                st.error("⚠️ UWAGA! Nie udało się obsadzić poniższych dni:")
                for f in fails: st.write(f)
                st.divider()
            else:
                st.balloons()
            
            try:
                pdf_bytes = create_pdf_bytes(df_res, f"Grafik {sel_period_name} {sel_year}")
                st.download_button(label="📥 Pobierz Grafik jako PDF", data=pdf_bytes, file_name=f"grafik_{sel_period_name}_{sel_year}.pdf", mime="application/pdf")
            except Exception as e: st.error(f"Błąd PDF: {e}")

            def style_rows(row):
                if row['Dyżurny'] == "BRAK": return ['background-color: #ffcccc; color: red; font-weight: bold'] * len(row)
                return ['color: #D81B60; font-weight: bold'] * len(row) if row['_is_red'] else [''] * len(row)

            st.dataframe(df_res.style.apply(style_rows, axis=1).format({"Data": lambda t: t.strftime("%Y-%m-%d")}), use_container_width=True, height=600, column_config={"_is_red": None})
            
            st.write("---")
            s_rows = []
            for d in ALL_DOCTORS:
                goal = targets.get(d, 0)
                row = {
                    "Lekarz": d, 
                    "Cel": goal, 
                    "Wynik": stats[d]['Total']
                }
                if d in ROTATION_DOCTORS:
                    row.update({k: v for k, v in stats[d].items() if k != 'Total'})
                s_rows.append(row)

            st.dataframe(pd.DataFrame(s_rows).fillna(""), hide_index=True)
            
    else:
        diff = total_days - total_planned
        st.warning(f"⚠️ Bilans się nie zgadza! Suma dyżurów ({total_planned}) jest mniejsza od liczby dni ({total_days}). \n\n 👉 **Musisz dodać jeszcze {diff} dyżurów w tabeli powyżej.**")
