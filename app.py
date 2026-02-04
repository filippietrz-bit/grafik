import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from streamlit_gsheets import GSheetsConnection

# --- KONFIGURACJA ZESPOŁU ---
DOCTORS = [
    "Jakub Sz.", 
    "Jędrzej", 
    "Filip", 
    "Ihab", 
    "Kacper", 
    "Jakub", 
    "Tymoteusz"
]

# Definicje statusów
STATUS_AVAILABLE = "Chcę dyżur (Dostępny)"
STATUS_RELUCTANT = "Mogę (Niechętnie)"
STATUS_UNAVAILABLE = "Niedostępny"
STATUS_FIXED = "Sztywny Dyżur (Jakub Sz.)"

# Grupy dni (sprawiedliwość)
GROUP_MON = "Poniedziałki"
GROUP_TUE_WED = "Wtorki/Środy"
GROUP_THU = "Czwartki"
GROUP_FRI = "Piątki"
GROUP_SAT = "Soboty"
GROUP_SUN = "Niedziele"

# --- FUNKCJE POMOCNICZE (LOGIKA MEDYCZNA) ---

def get_settlement_period_info(year, month):
    """Oblicza początek 2-miesięcznego okresu rozliczeniowego (styczeń-luty, marzec-kwiecień itd)."""
    # Jeśli miesiąc parzysty, cofamy się o 1. Jeśli nieparzysty, to jest początek.
    start_month = month if month % 2 != 0 else month - 1
    start_date = datetime.date(year, start_month, 1)
    
    day_names_pl = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
    start_day_name = day_names_pl[start_date.weekday()]
    
    return start_date, start_day_name

def get_week_key(date_obj):
    """Oblicza numer tygodnia w okresie rozliczeniowym (ruchomy tydzień)."""
    period_start_date, _ = get_settlement_period_info(date_obj.year, date_obj.month)
    days_diff = (date_obj - period_start_date).days
    week_index = days_diff // 7
    return f"{date_obj.year}_Okres{period_start_date.month}_Tydzien{week_index}"

def get_day_group(date_obj):
    """Zwraca grupę dnia dla sprawiedliwego podziału."""
    wd = date_obj.weekday()
    if wd == 0: return GROUP_MON
    if wd in [1, 2]: return GROUP_TUE_WED
    if wd == 3: return GROUP_THU
    if wd == 4: return GROUP_FRI
    if wd == 5: return GROUP_SAT
    if wd == 6: return GROUP_SUN
    return "Inne"

# --- OBSŁUGA ARKUSZY GOOGLE ---

def load_data():
    """Pobiera dane z Arkusza."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        # ttl=0 oznacza, że nie cache'ujemy danych, zawsze pobieramy świeże
        df = conn.read(ttl=0)
        # Jeśli arkusz jest pusty lub ma złe kolumny, zwracamy pusty DataFrame
        if df.empty or "Data" not in df.columns:
            return pd.DataFrame(columns=["Data", "Lekarz", "Status"])
        # Konwersja daty na string (dla bezpieczeństwa)
        df['Data'] = df['Data'].astype(str)
        return df
    except Exception as e:
        # Jeśli nie ma połączenia (np. lokalnie bez secrets), zwracamy pusty DF
        return pd.DataFrame(columns=["Data", "Lekarz", "Status"])

def save_data(df):
    """Zapisuje dane do Arkusza."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        conn.update(data=df)
        st.cache_data.clear() # Czyścimy cache Streamlit
        return True
    except Exception as e:
        st.error(f"Błąd zapisu (sprawdź secrets): {e}")
        return False

# --- GENERATOR GRAFIKU ---

def generate_schedule(dates, preferences_df):
    schedule = {} 
    stats = {doc: {'Total': 0, GROUP_MON: 0, GROUP_TUE_WED: 0, GROUP_THU: 0, GROUP_FRI: 0, GROUP_SAT: 0, GROUP_SUN: 0} for doc in DOCTORS}
    weekly_counts = {}

    # Konwersja preferencji na słownik dla szybkiego dostępu
    prefs_map = {}
    if not preferences_df.empty:
        for _, row in preferences_df.iterrows():
            d_str = str(row['Data'])
            if d_str not in prefs_map: prefs_map[d_str] = {}
            prefs_map[d_str][row['Lekarz']] = row['Status']

    # KROK 1: Sztywne dyżury (Jakub Sz.)
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        if prefs_map.get(d_str, {}).get("Jakub Sz.") == STATUS_FIXED:
            assignee = "Jakub Sz."
            schedule[d_str] = assignee
            
            # Statystyki
            stats[assignee]['Total'] += 1
            stats[assignee][get_day_group(d)] += 1
            wk = get_week_key(d)
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][assignee] = weekly_counts[wk].get(assignee, 0) + 1

    # KROK 2: Reszta zespołu
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        if d_str in schedule: continue # Już zajęte

        candidates = []
        wk = get_week_key(d)
        group = get_day_group(d)

        for doc in DOCTORS:
            if doc == "Jakub Sz.": continue # On ma tylko sztywne

            # --- SPRAWDZANIE ZASAD ---
            # 1. Dostępność
            status = prefs_map.get(d_str, {}).get(doc, STATUS_AVAILABLE)
            if status == STATUS_UNAVAILABLE: continue

            # 2. Odpoczynek po dyżurze (wczoraj nie mógł mieć dyżuru)
            prev_day = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            if schedule.get(prev_day) == doc: continue

            # 3. Limit 2 dyżury w tygodniu rozliczeniowym
            current_week_count = weekly_counts.get(wk, {}).get(doc, 0)
            if current_week_count >= 2: continue

            # --- PUNKTACJA ---
            weight = 10 if status == STATUS_AVAILABLE else 1
            
            candidates.append({
                'name': doc,
                'weight': weight,
                'group_count': stats[doc][group], # Kto ma najmniej dyżurów w te dni (np. w piątki)
                'total_count': stats[doc]['Total'] # Kto ma najmniej ogółem
            })

        if candidates:
            # Sortowanie: 
            # 1. Waga (chętni), 
            # 2. Mało w grupie, 
            # 3. Mało ogółem, 
            # 4. Losowo
            candidates.sort(key=lambda x: (-x['weight'], x['group_count'], x['total_count'], random.random()))
            chosen = candidates[0]['name']
            
            schedule[d_str] = chosen
            
            # Update statystyk
            stats[chosen]['Total'] += 1
            stats[chosen][group] += 1
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][chosen] = weekly_counts[wk].get(chosen, 0) + 1
        else:
            schedule[d_str] = "BRAK (Wszyscy zajęci/zmęczeni)"

    return schedule, stats

# --- INTERFEJS STRONY ---

st.set_page_config(page_title="Grafik Urologia", layout="wide")

st.title("🏥 Grafik Dyżurowy - Urologia")

# Sidebar - Daty
with st.sidebar:
    st.header("Konfiguracja")
    months = list(calendar.month_name)[1:]
    pl_months = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
    
    today = datetime.date.today()
    # Domyślnie następny miesiąc
    default_month_idx = (today.month % 12) 
    
    sel_month_name = st.selectbox("Miesiąc", pl_months, index=default_month_idx)
    sel_month = pl_months.index(sel_month_name) + 1
    sel_year = st.number_input("Rok", 2025, 2030, today.year if today.month < 12 else today.year + 1)
    
    # Info o okresie rozliczeniowym
    p_start, p_day = get_settlement_period_info(sel_year, sel_month)
    st.info(f"Okres rozliczeniowy zaczął się: {p_start} ({p_day}). Tydzień kodeksowy trwa od {p_day}a.")

# Główne zakładki
tab1, tab2 = st.tabs(["📝 Zgłaszanie Dostępności", "⚙️ Generowanie Grafiku"])

with tab1:
    st.subheader("Krok 1: Wybierz swoje nazwisko i zaznacz dostępność")
    current_user = st.selectbox("Jestem:", DOCTORS, index=2) # Domyślnie Filip
    
    dates = [datetime.date(sel_year, sel_month, day) for day in range(1, calendar.monthrange(sel_year, sel_month)[1] + 1)]
    
    # 1. Pobierz dane z Google Sheets
    df_db = load_data()
    
    # 2. Przygotuj dane do wyświetlenia w tabeli
    table_data = []
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        
        # Sprawdź co jest w bazie, jak nie ma to domyślny status
        status = STATUS_AVAILABLE
        if not df_db.empty:
            # Filtrujemy: ten dzień i ten lekarz
            record = df_db[(df_db['Data'] == d_str) & (df_db['Lekarz'] == current_user)]
            if not record.empty:
                status = record.iloc[0]['Status']
        
        day_pl = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"][d.weekday()]
        table_data.append({"Data": d, "Dzień": day_pl, "Status": status})
    
    df_editor = pd.DataFrame(table_data)
    
    # Opcje wyboru w tabeli
    opts = [STATUS_AVAILABLE, STATUS_RELUCTANT, STATUS_UNAVAILABLE]
    if current_user == "Jakub Sz.":
        opts = [STATUS_FIXED, STATUS_UNAVAILABLE]
        st.warning("Jakubie, zaznacz 'Sztywny Dyżur' tam gdzie masz ustalone terminy.")

    # 3. Wyświetl edytowalną tabelę
    edited_df = st.data_editor(
        df_editor,
        column_config={
            "Data": st.column_config.DateColumn(format="DD.MM.YYYY", disabled=True),
            "Dzień": st.column_config.TextColumn(disabled=True),
            "Status": st.column_config.SelectboxColumn("Twoja decyzja", options=opts, required=True, width="medium")
        },
        hide_index=True,
        use_container_width=True,
        height=500
    )
    
    # 4. Przycisk Zapisz
    if st.button("💾 Zapisz moje preferencje", type="primary"):
        with st.spinner("Zapisywanie do chmury..."):
            # Przygotuj nowe dane tego użytkownika
            new_entries = []
            for _, row in edited_df.iterrows():
                new_entries.append({
                    "Data": row['Data'].strftime('%Y-%m-%d'),
                    "Lekarz": current_user,
                    "Status": row['Status']
                })
            df_new = pd.DataFrame(new_entries)
            
            # Jeśli baza była pusta, to po prostu to nasze nowe dane
            if df_db.empty:
                final_df = df_new
            else:
                # Usuń stare wpisy tego lekarza dla tego miesiąca (żeby nie dublować)
                # (Konwersja dat na stringi dla pewności porównania)
                dates_str = [d.strftime('%Y-%m-%d') for d in dates]
                mask = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(dates_str))
                df_db_cleaned = df_db[~mask]
                
                # Połącz stare (bez tego usera w tym miesiącu) z nowymi
                final_df = pd.concat([df_db_cleaned, df_new], ignore_index=True)
            
            # Wyślij do Google Sheets
            if save_data(final_df):
                st.success(f"Gotowe! Preferencje dla lekarza {current_user} zapisane.")

with tab2:
    st.subheader("Krok 2: Generowanie grafiku dla całego zespołu")
    st.info("Algorytm bierze pod uwagę: regułę 11h odpoczynku, max 2 dyżury w tygodniu rozliczeniowym oraz sprawiedliwy podział dni.")
    
    if st.button("🚀 UŁÓŻ GRAFIK", type="primary"):
        # Pobierz wszystko z bazy
        all_prefs = load_data()
        
        dates_gen = [datetime.date(sel_year, sel_month, day) for day in range(1, calendar.monthrange(sel_year, sel_month)[1] + 1)]
        
        schedule_map, stats = generate_schedule(dates_gen, all_prefs)
        
        # Przygotuj wynik
        res_data = []
        for d in dates_gen:
            d_str = d.strftime('%Y-%m-%d')
            who = schedule_map.get(d_str, "-")
            day_pl = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"][d.weekday()]
            res_data.append({
                "Data": d,
                "Dzień": day_pl,
                "Dyżurny": who
            })
            
        st.success("Grafik wygenerowany!")
        st.dataframe(pd.DataFrame(res_data), use_container_width=True, hide_index=True)
        
        st.write("---")
        st.subheader("Czy jest sprawiedliwie? (Statystyki)")
        
        stats_rows = []
        for doc, s in stats.items():
            r = {"Lekarz": doc, "SUMA": s['Total']}
            r.update({k: v for k, v in s.items() if k != 'Total'})
            stats_rows.append(r)
            
        st.dataframe(pd.DataFrame(stats_rows), hide_index=True)
