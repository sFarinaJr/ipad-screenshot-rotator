from flask import Flask, send_from_directory
from playwright.sync_api import sync_playwright
import os
import json
from datetime import datetime
import base64
import requests

app = Flask(__name__)

# Configs do GitHub (não mude aqui, usa variável de ambiente)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_OWNER = "sfarinajr"  # seu usuário
GITHUB_REPO = "ipad-dashboard"  # nome do repo do dashboard
GITHUB_FILE_PATH = "latest-screenshot.png"  # nome fixo da imagem (sobrescreve sempre)

# Arquivo com a lista de sites
SITES_FILE = 'sites.txt'
STATE_FILE = 'state.json'
SCREENSHOTS_DIR = 'screenshots'

def load_sites():
    if not os.path.exists(SITES_FILE):
        raise FileNotFoundError(f"Arquivo {SITES_FILE} não encontrado.")
    with open(SITES_FILE, 'r', encoding='utf-8') as f:
        sites = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    if not sites:
        raise ValueError(f"Arquivo {SITES_FILE} vazio.")
    return sites

sites = load_sites()

if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR)

def get_current_index():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('current_index', 0) % len(sites)
        except:
            pass
    return 0

def save_current_index(index):
    with open(STATE_FILE, 'w') as f:
        json.dump({'current_index': index}, f)

def handle_cookie_banner(page):
    """Tenta remover banner de cookies clicando em botões comuns"""
    common_selectors = [
        'button:has-text("Aceitar")',
        'button:has-text("Aceitar todos")',
        'button:has-text("OK")',
        'button:has-text("Continuar")',
        'button:has-text("Allow")',
        'button:has-text("Agree")',
        'button:has-text("Accept all")',
        '[aria-label*="aceitar" i]',
        '[aria-label*="cookies" i] button',
        '#onetrust-accept-btn-handler',  # OneTrust comum
        '.cookie-accept',                # classes comuns
        '[id*="cookie"][id*="accept"]',
        '[class*="cookie"][class*="accept"]',
    ]

    for selector in common_selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=3000):
                print(f"Cookie banner detectado - clicando em: {selector}")
                button.click(timeout=5000)
                page.wait_for_timeout(2000)  # espera 2s para banner sumir
                return True
        except Exception:
            pass  # ignora se não encontrar ou falhar
    
    print("Nenhum banner de cookies detectado ou clicado")
    return False

def take_screenshot(url, index):
    path = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-extensions',
                    '--disable-background-networking',
                    '--disable-sync',
                    '--disable-background-timer-throttling',
                ]
            )
            print("Browser lançado")
            context = browser.new_context(
                viewport={'width': 1024, 'height': 768},
                device_scale_factor=1,
                user_agent="Mozilla/5.0 (iPad; CPU OS 9_3_5 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13G36 Safari/601.1",
                java_script_enabled=True,
                bypass_csp=True,
                ignore_https_errors=True,
            )
            page = context.new_page()
            print(f"Navegando para {url}")
            page.goto(url, wait_until='networkidle', timeout=90000)
            print("Página carregada - tratando banner de cookies")
            handle_cookie_banner(page)
            print("Aguardando 10 segundos extras para conteúdo dinâmico")
            page.wait_for_timeout(10000)  # pausa de 10 segundos
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshot_{index:02d}_{timestamp}.png"
            path = os.path.join(SCREENSHOTS_DIR, filename)
            page.screenshot(path=path, full_page=False)
            print(f"Screenshot salvo localmente: {path}")

            # Upload para GitHub
            if GITHUB_TOKEN and path:
                try:
                    with open(path, 'rb') as f:
                        content = base64.b64encode(f.read()).decode('utf-8')

                    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
                    headers = {
                        "Authorization": f"Bearer {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"
                    }

                    sha = None
                    resp = requests.get(api_url, headers=headers)
                    if resp.status_code == 200:
                        sha = resp.json().get('sha')

                    payload = {
                        "message": "Atualiza screenshot mais recente",
                        "content": content,
                        "sha": sha,
                        "committer": {"name": "Render Bot", "email": "render@bot.com"}
                    }

                    response = requests.put(api_url, headers=headers, json=payload)
                    if response.status_code in (200, 201):
                        url_img = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/{GITHUB_FILE_PATH}"
                        print(f"Upload GitHub sucesso: {url_img}")
                    else:
                        print(f"Falha upload GitHub: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f"Erro upload GitHub: {str(e)}")

    except Exception as e:
        print(f"Erro ao capturar {url}: {str(e)}")
        path = None
    return path

@app.route('/trigger')
def trigger():
    current_index = get_current_index()
    url = sites[current_index]
    local_path = take_screenshot(url, current_index)
    
    next_index = (current_index + 1) % len(sites)
    save_current_index(next_index)
    
    status = "sucesso" if local_path else "falha"
    return f"[{status}] Site {current_index+1}/{len(sites)}: {url} → {'screenshot salvo e enviado ao GitHub' if local_path else 'falhou'}"

@app.route('/latest-screenshot')
def latest_screenshot():
    files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
    if not files:
        return "Nenhuma screenshot encontrada ainda. Acesse /trigger para gerar.", 404
    latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, f)))
    return send_from_directory(SCREENSHOTS_DIR, latest_file, mimetype='image/png')

@app.route('/')
def home():
    return (
        f"Aplicação de screenshots rodando!<br>"
        f"Total de sites: {len(sites)}<br>"
        f"Próximo índice: {get_current_index()}<br>"
        f"Use /trigger para capturar e enviar screenshot para GitHub.<br>"
        f"Use /latest-screenshot para ver a última imagem salva (se existir)."
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
