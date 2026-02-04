import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from github import Github
from io import StringIO

# --- KONFIGURACJA ZESPOŁU ---
# Lista lekarzy (bez Jakuba Sz., bo on jest traktowany osobno w kalkulacjach)
DOCTORS_TEAM = ["Jędrzej", "Filip", "Ihab", "Kacper", "Jakub", "Tymoteusz"]
JAKUB_SZ = "Jakub Sz."
ALL_DOCTORS = [JAKUB_SZ] + DOCTORS_TEAM

# Statusy
STATUS_AVAILABLE = "Chcę dyżur (Dostępny)"
STATUS_RELUCTANT = "Mogę (Niechętnie)"
STATUS_UNAVAILABLE = "Niedostępny"
STATUS_FIXED = "Sztywny Dyżur (Jakub Sz.)"

# Grupy dni
GROUP_MON = "Poniedziałki"
GROUP_TUE_WED = "Wtorki/Środy"
GROUP_THU = "Czwartki"
GROUP_FRI = "Piątki"
GROUP_SAT = "Soboty"
GROUP_SUN = "Niedziele"

# Nazwa pliku w repozytorium
DATA_FILE = "data.csv"

# --- OBSŁUGA GITHUBA ---

def get_repo():
    """Łączy się z GitHubem."""
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        user = g.get_user()
        # Szukamy repozytorium 'grafik' lub pierwszego dostępnego
        for repo in user.get_repos():
             if any(x in repo.name.lower() for x in ["grafik", "urologia", "dyzury"]):
                 return repo
        return user.get_repos()[0]
    except Exception as e:
        st.error(f"Błąd połączenia z GitHubem: {e}")
        return None

def load_data():
    """Pobiera dane."""
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
    """Zapisuje dane."""
    repo = get_repo()
    if not repo: return False
    csv_content = df.to_csv(index=False)
    try:
        contents = repo.get_contents(DATA_FILE)
        repo.update_file(contents.path, "Aktualizacja", csv_content, contents.sha)
        return True
    except:
        try:
            repo.create_file(DATA_FILE, "Init", csv_content)
            return True
        except: return False

# --- LOGIKA KALENDARZA ---

def get_settlement_period_info(year, month):
    # Okresy zaczynają się w miesiącach nieparzystych: 1, 3, 5, 7, 9, 11
    # Jeśli podano parzysty, cofamy do nieparzystego startu
    start_month = month if month % 2 != 0 else month - 1
    start_date = datetime.date(year, start_month, 1)
    day_names_pl = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
    return start_date, day_names_pl[start_date.weekday()]

def get_period_dates(year, start_month):
    """Generuje listę dat dla całego 2-miesięcznego okresu."""
    dates = []
    
    # Miesiąc 1
    num_days_1 = calendar.monthrange(year, start_month)[1]
    dates.extend([datetime.date(year, start_month, d) for d in range(1, num_days_1 + 1)])
    
    # Miesiąc 2 (obsługa przejścia roku teoretycznie niepotrzebna przy blokach 1-2, ..., 11-12)
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
    if wd == 0: return GROUP_MON
    if wd in [1, 2]: return GROUP_TUE_WED
    if wd == 3: return GROUP_THU
    if wd == 4: return GROUP_FRI
    if wd == 5: return GROUP_SAT
    if wd == 6: return GROUP_SUN
    return "Inne"

# --- GENERATOR Z LIMITAMI ---

def generate_schedule(dates, preferences_df, target_limits):
    schedule = {} 
    stats = {doc: {'Total': 0, GROUP_MON: 0, GROUP_TUE_WED: 0, GROUP_THU: 0, GROUP_FRI: 0, GROUP_SAT: 0, GROUP_SUN: 0} for doc in ALL_DOCTORS}
    weekly_counts = {}

    prefs_map = {}
    if not preferences_df.empty:
        for _, row in preferences_df.iterrows():
            d_str = str(row['Data'])
            if d_str not in prefs_map: prefs_map[d_str] = {}
            prefs_map[d_str][row['Lekarz']] = row['Status']

    # KROK 1: Jakub Sz. (Sztywne dyżury)
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        if prefs_map.get(d_str, {}).get(JAKUB_SZ) == STATUS_FIXED:
            schedule[d_str] = JAKUB_SZ
            stats[JAKUB_SZ]['Total'] += 1
            stats[JAKUB_SZ][get_day_group(d)] += 1
            wk = get_week_key(d)
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][JAKUB_SZ] = weekly_counts[wk].get(JAKUB_SZ, 0) + 1

    # KROK 2: Reszta zespołu
    days_to_fill = [d for d in dates if d.strftime('%Y-%m-%d') not in schedule]
    random.shuffle(days_to_fill)
    
    for d in days_to_fill:
        d_str = d.strftime('%Y-%m-%d')
        wk = get_week_key(d)
        group = get_day_group(d)

        candidates = []

        for doc in DOCTORS_TEAM:
            # 1. Limit globalny (na 2 miesiące)
            if stats[doc]['Total'] >= target_limits.get(doc, 0):
                continue

            # 2. Dostępność
            status = prefs_map.get(d_str, {}).get(doc, STATUS_AVAILABLE)
            if status == STATUS_UNAVAILABLE: continue

            # 3. Odpoczynek po dyżurze
            prev_day = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            if schedule.get(prev_day) == doc: continue

            # 4. Limit tygodniowy (2 max)
            if weekly_counts.get(wk, {}).get(doc, 0) >= 2: continue

            weight = 10 if status == STATUS_AVAILABLE else 1
            
            candidates.append({
                'name': doc,
                'weight': weight,
                'group_count': stats[doc][group],
                'total_count': stats[doc]['Total']
            })

        if candidates:
            # Sortowanie: 
            # 1. Preferencja (chętni)
            # 2. Wyrównanie grup (kto ma najmniej w tej grupie dni)
            # 3. Wyrównanie ogólne
            # 4. Losowość
            candidates.sort(key=lambda x: (-x['weight'], x['group_count'], x['total_count'], random.random()))
            chosen = candidates[0]['name']
            
            schedule[d_str] = chosen
            stats[chosen]['Total'] += 1
            stats[chosen][group] += 1
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][chosen] = weekly_counts[wk].get(chosen, 0) + 1
        else:
            schedule[d_str] = "BRAK (Konflikt reguł)"

    return schedule, stats

# --- UI ---
st.set_page_config(page_title="Grafik Urologia", layout="wide")
st.title("🏥 Grafik Dyżurowy - Urologia")

with st.sidebar:
    st.header("Konfiguracja")
    st.image("https://img.icons8.com/fluency/96/calendar.png", width=64)
    
    # Wybór okresu 2-miesięcznego
    periods = [
        "Styczeń - Luty", 
        "Marzec - Kwiecień", 
        "Maj - Czerwiec", 
        "Lipiec - Sierpień", 
        "Wrzesień - Październik", 
        "Listopad - Grudzień"
    ]
    
    today = datetime.date.today()
    # Próba zgadnięcia obecnego okresu
    curr_month = today.month
    # Mapowanie miesiąca na indeks okresu (0-5)
    # 1,2 -> 0; 3,4 -> 1; 5,6 -> 2 etc.
    default_idx = (curr_month - 1) // 2
    
    sel_period_name = st.selectbox("Okres Rozliczeniowy", periods, index=default_idx)
    sel_year = st.number_input("Rok", 2025, 2030, today.year)
    
    # Mapowanie nazwy na numer miesiąca startowego
    period_start_months = {
        "Styczeń - Luty": 1, 
        "Marzec - Kwiecień": 3, 
        "Maj - Czerwiec": 5, 
        "Lipiec - Sierpień": 7, 
        "Wrzesień - Październik": 9, 
        "Listopad - Grudzień": 11
    }
    start_m = period_start_months[sel_period_name]
    
    p_start, p_day = get_settlement_period_info(sel_year, start_m)
    st.info(f"Początek okresu: {p_start} ({p_day}).\nGrafik generowany jest łącznie dla 2 miesięcy.")

tab1, tab2 = st.tabs(["📝 Zgłaszanie Dostępności", "🧮 Kalkulator i Grafik"])

# --- TAB 1: DOSTĘPNOŚĆ ---
with tab1:
    st.subheader(f"Dostępność: {sel_period_name} {sel_year}")
    current_user = st.selectbox("Lekarz:", ALL_DOCTORS, index=2)
    
    # Generuj daty dla 2 miesięcy
    dates = get_period_dates(sel_year, start_m)
    
    df_db = load_data()
    
    # Budowa tabeli
    t_data = []
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        status = STATUS_AVAILABLE
        if not df_db.empty:
            rec = df_db[(df_db['Data'] == d_str) & (df_db['Lekarz'] == current_user)]
            if not rec.empty: status = rec.iloc[0]['Status']
        
        day_pl = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"][d.weekday()]
        # Dodajemy kolumnę z miesiącem dla czytelności
        m_name = "Miesiąc 1" if d.month == start_m else "Miesiąc 2"
        
        t_data.append({"Data": d, "Miesiąc": m_name, "Dzień": day_pl, "Status": status})
    
    opts = [STATUS_AVAILABLE, STATUS_RELUCTANT, STATUS_UNAVAILABLE]
    if current_user == JAKUB_SZ: 
        opts = [STATUS_FIXED, STATUS_UNAVAILABLE]
        st.info("Jakubie, zaznacz 'Sztywny Dyżur' w dniach, które bierzesz na stałe.")

    edited_df = st.data_editor(pd.DataFrame(t_data), column_config={
        "Data": st.column_config.DateColumn(disabled=True, format="DD.MM.YYYY"),
        "Miesiąc": st.column_config.TextColumn(disabled=True),
        "Dzień": st.column_config.TextColumn(disabled=True),
        "Status": st.column_config.SelectboxColumn("Decyzja", options=opts, required=True, width="medium")
    }, hide_index=True, height=600, use_container_width=True)
    
    if st.button("💾 Zapisz Dostępność (GitHub)", type="primary"):
        with st.spinner("Zapisywanie..."):
            new_entries = [{"Data": r['Data'].strftime('%Y-%m-%d'), "Lekarz": current_user, "Status": r['Status']} for _, r in edited_df.iterrows()]
            df_new = pd.DataFrame(new_entries)
            
            if df_db.empty: final = df_new
            else:
                d_strs = [d.strftime('%Y-%m-%d') for d in dates]
                mask = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(d_strs))
                final = pd.concat([df_db[~mask], df_new], ignore_index=True)
            
            if save_data(final): st.success("Zapisano!")

# --- TAB 2: KALKULATOR I GENERATOR ---
with tab2:
    st.header("1. Kalkulator Dyżurów (na 2 miesiące)")
    
    all_prefs = load_data()
    dates_gen = get_period_dates(sel_year, start_m)
    
    # Policz ile dni Jakub Sz. zaznaczył jako FIXED w CAŁYM okresie
    jakub_fixed_count = 0
    if not all_prefs.empty:
        for d in dates_gen:
            d_s = d.strftime('%Y-%m-%d')
            s = all_prefs[(all_prefs['Data'] == d_s) & (all_prefs['Lekarz'] == JAKUB_SZ)]
            if not s.empty and s.iloc[0]['Status'] == STATUS_FIXED:
                jakub_fixed_count += 1

    total_days = len(dates_gen)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Dni w okresie", total_days)
    
    # Input dla Jakuba
    jakub_shifts = col2.number_input(f"Dyżury {JAKUB_SZ} (łącznie)", min_value=0, max_value=total_days, value=jakub_fixed_count)
    
    remaining_days = total_days - jakub_shifts
    col3.metric("Do podziału na resztę", remaining_days)
    
    # 2. Podział na resztę zespołu
    team_size = len(DOCTORS_TEAM)
    if team_size > 0:
        base_shifts = remaining_days // team_size
        remainder = remaining_days % team_size
    else:
        base_shifts = 0
        remainder = 0
    
    st.subheader("2. Ustal Limity dla Lekarzy")
    st.write(f"Na każdego z {team_size} lekarzy przypada średnio **{base_shifts}** dyżurów (w ciągu 2 mies). Reszta: **{remainder}**.")
    
    limits_data = []
    for i, doc in enumerate(DOCTORS_TEAM):
        val = base_shifts + 1 if i < remainder else base_shifts
        limits_data.append({"Lekarz": doc, "Limit Dyżurów": val})
        
    limits_df = pd.DataFrame(limits_data)
    
    edited_limits = st.data_editor(
        limits_df, 
        column_config={"Limit Dyżurów": st.column_config.NumberColumn(min_value=0, max_value=30, step=1)},
        hide_index=True,
        use_container_width=True
    )
    
    # Walidacja sumy
    current_sum = edited_limits["Limit Dyżurów"].sum()
    if current_sum != remaining_days:
        st.warning(f"⚠️ Suma przydzielonych dyżurów ({current_sum}) nie zgadza się z liczbą dni do obsadzenia ({remaining_days})!")
    else:
        st.success(f"✅ Suma się zgadza ({current_sum}). Można generować.")
    
        if st.button("🚀 GENERUJ GRAFIK (2 MIESIĄCE)", type="primary"):
            targets = {row['Lekarz']: row['Limit Dyżurów'] for _, row in edited_limits.iterrows()}
            
            with st.spinner("Układanie grafiku na cały okres..."):
                schedule_map, stats = generate_schedule(dates_gen, all_prefs, targets)
            
            # Wyniki - Tabela
            res_data = []
            for d in dates_gen:
                res_data.append({
                    "Data": d,
                    "Dzień": ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"][d.weekday()],
                    "Miesiąc": "Msc 1" if d.month == start_m else "Msc 2",
                    "Dyżurny": schedule_map.get(d.strftime('%Y-%m-%d'), "-")
                })
            
            st.dataframe(pd.DataFrame(res_data), use_container_width=True, hide_index=True, height=600)
            
            st.divider()
            st.subheader("Statystyki Wykonania Planu")
            s_rows = []
            for doc in ALL_DOCTORS:
                target = jakub_shifts if doc == JAKUB_SZ else targets.get(doc, 0)
                realized = stats[doc]['Total']
                status_icon = "✅" if realized == target else "⚠️"
                
                row = {
                    "Lekarz": doc, 
                    "Cel": target, 
                    "Wykonano": realized, 
                    "Status": status_icon,
                    **{k:v for k,v in stats[doc].items() if k!='Total'}
                }
                s_rows.append(row)
                
            st.dataframe(pd.DataFrame(s_rows), hide_index=True)
            
            missing = [d['Data'] for d in res_data if "BRAK" in str(d['Dyżurny'])]
            if missing:
                st.error(f"Nie udało się obsadzić dni: {len(missing)} dni. Sprawdź dostępność i limity.")
