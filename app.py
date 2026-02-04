import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from github import Github
from io import StringIO

# --- KONFIGURACJA ZESPOŁU ---
DOCTORS_TEAM = ["Jędrzej", "Filip", "Ihab", "Kacper", "Jakub", "Tymoteusz"]
JAKUB_SZ = "Jakub Sz."
ALL_DOCTORS = [JAKUB_SZ] + DOCTORS_TEAM

# Statusy
STATUS_AVAILABLE = "Chcę dyżur (Dostępny)"
STATUS_RELUCTANT = "Mogę (Niechętnie)"
STATUS_UNAVAILABLE = "Niedostępny"
STATUS_FIXED = "Sztywny Dyżur (Już ustalony)"  # Zmiana nazwy na bardziej uniwersalną

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
    # Inicjalizacja statystyk dla WSZYSTKICH lekarzy
    stats = {doc: {'Total': 0, "Poniedziałki": 0, "Wtorki/Środy": 0, "Czwartki": 0, "Piątki": 0, "Soboty": 0, "Niedziele": 0} for doc in ALL_DOCTORS}
    weekly_counts = {}

    prefs_map = {}
    if not preferences_df.empty:
        for _, row in preferences_df.iterrows():
            d_str = str(row['Data'])
            if d_str not in prefs_map: prefs_map[d_str] = {}
            prefs_map[d_str][row['Lekarz']] = row['Status']

    # KROK 1: SZTYWNE DYŻURY (Dla WSZYSTKICH lekarzy)
    # Iterujemy po wszystkich datach i sprawdzamy, czy ktoś ma "Fixed"
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        day_prefs = prefs_map.get(d_str, {})
        
        # Sprawdzamy, czy któryś lekarz ma tu sztywny dyżur
        assigned_fixed = None
        for doc in ALL_DOCTORS:
            if day_prefs.get(doc) == STATUS_FIXED:
                assigned_fixed = doc
                break # Zakładamy, że tylko jedna osoba ma fixed na dany dzień (kto pierwszy ten lepszy w pętli)
        
        if assigned_fixed:
            schedule[d_str] = assigned_fixed
            stats[assigned_fixed]['Total'] += 1
            stats[assigned_fixed][get_day_group(d)] += 1
            
            wk = get_week_key(d)
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][assigned_fixed] = weekly_counts[wk].get(assigned_fixed, 0) + 1

    # KROK 2: Obsadzanie reszty dni (tylko te, które nie są jeszcze w schedule)
    days_to_fill = [d for d in dates if d.strftime('%Y-%m-%d') not in schedule]
    random.shuffle(days_to_fill)
    
    for d in days_to_fill:
        d_str = d.strftime('%Y-%m-%d')
        wk = get_week_key(d)
        group = get_day_group(d)
        candidates = []

        # Daty sąsiednie do sprawdzania odpoczynku
        prev_day = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        next_day = (d + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        for doc in ALL_DOCTORS: # Teraz wszyscy mogą brać udział w losowaniu reszty (jeśli mają wolne limity)
            # Jeśli Jakub Sz. ma być tylko "fixed only", to można go tu pominąć warunkiem, 
            # ale jeśli ma brać dodatkowe dyżury, to zostaje. 
            # Domyślnie: Jakub Sz. zaznacza fixed, a reszta przydzielana jest wg limitu. 
            # Jeśli w kalkulatorze wpisano dla niego limit = liczba fixed, to warunek 1 go wytnie.
            
            # 1. Limit globalny
            if stats[doc]['Total'] >= target_limits.get(doc, 0): continue
            
            # 2. Dostępność
            status = prefs_map.get(d_str, {}).get(doc, STATUS_AVAILABLE)
            if status == STATUS_UNAVAILABLE: continue
            
            # 3. Odpoczynek po dyżurze (DZIEŃ WCZEŚNIEJSZY)
            # Czy lekarz pracował wczoraj?
            if schedule.get(prev_day) == doc: continue
            
            # 4. Odpoczynek przed dyżurem (DZIEŃ NASTĘPNY - FIXED)
            # Czy lekarz ma JUŻ PRZYDZIELONY (sztywny) dyżur jutro?
            # Jeśli tak, to dzisiaj nie może pracować, bo jutro rano wchodzi na dyżur (więc nie ma wolnego po dzisiejszym).
            # A jeśli dzisiaj weźmie, to jutro nie będzie wypoczęty? 
            # Zasada brzmi: dzień po dyżurze wolny. Więc jeśli wezmę dzisiaj, to jutro muszę mieć wolne.
            # A jeśli jutro mam sztywny, to nie mogę mieć wolnego -> więc nie mogę wziąć dzisiaj.
            if schedule.get(next_day) == doc: continue
            
            # 5. Limit tygodniowy (2 max)
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
    current_user = st.selectbox("Lekarz:", ALL_DOCTORS, index=2)
    
    dates = get_period_dates(sel_year, start_m)
    df_db = load_data()
    
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
    
    # TERAZ WSZYSCY MAJĄ DOSTĘP DO OPCJI 'FIXED'
    opts = [STATUS_AVAILABLE, STATUS_RELUCTANT, STATUS_FIXED, STATUS_UNAVAILABLE]

    edited_df = st.data_editor(pd.DataFrame(t_data), column_config={
        "Data": st.column_config.DateColumn(disabled=True, format="DD.MM.YYYY"),
        "Miesiąc": st.column_config.TextColumn(disabled=True),
        "Dzień / Święto": st.column_config.TextColumn(disabled=True, width="medium"),
        "Status": st.column_config.SelectboxColumn("Decyzja", options=opts, required=True, width="medium")
    }, hide_index=True, height=600, use_container_width=True)
    
    if st.button("💾 Zapisz (GitHub)", type="primary"):
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
    
    # Zliczamy sztywne dyżury dla każdego lekarza
    fixed_counts = {doc: 0 for doc in ALL_DOCTORS}
    if not all_prefs.empty:
        for d in dates_gen:
            d_s = d.strftime('%Y-%m-%d')
            # Pobieramy wpisy dla danej daty
            day_entries = all_prefs[all_prefs['Data'] == d_s]
            for _, row in day_entries.iterrows():
                if row['Status'] == STATUS_FIXED:
                    fixed_counts[row['Lekarz']] = fixed_counts.get(row['Lekarz'], 0) + 1

    total_days = len(dates_gen)
    total_fixed = sum(fixed_counts.values())
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Liczba dni", total_days)
    c2.metric("Już obsadzone (Fixed)", total_fixed)
    
    rem_days = total_days - total_fixed
    c3.metric("Do losowania", max(0, rem_days))
    
    st.write("---")
    st.subheader("Ustal Limity (Cel Dyżurów)")
    
    # Proponowane limity: Fixed + (Reszta / Liczba Lekarzy)
    team_size = len(ALL_DOCTORS)
    if team_size > 0:
        base_extra = max(0, rem_days) // team_size
        remainder_extra = max(0, rem_days) % team_size
    else:
        base_extra = 0
        remainder_extra = 0
        
    lim_data = []
    for i, doc in enumerate(ALL_DOCTORS):
        extra = base_extra + 1 if i < remainder_extra else base_extra
        total_suggested = fixed_counts[doc] + extra
        lim_data.append({"Lekarz": doc, "Fixed (Już ma)": fixed_counts[doc], "Limit Docelowy": total_suggested})
        
    edited_limits = st.data_editor(
        pd.DataFrame(lim_data), 
        column_config={
            "Fixed (Już ma)": st.column_config.NumberColumn(disabled=True),
            "Limit Docelowy": st.column_config.NumberColumn(min_value=0, max_value=31, step=1)
        },
        hide_index=True, 
        use_container_width=True
    )
    
    current_target_sum = edited_limits["Limit Docelowy"].sum()
    
    if current_target_sum == total_days:
        st.success(f"Suma limitów ({current_target_sum}) zgadza się z liczbą dni ({total_days}).")
        if st.button("🚀 GENERUJ", type="primary"):
            targets = {r['Lekarz']: r['Limit Docelowy'] for _, r in edited_limits.iterrows()}
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
                return ['background-color: #ffe6e6'] * len(row) if row['_is_red'] else [''] * len(row)
            
            st.dataframe(
                df_res.style.apply(highlight_red_days, axis=1).format({"Data": lambda t: t.strftime("%Y-%m-%d")}),
                use_container_width=True, 
                height=600,
                column_config={"_is_red": None}
            )
            
            st.write("---")
            s_rows = [{"Lekarz": d, "Cel": targets.get(d,0), "Wykonano": stats[d]['Total'], **{k:v for k,v in stats[d].items() if k!='Total'}} for d in ALL_DOCTORS]
            st.dataframe(pd.DataFrame(s_rows), hide_index=True)
    else:
        st.error(f"Suma 'Limit Docelowy' wynosi {current_target_sum}, a powinna {total_days}. Skoryguj liczby w tabeli.")
