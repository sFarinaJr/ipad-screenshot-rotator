from flask import Flask, send_from_directory
from playwright.sync_api import sync_playwright
import os
import json
from datetime import datetime
import base64
import requests
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# Configurações GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_OWNER = "sfarinajr"
GITHUB_REPO = "ipad-dashboard"

# Configurações de limite e nomes
MAX_SCREENS = 10
GITHUB_FILE_PREFIX = "screenshot-"
GITHUB_FILE_EXT = ".png"
SCREENSHOTS_DIR = 'screenshots'

SITES_FILE = 'sites.txt'
STATE_FILE = 'state.json'

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
        '#onetrust-accept-btn-handler',
        '.cookie-accept',
        '[id*="cookie"][id*="accept"]',
        '[class*="cookie"][class*="accept"]',
    ]

    for selector in common_selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=3000):
                print(f"Cookie banner detectado - clicando em: {selector}")
                button.click(timeout=5000)
                page.wait_for_timeout(2000)
                return True
        except Exception:
            pass
    print("Nenhum banner de cookies detectado ou clicado")
    return False

# ───────────────────────────────────────────────
# Funções auxiliares para gerenciamento no GitHub
# ───────────────────────────────────────────────

def get_github_filename(number: int) -> str:
    return f"{GITHUB_FILE_PREFIX}{number:03d}{GITHUB_FILE_EXT}"

def list_github_screenshots() -> list[int]:
    if not GITHUB_TOKEN:
        return []
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"Não conseguiu listar contents → {resp.status_code}")
            return []
        
        numbers = []
        for item in resp.json():
            name = item.get("name", "")
            if item.get("type") == "file" and name.startswith(GITHUB_FILE_PREFIX) and name.endswith(GITHUB_FILE_EXT):
                try:
                    num_str = name[len(GITHUB_FILE_PREFIX):-len(GITHUB_FILE_EXT)]
                    numbers.append(int(num_str))
                except:
                    pass
        return sorted(numbers)
    except Exception as e:
        print("Erro ao listar arquivos do GitHub:", str(e))
        return []

def delete_oldest_github_screenshot():
    numbers = list_github_screenshots()
    if len(numbers) <= MAX_SCREENS:
        return
    
    oldest = numbers[0]
    filename = get_github_filename(oldest)
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{filename}"
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"Não encontrou arquivo para deletar: {filename}")
            return
        sha = resp.json().get("sha")
        if not sha:
            return
        
        payload = {
            "message": f"Remove screenshot antigo {filename}",
            "sha": sha,
            "committer": {"name": "Render Bot", "email": "render@bot.com"}
        }
        del_resp = requests.delete(api_url, headers=headers, json=payload)
        if del_resp.status_code in (200, 204):
            print(f"Deletado do GitHub: {filename}")
        else:
            print(f"Falha ao deletar {filename}: {del_resp.status_code} - {del_resp.text}")
    except Exception as e:
        print("Erro ao deletar screenshot antigo:", str(e))

# ───────────────────────────────────────────────
# Captura de screenshot + upload + limpeza
# ───────────────────────────────────────────────

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
            page.wait_for_timeout(10000)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            local_filename = f"screenshot_{index:02d}_{timestamp}.png"
            path = os.path.join(SCREENSHOTS_DIR, local_filename)
            page.screenshot(path=path, full_page=False)
            print(f"Screenshot salvo localmente: {path}")

            # Limpeza local - manter apenas as últimas MAX_SCREENS
            all_local = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
            all_local.sort(key=lambda f: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, f)))
            while len(all_local) > MAX_SCREENS:
                to_remove = os.path.join(SCREENSHOTS_DIR, all_local.pop(0))
                try:
                    os.remove(to_remove)
                    print(f"Removido arquivo local antigo: {os.path.basename(to_remove)}")
                except Exception as e:
                    print(f"Erro ao remover {to_remove}: {e}")

            # Upload para GitHub com numeração sequencial
            if GITHUB_TOKEN and os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        content = base64.b64encode(f.read()).decode('utf-8')

                    existing_numbers = list_github_screenshots()
                    next_number = 1 if not existing_numbers else max(existing_numbers) + 1
                    filename = get_github_filename(next_number)

                    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{filename}"
                    headers = {
                        "Authorization": f"Bearer {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"
                    }

                    payload = {
                        "message": f"Adiciona screenshot {filename} - site {index+1}",
                        "content": content,
                        "committer": {"name": "Render Bot", "email": "render@bot.com"}
                    }

                    response = requests.put(api_url, headers=headers, json=payload)
                    if response.status_code in (200, 201):
                        url_img = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/{filename}"
                        print(f"Upload GitHub sucesso: {url_img}")
                        # Controla limite no GitHub
                        delete_oldest_github_screenshot()
                    else:
                        print(f"Falha no upload GitHub: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f"Erro no upload para GitHub: {str(e)}")

            browser.close()

    except Exception as e:
        print(f"Erro ao capturar screenshot de {url}: {str(e)}")
        path = None

    return path

# ───────────────────────────────────────────────
# Scheduler - roda a cada 5 minutos
# ───────────────────────────────────────────────

def scheduled_screenshot():
    current_index = get_current_index()
    url = sites[current_index]
    local_path = take_screenshot(url, current_index)
    
    next_index = (current_index + 1) % len(sites)
    save_current_index(next_index)
    
    status = "sucesso" if local_path else "falha"
    print(f"[SCHEDULER] {status} - Site {current_index+1}/{len(sites)}: {url}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=scheduled_screenshot, trigger="interval", minutes=5)
scheduler.start()

atexit.register(lambda: scheduler.shutdown())

# ───────────────────────────────────────────────
# Rotas Flask
# ───────────────────────────────────────────────

@app.route('/trigger')
def trigger():
    current_index = get_current_index()
    url = sites[current_index]
    local_path = take_screenshot(url, current_index)
    
    next_index = (current_index + 1) % len(sites)
    save_current_index(next_index)
    
    status = "sucesso" if local_path else "falha"
    return f"[{status.upper()}] Site {current_index+1}/{len(sites)}: {url} → {'screenshot salvo e enviado ao GitHub' if local_path else 'falhou'}"

@app.route('/latest-screenshot')
def latest_screenshot():
    files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
    if not files:
        return "Nenhuma screenshot encontrada ainda. Acesse /trigger para gerar.", 404
    
    latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, f)))
    return send_from_directory(SCREENSHOTS_DIR, latest_file, mimetype='image/png')

@app.route('/list-screenshots')
def list_screenshots():
    numbers = list_github_screenshots()
    if not numbers:
        return "Nenhum screenshot encontrado no GitHub ainda."
    
    html = "<h3>Últimas screenshots no GitHub (mais recentes primeiro)</h3><ul>"
    for n in sorted(numbers, reverse=True)[:MAX_SCREENS]:
        filename = get_github_filename(n)
        url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/{filename}"
        html += f'<li><a href="{url}" target="_blank">{filename}</a></li>'
    html += "</ul>"
    return html

@app.route('/')
def home():
    return (
        f"<h3>Aplicação de screenshots cíclicos</h3>"
        f"Total de sites: {len(sites)}<br>"
        f"Próximo índice: {get_current_index()}<br><br>"
        f"<b>Comandos úteis:</b><br>"
        f"• /trigger → captura o próximo site e sobe para o GitHub<br>"
        f"• /latest-screenshot → mostra a screenshot local mais recente<br>"
        f"• /list-screenshots → lista links das últimas imagens no GitHub"
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
