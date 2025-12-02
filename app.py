import os
import json
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, make_response, redirect, url_for, jsonify
from google.cloud import storage
import yfinance as yf
import pandas as pd

from data_loader import load_ticker_data, get_code_from_keyword

app = Flask(__name__)

# --- Configuration ---
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
CACHE_FILE_NAME = "companydb_posts.json"
CACHE_TTL = 300

# --- Load Data (Execute once at startup) ---
COMPANY_MAP = load_ticker_data()

# --- Fetch YFinance Data ---
def get_stock_data(code):
    try:
        # Get basic info from CSV first
        static_info = COMPANY_MAP.get(code, {})
        
        ticker_symbol = f"{code}.T"
        stock = yf.Ticker(ticker_symbol)
        
        # Financials (Last 4 years)
        financials = stock.financials
        if financials.empty:
            return None

        financials = financials.T
        financials = financials.sort_index(ascending=True)
        
        years, sales, profit, net_income = [], [], [], []

        for date, row in financials.iterrows():
            years.append(date.strftime('%Y'))
            s = row.get('Total Revenue', 0)
            p = row.get('Operating Income', 0)
            n = row.get('Net Income', 0)
            
            sales.append(int(s / 100000000) if not pd.isna(s) else 0)
            profit.append(int(p / 100000000) if not pd.isna(p) else 0)
            net_income.append(int(n / 100000000) if not pd.isna(n) else 0)

        # Merge YFinance and CSV info
        yf_info = stock.info
        company_data = {
            "code": code,
            "name_ja": static_info.get('name_ja', yf_info.get('longName', code)),
            "name_en": static_info.get('name_en', yf_info.get('shortName', code)),
            "market": static_info.get('market', yf_info.get('exchange', 'JPX')),
            "industry": static_info.get('sector', yf_info.get('industry', '-')),
            "years": years,
            "sales": sales,
            "profit": profit,
            "net_income": net_income
        }
        return company_data

    except Exception as e:
        print(f"Error fetching data for {code}: {e}")
        return None

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html', update_date=datetime.now().strftime('%Y/%m/%d'))

@app.route('/search')
def search_handler():
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return redirect(url_for('index'))

    # Use smart search function
    target_code = get_code_from_keyword(keyword, COMPANY_MAP)

    if target_code:
        print(f"Search match: '{keyword}' -> {target_code}") 
        return redirect(url_for('company_detail', code=target_code))
    else:
        print(f"Search failed for: '{keyword}'")
        return render_template('index.html', error="Not Found / 該当する企業が見つかりませんでした。")

@app.route('/company/<code>')
def company_detail(code):
    company = get_stock_data(code)
    if not company:
        return render_template('index.html', error="Data Not Found / データの取得に失敗しました。")
    
    # Link to Starful.biz search
    starful_link = f"https://starful.biz/?q={company['name_ja']}"
    
    return render_template('company.html', company=company, starful_link=starful_link)

@app.route('/sitemap.xml')
def sitemap_xml():
    lastmod = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{request.url_root.rstrip('/')}/</loc><lastmod>{lastmod}</lastmod></url>
</urlset>"""
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)