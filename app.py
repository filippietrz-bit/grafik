import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from github import Github
from io import StringIO

# --- KONFIGURACJA ZESPOŁU ---

# Grupa 1: Lekarze z "grafikiem sztywnym" (wybierają konkretne dni, nie biorą udziału w losowaniu reszty)
FIXED_DOCTORS = [
    "Jakub Sz.", 
    "Gerard", 
    "Tomasz", 
    "Rafał", 
    "Marcin", 
    "Daniel",
    "Weronika"
]

# Grupa 2: Lekarze "rotacyjni" (biorą udział w losowaniu pozostałych dni)
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

# Nazwa pliku w repozytorium
DATA_FILE = "data.csv"

# --- KALENDARZ POLSKICH ŚWIĄT ---

def get_easter_date(year):
    """Oblicza datę Wielkanocy."""
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
    return datetime.date(year, month, day)

def get_polish_holidays(year):
    """Zwraca słownik świąt w Polsce."""
    easter = get_easter_date(year)
    easter_monday = easter + datetime.timedelta(days=1)
    corpus_christi = easter + datetime.timedelta(days=60)
    
    holidays = {
        datetime.date(year, 1, 1): "Nowy Rok",
        datetime.date(year, 1, 6): "Trzech Króli",
        easter: "Wielkanoc",
        easter_monday: "Poniedziałek Wielkanocny",
        datetime.date(year, 5, 1): "Święto Pracy",
        datetime.date(year, 5, 3): "Święto Konstytucji 3 Maja",
        corpus_christi: "Boże Ciało",
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
    else:
        return day_name

# --- OBSŁUGA GITHUBA ---

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
        repo.update_file(contents.path, "Update", csv_content, contents.sha)
        return True
    except:
        try:
            repo.create_file(DATA_FILE, "Init", csv_content)
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
    num_days_1 = calendar.monthrange(year, start_month)[1]
    dates.extend([datetime.date(year, start_month, d) for d in range(1, num_days_1 + 1)])
    next_month = start_month + 1
    if next_month <= 12:
        num_days_2 = calendar.monthrange(year, next_month)[1]
        dates.extend([datetime.date(year, next_month, d) for d in range(1, num_days_2 + 1)])
    return dates

def get_week_key(date_obj):
    period_start_date, _ = get_settlement_period_info(date_obj.year, date_obj.month)
    days_diff = (date_obj - period_start_date).days
    week_index = days_diff // 7
    return f"{date_obj.year}_Okres{period_start_date.month}_Tydzien{week_index}"

def get_day_group(date_obj):
    wd = date_obj.weekday()
    if wd == 0: return "Poniedziałki"
    if wd in [1, 2]: return "Wtorki/Środy"
    if wd == 3: return "Czwartki"
    if wd == 4: return "Piątki"
    if wd == 5: return "Soboty"
    if wd == 6: return "Niedziele"
    return "Inne"

# --- GENERATOR ---

def generate_schedule(dates, preferences_df, target_limits):
    schedule = {} 
    stats = {doc: {'Total': 0, "Poniedziałki": 0, "Wtorki/Środy": 0, "Czwartki": 0, "Piątki": 0, "Soboty": 0, "Niedziele": 0} for doc in ALL_DOCTORS}
    weekly_counts = {}

    prefs_map = {}
    if not preferences_df.empty:
        for _, row in preferences_df.iterrows():
            d_str = str(row['Data'])
            if d_str not in prefs_map: prefs_map[d_str] = {}
            prefs_map[d_str][row['Lekarz']] = row['Status']

    # KROK 1: SZTYWNE DYŻURY (Wszystkich, ale głównie grupy FIXED_DOCTORS)
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        day_prefs = prefs_map.get(d_str, {})
        
        assigned_fixed = None
        
        # Priorytet dla grupy Fixed
        for doc in FIXED_DOCTORS:
            if day_prefs.get(doc) == STATUS_FIXED:
                assigned_fixed = doc
                break
        
        # Jeśli nikt z fixed nie ma, sprawdzamy rotacyjnych (też mogą mieć fixed)
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

    # KROK 2: Obsadzanie reszty dni (Tylko grupa ROTATION_DOCTORS)
    days_to_fill = [d for d in dates if d.strftime('%Y-%m-%d') not in schedule]
    random.shuffle(days_to_fill)
    
    for d in days_to_fill:
        d_str = d.strftime('%Y-%m-%d')
        wk = get_week_key(d)
        group = get_day_group(d)
        candidates = []

        prev_day = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        next_day = (d + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        for doc in ROTATION_DOCTORS:
            # 1. Limit globalny
            if stats[doc]['Total'] >= target_limits.get(doc, 0): continue
            
            # 2. Dostępność
            status = prefs_map.get(d_str, {}).get(doc, STATUS_AVAILABLE)
            if status == STATUS_UNAVAILABLE: continue
            
            # 3. Odpoczynek po dyżurze (wczoraj)
            if schedule.get(prev_day) == doc: continue
            
            # 4. Odpoczynek przed dyżurem (jutro - fixed)
            if schedule.get(next_day) == doc: continue
            
            # 5. Limit tygodniowy
            if weekly_counts.get(wk, {}).get(doc, 0) >= 2: continue

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

    return schedule, stats

# --- UI ---
st.set_page_config(page_title="Grafik Urologia", layout="wide")
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

tab1, tab2 = st.tabs(["📝 Zgłaszanie Dostępności", "🧮 Kalkulator i Grafik"])

# --- TAB 1 ---
with tab1:
    st.subheader(f"Dostępność: {sel_period_name} {sel_year}")
    current_user = st.selectbox("Lekarz:", ALL_DOCTORS, index=2) # Domyślnie Filip
    
    dates = get_period_dates(sel_year, start_m)
    df_db = load_data()
    
    # --- LOGIKA DLA GRUPY FIXED (Uproszczona Lista) ---
    if current_user in FIXED_DOCTORS:
        st.info("👋 Tryb dodawania pojedynczych dyżurów. Kliknij '+', aby dodać wiersz i wybierz datę.")
        
        existing_data = []
        if not df_db.empty:
            d_strs = [d.strftime('%Y-%m-%d') for d in dates]
            mask = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(d_strs))
            subset = df_db[mask]
            
            for _, row in subset.iterrows():
                if row['Status'] == STATUS_FIXED:
                    try:
                        d_obj = datetime.datetime.strptime(row['Data'], '%Y-%m-%d').date()
                        existing_data.append({"Data": d_obj, "Status": STATUS_FIXED})
                    except: pass
        
        if not existing_data:
            jakub_df = pd.DataFrame(columns=["Data", "Status"])
        else:
            jakub_df = pd.DataFrame(existing_data)
        
        edited_jakub = st.data_editor(
            jakub_df,
            column_config={
                "Data": st.column_config.DateColumn("Data Dyżuru", format="DD.MM.YYYY", required=True),
                "Status": st.column_config.SelectboxColumn("Status", options=[STATUS_FIXED], required=True, default=STATUS_FIXED)
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )
        
        if st.button(f"💾 Zapisz Dyżury ({current_user})", type="primary"):
            with st.spinner("Zapisywanie..."):
                valid_entries = []
                period_date_strs = [d.strftime('%Y-%m-%d') for d in dates]
                
                for _, row in edited_jakub.iterrows():
                    d_val = row['Data']
                    if pd.isna(d_val): continue
                    try:
                        d_val_fixed = pd.to_datetime(d_val)
                        d_str = d_val_fixed.strftime('%Y-%m-%d')
                    except: continue 
                    
                    if d_str in period_date_strs:
                        valid_entries.append({"Data": d_str, "Lekarz": current_user, "Status": STATUS_FIXED})
                    else:
                        st.warning(f"Data {d_str} jest spoza wybranego okresu i została pominięta.")
                
                final_new = pd.DataFrame(valid_entries)
                if df_db.empty: final_db = final_new
                else:
                    mask_remove = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(period_date_strs))
                    df_cleaned = df_db[~mask_remove]
                    final_db = pd.concat([df_cleaned, final_new], ignore_index=True)
                if save_data(final_db): st.success(f"Zapisano listę dyżurów dla: {current_user}")

    # --- LOGIKA DLA GRUPY ROTATION (Pełny Kalendarz) ---
    else:
        t_data = []
        for d in dates:
            d_str = d.strftime('%Y-%m-%d')
            status = STATUS_AVAILABLE
            if not df_db.empty:
                rec = df_db[(df_db['Data'] == d_str) & (df_db['Lekarz'] == current_user)]
                if not rec.empty: status = rec.iloc[0]['Status']
            day_desc = get_day_description(d)
            m_name = "Msc 1" if d.month == start_m else "Msc 2"
            t_data.append({"Data": d, "Miesiąc": m_name, "Dzień / Święto": day_desc, "Status": status})
        
        opts = [STATUS_AVAILABLE, STATUS_RELUCTANT, STATUS_FIXED, STATUS_UNAVAILABLE]
        edited_df = st.data_editor(pd.DataFrame(t_data), column_config={
            "Data": st.column_config.DateColumn(disabled=True, format="DD.MM.YYYY"),
            "Miesiąc": st.column_config.TextColumn(disabled=True),
            "Dzień / Święto": st.column_config.TextColumn(disabled=True, width="medium"),
            "Status": st.column_config.SelectboxColumn("Decyzja", options=opts, required=True, width="medium")
        }, hide_index=True, height=600, use_container_width=True)
        
        if st.button(f"💾 Zapisz Dostępność ({current_user})", type="primary"):
            with st.spinner("Zapisywanie..."):
                new_entries = [{"Data": r['Data'].strftime('%Y-%m-%d'), "Lekarz": current_user, "Status": r['Status']} for _, r in edited_df.iterrows()]
                final = pd.DataFrame(new_entries)
                if not df_db.empty:
                    d_strs = [d.strftime('%Y-%m-%d') for d in dates]
                    mask = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(d_strs))
                    final = pd.concat([df_db[~mask], final], ignore_index=True)
                if save_data(final): st.success("Zapisano!")

# --- TAB 2 ---
with tab2:
    st.header("Kalkulator i Generator")
    all_prefs = load_data()
    dates_gen = get_period_dates(sel_year, start_m)
    
    # 1. Obliczamy ile dyżurów ma grupa FIXED (z bazy)
    fixed_counts_map = {doc: 0 for doc in FIXED_DOCTORS}
    
    if not all_prefs.empty:
        d_strs = [d.strftime('%Y-%m-%d') for d in dates_gen]
        # Filtrujemy tylko wpisy z tego okresu i tylko fixed
        period_data = all_prefs[all_prefs['Data'].isin(d_strs)]
        
        for doc in FIXED_DOCTORS:
            count = len(period_data[(period_data['Lekarz'] == doc) & (period_data['Status'] == STATUS_FIXED)])
            fixed_counts_map[doc] = count

    total_days = len(dates_gen)
    c1, c2, c3 = st.columns(3)
    c1.metric("Liczba dni w okresie", total_days)
    
    # Wyświetlamy tabelkę z podsumowaniem dyżurów Fixed (tylko do odczytu/edycji sumy)
    st.subheader("Dyżury Ustalone (Fixed)")
    st.caption("Poniżej liczba dyżurów zaciągnięta z bazy. Możesz ją ręcznie skorygować w kolumnie 'Do Obliczeń', aby wpłynąć na pulę dla reszty.")
    
    fixed_table_data = []
    for doc in FIXED_DOCTORS:
        fixed_table_data.append({
            "Lekarz": doc, 
            "Z bazy": fixed_counts_map[doc],
            "Do Obliczeń": fixed_counts_map[doc]
        })
    
    edited_fixed_table = st.data_editor(
        pd.DataFrame(fixed_table_data),
        column_config={
            "Lekarz": st.column_config.TextColumn(disabled=True),
            "Z bazy": st.column_config.NumberColumn(disabled=True),
            "Do Obliczeń": st.column_config.NumberColumn(min_value=0, max_value=31, step=1)
        },
        hide_index=True,
        use_container_width=True
    )
    
    total_fixed_calculated = edited_fixed_table["Do Obliczeń"].sum()
    c2.metric("Suma Fixed", total_fixed_calculated)
    
    rem_days = total_days - total_fixed_calculated
    c3.metric(f"Do podziału na {len(ROTATION_DOCTORS)} os.", max(0, rem_days))
    
    st.write("---")
    st.subheader(f"Limity dla Zespołu Rotacyjnego (Suma musi wynosić {rem_days})")
    
    # Obliczamy ile fixed mają lekarze ROTACYJNI (może się zdarzyć)
    fixed_rotation_counts = {doc: 0 for doc in ROTATION_DOCTORS}
    if not all_prefs.empty:
        period_data = all_prefs[all_prefs['Data'].isin([d.strftime('%Y-%m-%d') for d in dates_gen])]
        for doc in ROTATION_DOCTORS:
            count = len(period_data[(period_data['Lekarz'] == doc) & (period_data['Status'] == STATUS_FIXED)])
            fixed_rotation_counts[doc] = count
            
    total_rotation_fixed_already = sum(fixed_rotation_counts.values())
    to_randomize = max(0, rem_days - total_rotation_fixed_already)
    
    team_size = len(ROTATION_DOCTORS)
    if team_size > 0:
        base_extra = to_randomize // team_size
        remainder_extra = to_randomize % team_size
    else:
        base_extra = 0
        remainder_extra = 0
        
    lim_data = []
    for i, doc in enumerate(ROTATION_DOCTORS):
        extra = base_extra + 1 if i < remainder_extra else base_extra
        val_fixed = fixed_rotation_counts[doc]
        total_suggested = val_fixed + extra
        lim_data.append({"Lekarz": doc, "Limit Docelowy": total_suggested})
        
    edited_limits = st.data_editor(
        pd.DataFrame(lim_data), 
        column_config={
            "Limit Docelowy": st.column_config.NumberColumn(min_value=0, max_value=31, step=1)
        },
        hide_index=True, 
        use_container_width=True
    )
    
    current_target_sum = edited_limits["Limit Docelowy"].sum()
    
    if current_target_sum == rem_days:
        st.success(f"Suma limitów ({current_target_sum}) zgadza się z pulą do podziału ({rem_days}).")
        if st.button("🚀 GENERUJ", type="primary"):
            # Budujemy targets dla wszystkich. 
            # Dla Fixed - bierzemy to co w tabeli "Do Obliczeń" (chociaż algorytm i tak patrzy na konkretne dni, 
            # ale do statystyk się przyda).
            # Dla Rotation - bierzemy z tabeli limitów.
            
            targets = {}
            # Dodajemy rotacyjnych
            for _, r in edited_limits.iterrows():
                targets[r['Lekarz']] = r['Limit Docelowy']
            # Dodajemy fixed (żeby statystyki miały sensowne "Cel")
            for _, r in edited_fixed_table.iterrows():
                targets[r['Lekarz']] = r['Do Obliczeń']

            sch, stats = generate_schedule(dates_gen, all_prefs, targets)
            
            res_rows = []
            for d in dates_gen:
                is_free = is_red_day(d)
                res_rows.append({
                    "Data": d,
                    "Info": get_day_description(d),
                    "Dyżurny": sch.get(d.strftime('%Y-%m-%d'), "-"),
                    "_is_red": is_free
                })
            
            df_res = pd.DataFrame(res_rows)
            
            def highlight_red_days(row):
                return ['color: #D81B60; font-weight: bold'] * len(row) if row['_is_red'] else [''] * len(row)
            
            st.dataframe(
                df_res.style.apply(highlight_red_days, axis=1).format({"Data": lambda t: t.strftime("%Y-%m-%d")}),
                use_container_width=True, 
                height=600,
                column_config={"_is_red": None}
            )
            
            st.write("---")
            s_rows = []
            for d in ALL_DOCTORS:
                goal = targets.get(d, 0)
                s_rows.append({
                    "Lekarz": d, 
                    "Cel": goal, 
                    "Wykonano": stats[d]['Total'], 
                    **{k:v for k,v in stats[d].items() if k!='Total'}
                })

            st.dataframe(pd.DataFrame(s_rows), hide_index=True)
    else:
        st.error(f"Suma limitów rotacyjnych wynosi {current_target_sum}, a powinna {rem_days}. Skoryguj liczby.")
