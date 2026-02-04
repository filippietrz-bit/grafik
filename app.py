import streamlit as st
import pandas as pd
import datetime
import calendar
import random
from github import Github
from io import StringIO

# --- KONFIGURACJA ZESPOŁU ---
DOCTORS = [
    "Jakub Sz.", "Jędrzej", "Filip", "Ihab", "Kacper", "Jakub", "Tymoteusz"
]
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

# Nazwa pliku w repozytorium, gdzie trzymamy dane
DATA_FILE = "data.csv"
# UWAGA: Tutaj Streamlit sam znajdzie repozytorium po tokenie, 
# ale dla pewności wpisz tu nazwę swojego repozytorium jeśli znasz, np. "grafik-urologia"
# Jeśli zostawisz None, skrypt spróbuje zgadnąć.

# --- OBSŁUGA GITHUBA (ZAMIAST GOOGLE SHEETS) ---

def get_repo():
    """Łączy się z repozytorium GitHub używając tokenu."""
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        user = g.get_user()
        
        # Szukamy repozytorium, w którym uruchomiona jest ta aplikacja
        # (Uproszczenie: szukamy pierwszego repo, które ma plik app.py i requirements.txt
        #  lub po prostu nazwy repozytorium z URL aplikacji jeśli user wpisze wyżej)
        
        # Najbezpieczniejsza metoda: Szukamy repozytorium o nazwie, którą stworzyłeś.
        # Wstawiam tu pętlę szukającą repozytorium, które ma plik 'app.py'
        # Jeśli masz tylko jedno repozytorium z taką nazwą, to zadziała.
        
        for repo in user.get_repos():
             # Sprawdźmy czy to nasze repo (możesz tu wpisać "grafik" jeśli tak nazwałeś repo)
             # Ale dla uniwersalności spróbujmy zapisać w tym samym, z którego czytamy
             if repo.name.lower() in ["grafik", "urologia", "grafik-urologia", "urologia-grafik", "dyzury"]:
                 return repo
        
        # Jeśli nie znalazł po nazwie, weź pierwsze z brzegu (często działa przy 1 projekcie)
        return user.get_repos()[0]

    except Exception as e:
        st.error(f"Błąd połączenia z GitHubem. Sprawdź token w secrets. Błąd: {e}")
        return None

def load_data():
    """Pobiera plik CSV z GitHuba."""
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
    """Zapisuje (aktualizuje) plik CSV na GitHubie."""
    repo = get_repo()
    if not repo: return False
    
    csv_content = df.to_csv(index=False)
    
    try:
        contents = repo.get_contents(DATA_FILE)
        repo.update_file(contents.path, "Aktualizacja grafiku", csv_content, contents.sha)
        return True
    except:
        try:
            repo.create_file(DATA_FILE, "Init data", csv_content)
            return True
        except Exception as e:
            st.error(f"Nie udało się zapisać: {e}")
            return False

# --- LOGIKA KALENDARZA ---

def get_settlement_period_info(year, month):
    start_month = month if month % 2 != 0 else month - 1
    start_date = datetime.date(year, start_month, 1)
    day_names_pl = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
    return start_date, day_names_pl[start_date.weekday()]

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

def generate_schedule(dates, preferences_df):
    schedule = {} 
    stats = {doc: {'Total': 0, GROUP_MON: 0, GROUP_TUE_WED: 0, GROUP_THU: 0, GROUP_FRI: 0, GROUP_SAT: 0, GROUP_SUN: 0} for doc in DOCTORS}
    weekly_counts = {}

    prefs_map = {}
    if not preferences_df.empty:
        for _, row in preferences_df.iterrows():
            d_str = str(row['Data'])
            if d_str not in prefs_map: prefs_map[d_str] = {}
            prefs_map[d_str][row['Lekarz']] = row['Status']

    # KROK 1: Jakub Sz.
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        if prefs_map.get(d_str, {}).get("Jakub Sz.") == STATUS_FIXED:
            assignee = "Jakub Sz."
            schedule[d_str] = assignee
            stats[assignee]['Total'] += 1
            stats[assignee][get_day_group(d)] += 1
            wk = get_week_key(d)
            if wk not in weekly_counts: weekly_counts[wk] = {}
            weekly_counts[wk][assignee] = weekly_counts[wk].get(assignee, 0) + 1

    # KROK 2: Reszta
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        if d_str in schedule: continue

        candidates = []
        wk = get_week_key(d)
        group = get_day_group(d)

        for doc in DOCTORS:
            if doc == "Jakub Sz.": continue

            status = prefs_map.get(d_str, {}).get(doc, STATUS_AVAILABLE)
            if status == STATUS_UNAVAILABLE: continue

            prev_day = (d - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            if schedule.get(prev_day) == doc: continue

            current_week_count = weekly_counts.get(wk, {}).get(doc, 0)
            if current_week_count >= 2: continue

            weight = 10 if status == STATUS_AVAILABLE else 1
            candidates.append({
                'name': doc,
                'weight': weight,
                'group_count': stats[doc][group],
                'total_count': stats[doc]['Total']
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
    st.header("Konfiguracja")
    pl_months = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
    today = datetime.date.today()
    default_month_idx = (today.month % 12) 
    sel_month_name = st.selectbox("Miesiąc", pl_months, index=default_month_idx)
    sel_month = pl_months.index(sel_month_name) + 1
    sel_year = st.number_input("Rok", 2025, 2030, today.year if today.month < 12 else today.year + 1)
    p_start, p_day = get_settlement_period_info(sel_year, sel_month)
    st.info(f"Okres rozliczeniowy start: {p_start} ({p_day}).")

tab1, tab2 = st.tabs(["📝 Zgłaszanie Dostępności", "⚙️ Generowanie Grafiku"])

with tab1:
    st.subheader("Wybierz lekarza i zaznacz dostępność")
    current_user = st.selectbox("Lekarz:", DOCTORS, index=2)
    dates = [datetime.date(sel_year, sel_month, day) for day in range(1, calendar.monthrange(sel_year, sel_month)[1] + 1)]
    
    df_db = load_data()
    
    table_data = []
    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        status = STATUS_AVAILABLE
        if not df_db.empty:
            record = df_db[(df_db['Data'] == d_str) & (df_db['Lekarz'] == current_user)]
            if not record.empty: status = record.iloc[0]['Status']
        
        day_pl = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"][d.weekday()]
        table_data.append({"Data": d, "Dzień": day_pl, "Status": status})
    
    opts = [STATUS_AVAILABLE, STATUS_RELUCTANT, STATUS_UNAVAILABLE]
    if current_user == "Jakub Sz.": opts = [STATUS_FIXED, STATUS_UNAVAILABLE]

    edited_df = st.data_editor(
        pd.DataFrame(table_data),
        column_config={
            "Data": st.column_config.DateColumn(format="DD.MM.YYYY", disabled=True),
            "Dzień": st.column_config.TextColumn(disabled=True),
            "Status": st.column_config.SelectboxColumn("Decyzja", options=opts, required=True, width="medium")
        },
        hide_index=True, use_container_width=True, height=500
    )
    
    if st.button("💾 Zapisz (GitHub)", type="primary"):
        with st.spinner("Zapisywanie w repozytorium..."):
            new_entries = [{"Data": row['Data'].strftime('%Y-%m-%d'), "Lekarz": current_user, "Status": row['Status']} for _, row in edited_df.iterrows()]
            df_new = pd.DataFrame(new_entries)
            
            if df_db.empty:
                final_df = df_new
            else:
                dates_str = [d.strftime('%Y-%m-%d') for d in dates]
                mask = (df_db['Lekarz'] == current_user) & (df_db['Data'].isin(dates_str))
                final_df = pd.concat([df_db[~mask], df_new], ignore_index=True)
            
            if save_data(final_df):
                st.success("Zapisano! Dane są bezpieczne na GitHubie.")

with tab2:
    if st.button("🚀 UŁÓŻ GRAFIK", type="primary"):
        all_prefs = load_data()
        dates_gen = [datetime.date(sel_year, sel_month, day) for day in range(1, calendar.monthrange(sel_year, sel_month)[1] + 1)]
        schedule_map, stats = generate_schedule(dates_gen, all_prefs)
        
        res_data = [{"Data": d, "Dzień": ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"][d.weekday()], "Dyżurny": schedule_map.get(d.strftime('%Y-%m-%d'), "-")} for d in dates_gen]
        st.dataframe(pd.DataFrame(res_data), use_container_width=True, hide_index=True)
        
        st.write("---")
        stats_rows = [{"Lekarz": doc, "SUMA": s['Total'], **{k:v for k,v in s.items() if k!='Total'}} for doc, s in stats.items()]
        st.dataframe(pd.DataFrame(stats_rows), hide_index=True)
