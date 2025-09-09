import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from agno.agent import Agent
from agno.media import Image
from agno.models.openai import OpenAIChat
from jsonToDoc import processar_pasta_resultados
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# CORREÇÃO PRINCIPAL: Import correto do agente de resumo

try:
    from AgenteResumo import ProcessadorFinanceiro  # Fallback para versão original
    AGENTE_RESUMO_DISPONIVEL = True
    print("⚠️ Agente Resumo importado com sucesso.")
except ImportError:
    print("❌ AgenteResumo não encontrado. Resumos automáticos não serão gerados.")
    AGENTE_RESUMO_DISPONIVEL = False

load_dotenv()

# Arquivo para persistir o último trimestre
ARQUIVO_TRIMESTRE = "ultimo_trimestre.txt"

def carregar_ultimo_trimestre():
    try:
        if os.path.exists(ARQUIVO_TRIMESTRE):
            with open(ARQUIVO_TRIMESTRE, 'r', encoding='utf-8') as f:
                return f.read().strip()
    except Exception as e:
        print(f"Erro ao carregar último trimestre: {e}")
    return ""

def baixar_e_salvar_pdf(trimestre_detectado):
    """
    Baixa os arquivos e processa automaticamente com o AgenteResumo CORRIGIDO
    """
    print(f"Baixando e salvando PDFs para o trimestre {trimestre_detectado}")
    
    # Extrai ano e trimestre
    try:
        trimestre_num = trimestre_detectado[0]  # "1", "2", "3", "4"
        ano = "20" + trimestre_detectado[2:]    # "2025" de "1T25"
        print(f"Processando trimestre {trimestre_num} do ano {ano}")
    except (IndexError, ValueError) as e:
        print(f"Erro ao processar trimestre {trimestre_detectado}: {e}")
        return False

    # Cria pasta para armazenar os arquivos
    pasta_destino = Path(f"downloads/{ano}/T{trimestre_num}")
    pasta_destino.mkdir(parents=True, exist_ok=True)
    
    # Configuração do Selenium
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    driver = None
    arquivos_baixados = []
    
    try:
        driver = webdriver.Chrome(options=options)
        url = "https://ri.positivotecnologia.com.br/informacoes-ao-mercado/central-de-resultados/"
        driver.get(url)
        
        # Espera a página carregar
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "data"))
        )
        
        # Seleciona o ano correto no dropdown
        try:
            year_select = driver.find_element(By.ID, "fano")
            year_select.click()
            year_option = driver.find_element(By.XPATH, f"//option[@value='{ano}']")
            year_option.click()
            time.sleep(2)
        except Exception as e:
            print(f"Erro ao selecionar ano {ano}: {e}")
        
        # Mapeia os tipos de arquivo que queremos baixar
        tipos_arquivo = {
            "Release de Resultados": "release_resultados",
            "Demonstrações Financeiras": "demonstracoes_financeiras", 
            "Transcrição": "transcricao"
        }
        
        # Procura os links para cada tipo de arquivo
        for tipo_nome, tipo_arquivo in tipos_arquivo.items():
            try:
                # Encontra a linha da tabela para este tipo
                linha = driver.find_element(By.XPATH, f"//td[text()='{tipo_nome}']/parent::tr")
                
                # Encontra o link na coluna do trimestre correto
                coluna_trimestre = int(trimestre_num) + 1
                link_element = linha.find_element(By.XPATH, f".//td[{coluna_trimestre}]//a")
                
                if link_element and "off" not in link_element.get_attribute("class"):
                    link_url = link_element.get_attribute("href")
                    print(f"Encontrado link para {tipo_nome}: {link_url}")
                    
                    # Baixa o arquivo com nome padronizado
                    if tipo_arquivo == "transcricao" and trimestre_detectado == "1T25":
                        nome_arquivo = f"{tipo_arquivo}_{trimestre_detectado}.docx"
                    else:
                        nome_arquivo = f"{tipo_arquivo}_{trimestre_detectado}.pdf"
                    caminho_arquivo = pasta_destino / nome_arquivo
                    
                    if baixar_arquivo(link_url, caminho_arquivo):
                        arquivos_baixados.append({
                            "tipo": tipo_arquivo,
                            "nome": tipo_nome,
                            "caminho": str(caminho_arquivo),
                            "url": link_url,
                            "trimestre": trimestre_detectado,
                            "nome_arquivo": nome_arquivo
                        })
                        print(f"✓ {tipo_nome} baixado: {caminho_arquivo}")
                    else:
                        print(f"✗ Erro ao baixar {tipo_nome}")
                else:
                    print(f"⚠ {tipo_nome} não disponível para {trimestre_detectado}")
                    
            except Exception as e:
                print(f"Erro ao processar {tipo_nome}: {e}")
    
    except Exception as e:
        print(f"Erro geral ao baixar arquivos: {e}")
        return False
    
    finally:
        if driver:
            driver.quit()
    
    # Salva informações no banco de dados
    if arquivos_baixados:
        salvar_no_banco_dados(arquivos_baixados, trimestre_detectado)
        print(f"✓ {len(arquivos_baixados)} arquivos baixados e salvos no banco")
        
        # CORREÇÃO PRINCIPAL: Processamento automático corrigido
        if AGENTE_RESUMO_DISPONIVEL:
            print("\n" + "="*60)
            print(f"🤖 INICIANDO PROCESSAMENTO AUTOMÁTICO - {trimestre_detectado}")
            print("="*60)
            
            resultado_processamento = processar_com_agente_resumo_corrigido(
                pasta_destino, 
                trimestre_detectado, 
                arquivos_baixados
            )
            
            if resultado_processamento:
                print("✅ Processamento automático concluído com sucesso!")
                print(f"📊 Resumo executivo gerado para {trimestre_detectado}")
                return True
            else:
                print("⚠️ Processamento automático falhou, mas arquivos foram baixados")
                return True  # Ainda é sucesso pois os arquivos foram baixados
        
        return True
    else:
        print("⚠ Nenhum arquivo foi baixado")
        return False

def processar_com_agente_resumo_corrigido(pasta_destino, trimestre_detectado, arquivos_baixados):
    """
    VERSÃO TOTALMENTE CORRIGIDA: Usa o ProcessadorFinanceiro corrigido
    """
    try:
        print(f"📄 Iniciando processamento automático dos arquivos do {trimestre_detectado}")
        print(f"📁 Pasta de destino: {pasta_destino}")
        print(f"📋 Arquivos para processar: {len(arquivos_baixados)}")
        
        # CORREÇÃO: Inicializa o processador com tratamento de erro
        try:
            processor = ProcessadorFinanceiro(usar_banco_dados=True)
            print("✅ ProcessadorFinanceiro inicializado")
        except Exception as e:
            print(f"❌ Erro ao inicializar ProcessadorFinanceiro: {e}")
            return False
        
        # CORREÇÃO: Usa o método correto que existe na classe
        print("🚀 Executando processamento completo da pasta...")
        resultado_completo = processor.processar_trimestre_completo(
            str(pasta_destino), 
            trimestre_detectado
        )
        
        # Verifica resultado
        if resultado_completo['status'] == 'sucesso':
            sucessos = [r for r in resultado_completo['arquivos_processados'] if r['status'] == 'sucesso']
            erros = len(resultado_completo['arquivos_processados']) - len(sucessos)
            
            print(f"\n📊 RESULTADOS DO PROCESSAMENTO:")
            print(f"   ✅ Sucessos: {len(sucessos)}")
            print(f"   ❌ Erros: {erros}")
            
            # Exibe resumo executivo se disponível
            if resultado_completo.get('resumo_executivo'):
                print("\n" + "="*60)
                print(f"📊 RESUMO EXECUTIVO - {trimestre_detectado}")
                print("="*60)
                print(resultado_completo['resumo_executivo'])
                print("="*60)
            
            # Log de arquivos processados
            print(f"\n📄 ARQUIVOS PROCESSADOS:")
            for resultado in resultado_completo['arquivos_processados']:
                status_icon = "✅" if resultado['status'] == 'sucesso' else "❌"
                arquivo_nome = Path(resultado['arquivo']).name
                print(f"   {status_icon} {resultado['tipo']}: {arquivo_nome}")
                if resultado['status'] == 'erro':
                    print(f"      💬 Erro: {resultado.get('erro', 'Desconhecido')}")
            
            return len(sucessos) > 0  # Retorna True se pelo menos um arquivo foi processado
        else:
            print(f"❌ Erro no processamento completo: {resultado_completo.get('erro', 'Erro desconhecido')}")
            return False
            
    except Exception as e:
        print(f"❌ Erro crítico no processamento automático: {e}")
        import traceback
        traceback.print_exc()
        return False

def baixar_arquivo(url, caminho_destino):
    """
    Baixa um arquivo da URL especificada para o caminho de destino
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Salva o arquivo
        with open(caminho_destino, 'wb') as f:
            f.write(response.content)
        
        # Verifica se o arquivo foi salvo corretamente
        if caminho_destino.exists() and caminho_destino.stat().st_size > 0:
            return True
        else:
            print(f"Arquivo salvo mas está vazio: {caminho_destino}")
            return False
            
    except requests.RequestException as e:
        print(f"Erro ao baixar arquivo de {url}: {e}")
        return False
    except Exception as e:
        print(f"Erro inesperado ao salvar arquivo: {e}")
        return False

def salvar_no_banco_dados(arquivos_info, ultimo_trimestre):
    """
    Salva as informações dos arquivos no banco de dados
    """
    print("=== INFORMAÇÕES PARA SALVAR NO BANCO ===")
    for arquivo in arquivos_info:
        print(f"Tipo: {arquivo['tipo']}")
        print(f"Nome: {arquivo['nome']}")
        print(f"Trimestre: {arquivo['trimestre']}")
        print(f"Caminho: {arquivo['caminho']}")
        print(f"URL: {arquivo['url']}")
        print(f"Nome do arquivo: {arquivo['nome_arquivo']}")
        print("-" * 50)
    
    # Salva último trimestre em arquivo
    try:
        with open(ARQUIVO_TRIMESTRE, 'w', encoding='utf-8') as f:
            f.write(ultimo_trimestre)
        print(f"Trimestre salvo: {ultimo_trimestre}")
    except Exception as e:
        print(f"Erro ao salvar trimestre: {e}")

def capturar_screenshot(url, nome_arquivo="pagina.png"):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        
        # Espera a página carregar completamente
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Espera adicional para JS renderizar
        time.sleep(5)
        
        # Verifica se o diretório existe, se não, cria
        os.makedirs(os.path.dirname(nome_arquivo) if os.path.dirname(nome_arquivo) else '.', exist_ok=True)
        
        # Tira screenshot
        driver.save_screenshot(nome_arquivo)
        
        # Verifica se o arquivo foi criado
        if not os.path.exists(nome_arquivo):
            raise Exception(f"Screenshot não foi salvo em {nome_arquivo}")
            
        print(f"Screenshot salvo: {nome_arquivo}")
        return nome_arquivo
        
    except Exception as e:
        print(f"Erro ao capturar screenshot: {e}")
        raise e
    finally:
        if driver:
            driver.quit()

def verificar_e_atualizar():
    """
    Função principal que verifica novos trimestres e processa automaticamente
    """
    url = "https://ri.positivotecnologia.com.br/informacoes-ao-mercado/central-de-resultados/"
    
    try:
        screenshot = capturar_screenshot(url)
        
        # Verifica se o arquivo existe
        if not os.path.exists(screenshot):
            print(f"Erro: Arquivo de screenshot não encontrado: {screenshot}")
            return "Erro ao capturar screenshot"

        # CORREÇÃO: Usa modelo correto
        agent = Agent(
            model=OpenAIChat(id="gpt-5-nano"),  # Modelo real
            markdown=True,
        )

        # Converte para Path e cria objeto Image
        image_path = Path(screenshot)
        
        print("Identificando trimestre na imagem...")
        resposta = agent.run(
            "Analise esta captura de tela da Central de Resultados da Positivo Tecnologia. Na tabela, examine CUIDADOSAMENTE cada coluna de trimestre (1T, 2T, 3T, 4T) e identifique os ícones de download. IGNORE qualquer trimestre que tenha ícones CINZAS ou DESATIVADOS. Encontre o trimestre mais alto (maior número) que possui ícones de download ROXOS/AZUIS ATIVOS para qualquer tipo de documento. Se apenas 1T tem downloads ativos, responda 1T25. Se 1T e 2T têm downloads ativos, responda 2T25. Responda APENAS no formato XTY (exemplo: 2T25), sem texto adicional.",
            images=[Image(filepath=image_path)],
        )
        
        # Extrai apenas o conteúdo da resposta
        trimestre_detectado = resposta.content.strip() if resposta and hasattr(resposta, 'content') else ""
        ultimo_trimestre = carregar_ultimo_trimestre()

        print(f"🔍 Trimestre detectado: '{trimestre_detectado}'")
        print(f"🔍 Último trimestre salvo: '{ultimo_trimestre}'")

        if ultimo_trimestre != trimestre_detectado and trimestre_detectado:
            print(f"🆕 Novo trimestre detectado: {trimestre_detectado} (último era {ultimo_trimestre})")
            
            sucesso = baixar_e_salvar_pdf(trimestre_detectado)
            
            if sucesso:
                return f"✅ Atualizado para {trimestre_detectado}. Arquivos baixados e processados automaticamente."
            else:
                return f"⚠️ Trimestre {trimestre_detectado} detectado, mas houve problemas no download."
        else:
            return f"ℹ️ Nenhuma atualização. Último trimestre continua sendo {ultimo_trimestre}."
            
    except Exception as e:
        print(f"❌ Erro na verificação: {e}")
        return f"Erro: {str(e)}"

def testar_captura():
    """Função para testar apenas a captura de screenshot"""
    try:
        url = "https://ri.positivotecnologia.com.br/"
        screenshot = capturar_screenshot(url, "teste_screenshot.png")
        print(f"Teste concluído. Screenshot: {screenshot}")
        print(f"Arquivo existe: {os.path.exists(screenshot)}")
        print(f"Tamanho do arquivo: {os.path.getsize(screenshot) if os.path.exists(screenshot) else 'N/A'} bytes")
        
        # Teste o agente
        agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            markdown=True,
        )
        
        image_path = Path(screenshot)
        
        print("Testando agente com imagem...")
        resposta = agent.run(
            "Descreva brevemente o que você vê nesta imagem",
            images=[Image(filepath=image_path)],
        )
        
        print(f"Resposta: {resposta.content if resposta and hasattr(resposta, 'content') else resposta}")
        
    except Exception as e:
        print(f"Erro no teste: {e}")

def processar_trimestre_manualmente(pasta_trimestre, trimestre):
    """
    CORRIGIDO: Função para processar manualmente um trimestre já baixado
    """
    if not AGENTE_RESUMO_DISPONIVEL:
        print("❌ AgenteResumo não disponível")
        return False
    
    pasta = Path(pasta_trimestre)
    if not pasta.exists():
        print(f"❌ Pasta não encontrada: {pasta}")
        return False
    
    try:
        print(f"📁 Processando manualmente pasta: {pasta}")
        print(f"📋 Trimestre: {trimestre}")
        
        processor = ProcessadorFinanceiro(usar_banco_dados=True)
        resultado = processor.processar_trimestre_completo(str(pasta), trimestre)
        
        if resultado['status'] == 'sucesso':
            print(f"\n📊 RESUMO EXECUTIVO - {trimestre}")
            print("="*60)
            print(resultado.get('resumo_executivo', 'Resumo não disponível'))
            print("="*60)
            
            print(f"\n📄 ARQUIVOS PROCESSADOS:")
            for arquivo in resultado.get('arquivos_processados', []):
                status_icon = "✅" if arquivo['status'] == 'sucesso' else "❌"
                print(f"   {status_icon} {arquivo['tipo']}: {Path(arquivo['arquivo']).name}")
                if arquivo['status'] == 'erro':
                    print(f"      💬 Erro: {arquivo.get('erro', 'Desconhecido')}")
            
            return True
        else:
            print(f"❌ Erro no processamento: {resultado.get('erro', 'Erro desconhecido')}")
            return False
        
    except Exception as e:
        print(f"❌ Erro no processamento manual: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Para testar apenas a captura:
    # testar_captura()
    
    # Para processar manualmente um trimestre já baixado:
    # processar_trimestre_manualmente("downloads/2024/T3", "3T24")
    
    # Execução principal - verifica novos trimestres e processa automaticamente
    resultado = verificar_e_atualizar()
    print("\n" + "="*60)
    print("🎯 Processando resultados para documentos...")
    try:
        processar_pasta_resultados()
        print("✅ Documentos processados com sucesso")
    except Exception as e:
        print(f"❌ Erro ao processar documentos: {e}")
    print(f"\n🎯 RESULTADO FINAL: {resultado}")