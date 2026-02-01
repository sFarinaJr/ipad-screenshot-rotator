from flask import Flask
from playwright.sync_api import sync_playwright
import os
import json
from datetime import datetime

app = Flask(__name__)

sites = [
    "https://www.uol.com.br/",
    "https://www.terra.com.br/",
    "https://cryptobubbles.net/",
    "https://www.msn.com/pt-br",
    "https://www.gazetadigital.com.br/",
    "https://livecoins.com.br/",
    "https://portaldobitcoin.uol.com.br/",
    "https://news.google.com/home?hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://www.r7.com/",
    "https://beta.coin360.com/"
]

STATE_FILE = 'state.json'
SCREENSHOTS_DIR = 'screenshots'

if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR)

def get_current_index():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            return data.get('current_index', 0)
    return 0

def save_current_index(index):
    with open(STATE_FILE, 'w') as f:
        json.dump({'current_index': index}, f)

def take_screenshot(url, index):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1024, 'height': 768},
            device_scale_factor=1,
            user_agent="Mozilla/5.0 (iPad; CPU OS 9_3_5 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13G36 Safari/601.1"
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until='networkidle', timeout=60000)  # Adicionado timeout para sites lentos
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshot_{index}_{timestamp}.png"
            path = os.path.join(SCREENSHOTS_DIR, filename)
            page.screenshot(path=path, full_page=False)
        except Exception as e:
            print(f"Erro ao capturar {url}: {e}")
            path = None  # Ou lide com erro
        browser.close()
    return path

@app.route('/trigger')
def trigger():
    current_index = get_current_index()
    url = sites[current_index]
    path = take_screenshot(url, current_index)
    next_index = (current_index + 1) % len(sites)
    save_current_index(next_index)
    return f"Screenshot taken for {url} and saved to {path}"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
