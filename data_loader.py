import pandas as pd
import os

# [Manual Aliases] Backup mapping for major companies in case CSV loading fails
MANUAL_ALIASES = {
    # --- Major Global Companies ---
    "sony": "6758",
    "toyota": "7203",
    "nintendo": "7974",
    "softbank": "9984",
    "fast retailing": "9983",
    "uniqlo": "9983",
    "gu": "9983",
    "keyence": "6861",
    "tokyo electron": "8035",
    "hitachi": "6501",
    "mitsubishi": "8058", 
    "mitsubishi corp": "8058",
    "honda": "7267",
    "recruit": "6098",
    "kddi": "9433",
    "shin-etsu": "4063",
    "daikin": "6367",
    "smfg": "8316", 
    "smbc": "8316",
    "mufg": "8306", 
    "mizuho": "8411",
    "japan post": "6178",
    "takeda": "4502",
    "seven": "3382",
    "7-eleven": "3382",
    "fanuc": "6954",
    "denso": "6902",
    "smc": "6273",
    "muji": "7453",
    "jal": "9201",
    "ana": "9202",
    "jr east": "9020",
    "jr central": "9022",
    "jr west": "9021",
    "panasonic": "6752",
    "canon": "7751",
    "bridgestone": "5108",
    "komatsu": "6301",
    "olympus": "7733",
    "fujifilm": "4901",
    "kyocera": "6971",
    "murata": "6981",
    "nidec": "6594",
    "kao": "4452",
    "shiseido": "4911",
    "aeon": "8267",
    "asahi": "2502",
    "kirin": "2503",
    "line": "4689",
    "yahoo": "4689",
    "rakuten": "4755"
}

def load_ticker_data():
    """
    Load Japanese (data_j.csv) and English (data_e.csv) lists and merge them.
    """
    company_map = {}
    
    print("--- Starting Data Load ---")

    # 1. Load Japanese Data (data_j.csv)
    if os.path.exists('data_j.csv'):
        try:
            # Try encoding (utf-8 -> shift-jis)
            try:
                df_j = pd.read_csv('data_j.csv', dtype=str, encoding='utf-8')
            except UnicodeDecodeError:
                df_j = pd.read_csv('data_j.csv', dtype=str, encoding='shift-jis')

            # Use Index instead of Column Names for safety
            # Index 1: Code, Index 2: Name
            for _, row in df_j.iterrows():
                if len(row) < 3: continue

                code = str(row.iloc[1]).strip()
                name = str(row.iloc[2]).strip()
                
                if code and code.isdigit():
                    search_text = f"{code} {name.lower()}"
                    company_map[code] = {
                        'code': code,
                        'name_ja': name,
                        'name_en': name, # Default to Japanese if English missing
                        'search_text': search_text
                    }
            print(f"[OK] Loaded {len(company_map)} Japanese entries.")
        except Exception as e:
            print(f"[Error] Failed to load data_j.csv: {e}")
    else:
        print("[Warning] data_j.csv not found.")

    # 2. Load English Data (data_e.csv)
    if os.path.exists('data_e.csv'):
        try:
            try:
                # Excel CSV usually uses utf-8-sig
                df_e = pd.read_csv('data_e.csv', dtype=str, encoding='utf-8-sig')
            except UnicodeDecodeError:
                try:
                    df_e = pd.read_csv('data_e.csv', dtype=str, encoding='utf-8')
                except:
                    df_e = pd.read_csv('data_e.csv', dtype=str, encoding='shift-jis')

            merged_count = 0
            # Use Index: Index 1=Local Code, Index 2=Name (English)
            for _, row in df_e.iterrows():
                if len(row) < 3: continue 

                code = str(row.iloc[1]).strip()
                name_en = str(row.iloc[2]).strip()

                # Truncate if code > 4 digits
                if len(code) > 4:
                    code = code[:4]

                if code in company_map:
                    company_map[code]['name_en'] = name_en
                    # Add English name to search text
                    company_map[code]['search_text'] += f" {name_en.lower()}"
                    merged_count += 1
            
            print(f"[OK] Merged {merged_count} English names.")
            
        except Exception as e:
            print(f"[Error] Failed to load data_e.csv: {e}")
    else:
        print("[Warning] data_e.csv not found. Using manual aliases only.")
            
    return company_map

def get_code_from_keyword(keyword, company_map):
    if not keyword:
        return None
        
    keyword_norm = keyword.lower().strip()

    # 1. Direct Code Search
    if keyword_norm.isdigit():
        if keyword_norm in company_map:
            return keyword_norm
            
    # 2. Manual Alias Search (High Priority)
    if keyword_norm in MANUAL_ALIASES:
        return MANUAL_ALIASES[keyword_norm]

    # 3. Name Search (Japanese or English partial match)
    for code, info in company_map.items():
        if keyword_norm in info.get('search_text', ''):
            return code
            
    return None