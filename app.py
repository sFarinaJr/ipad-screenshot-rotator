from flask import Flask
from playwright.sync_api import sync_playwright
import os
import json
from datetime import datetime

app = Flask(__name__)

# Arquivo com a lista de sites (um por linha)
SITES_FILE = 'sites.txt'
STATE_FILE = 'state.json'
SCREENSHOTS_DIR = 'screenshots'

# Carrega os sites do arquivo uma vez ao iniciar a aplicação
def load_sites():
    if not os.path.exists(SITES_FILE):
        raise FileNotFoundError(f"Arquivo {SITES_FILE} não encontrado. Crie-o com um site por linha.")
    with open(SITES_FILE, 'r', encoding='utf-8') as f:
        sites = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    if not sites:
        raise ValueError(f"Arquivo {SITES_FILE} está vazio ou só contém comentários.")
    return sites

sites = load_sites()  # Carrega na inicialização

if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR)

def get_current_index():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                index = data.get('current_index', 0)
                # Proteção: se o arquivo sites.txt mudou e o índice ficou inválido
                return index % len(sites)
        except (json.JSONDecodeError, ValueError):
            pass
    return 0

def save_current_index(index):
    with open(STATE_FILE, 'w') as f:
        json.dump({'current_index': index}, f)

def take_screenshot(url, index):
    try:
        with sync_playwright() as p:
            print(f"Iniciando browser para {url}")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',               # Essencial em containers como Render
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',    # Evita problemas de memória compartilhada
                    '--disable-gpu',              # GPU não disponível no free
                    '--disable-extensions',
                ]
            )
            print("Browser lançado com sucesso")
            context = browser.new_context(
                viewport={'width': 1024, 'height': 768},
                device_scale_factor=1,
                user_agent="Mozilla/5.0 (iPad; CPU OS 9_3_5 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13G36 Safari/601.1",
                java_script_enabled=True,
                bypass_csp=True,
                ignore_https_errors=True,  # Ajuda em sites com SSL issues
            )
            page = context.new_page()
            print(f"Navegando para {url}")
            page.goto(url, wait_until='networkidle', timeout=90000)  # Aumentado para 90s
            print("Página carregada, aguardando extra")
            page.wait_for_timeout(3000)  # Delay extra para JS dinâmico
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshot_{index:02d}_{timestamp}.png"
            path = os.path.join(SCREENSHOTS_DIR, filename)
            page.screenshot(path=path, full_page=False)
            print(f"Screenshot salvo com sucesso: {path}")
    except Exception as e:
        error_msg = f"Erro ao capturar {url}: {str(e)}"
        print(error_msg)  # Isso vai para os logs do Render
        path = None
    finally:
        if 'browser' in locals():
            browser.close()
    return path

@app.route('/trigger')
def trigger():
    current_index = get_current_index()
    url = sites[current_index]
    path = take_screenshot(url, current_index)
    
    next_index = (current_index + 1) % len(sites)
    save_current_index(next_index)
    
    status = "sucesso" if path else "falha"
    return f"[{status}] Screenshot do site {current_index+1}/{len(sites)}: {url} → {path or 'falhou'}"

@app.route('/')
def home():
    return (
        f"Aplicação de screenshots rodando!<br>"
        f"Total de sites: {len(sites)}<br>"
        f"Próximo índice: {get_current_index()}<br>"
        f"Use /trigger para capturar o próximo screenshot.<br>"
        f"Configure cron-job.org para chamar esta URL a cada 5 minutos."
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
