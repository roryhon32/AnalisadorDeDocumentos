#!/usr/bin/env python3
"""
Sistema de integração otimizado para análise de resultados com bot Telegram
Melhorias: Retry, logging estruturado, validação robusta, tratamento de erros
"""
# -*- coding: utf-8 -*-

import os
import sys
import time
import signal
import threading
import subprocess
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime
from dotenv import load_dotenv

# ============================================================================
# LOGGING ESTRUTURADO
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('integracao.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Garante encoding UTF-8 no Windows
if sys.platform == "win32":
    os.system("chcp 65001")

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv('TOKEN')

# ============================================================================
# CONFIGURAÇÕES DE RETRY
# ============================================================================
class RetryConfig:
    """Configuração de retry automático"""
    def __init__(self, max_retries: int = 3, initial_delay: float = 1.0, backoff: float = 2.0):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff = backoff

def retry_with_backoff(config: RetryConfig, name: str = "operação"):
    """Decorator para retry com backoff exponencial"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = config.initial_delay
            last_exception = None
            
            for attempt in range(config.max_retries):
                try:
                    logger.debug(f"🔄 Tentativa {attempt + 1}/{config.max_retries} de {name}")
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < config.max_retries - 1:
                        logger.warning(f"⚠️ Erro em {name} (tentativa {attempt + 1}): {str(e)[:100]}. Aguardando {delay}s...")
                        time.sleep(delay)
                        delay *= config.backoff
                    else:
                        logger.error(f"❌ Falha final em {name} após {config.max_retries} tentativas")
            
            raise last_exception
        return wrapper
    return decorator

# ============================================================================
class IntegratedSystem:
    """Sistema integrado otimizado de monitoramento e bot Telegram"""
    
    def __init__(self):
        self.bot_process = None
        self.monitoring_thread = None
        self.running = True
        self.retry_config = RetryConfig(max_retries=3, initial_delay=1.0, backoff=2.0)
        self.setup_signal_handlers()
        self.last_check_file = Path("bot_data/last_check.json")
        logger.info("🎯 IntegratedSystem inicializado")
    
    def setup_signal_handlers(self):
        """Configura handlers para encerramento gracioso"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handler para sinais de encerramento"""
        logger.info(f"🛑 Recebido sinal {signum}. Encerrando sistema...")
        self.stop()
        sys.exit(0)
    
    def check_dependencies(self) -> bool:
        """Verifica se todas as dependências estão disponíveis"""
        logger.info("🔍 Verificando dependências...")
        
        # Verifica variáveis de ambiente essenciais
        required_env = ['OPENAI_API_KEY', 'TOKEN']
        missing_env = [var for var in required_env if not os.getenv(var)]
        
        if missing_env:
            logger.error(f"Variáveis de ambiente faltando: {', '.join(missing_env)}")
            logger.info("Configure-as no arquivo .env com:")
            logger.info("OPENAI_API_KEY=sua_chave_openai")
            logger.info("TOKEN=seu_token_telegram")
            return False
        
        # Verifica arquivos essenciais
        required_files = {
            'bot.py': 'Bot do Telegram',
            'screnshot.py': 'Sistema de screenshots e monitoramento', 
            'AgenteResumo.py': 'Processador de resumos'
        }
        
        missing_files = []
        for file, desc in required_files.items():
            if not Path(file).exists():
                missing_files.append(f"{file} ({desc})")
                logger.warning(f"Arquivo não encontrado: {file}")
        
        if missing_files:
            logger.error(f"Arquivos faltando: {', '.join(missing_files)}")
            return False
        
        # Testa importações críticas com retry
        imports_to_test = [
            ('telegram', 'python-telegram-bot'),
            ('selenium', 'selenium'),
            ('openai', 'openai'),
        ]
        
        for module, pip_name in imports_to_test:
            try:
                __import__(module)
                logger.info(f"✅ {module} disponível")
            except ImportError:
                logger.error(f"Instale: pip install {pip_name}")
                return False
        
        # Testa jsonToDoc
        try:
            from jsonToDoc import processar_pasta_resultados
            logger.info("✅ jsonToDoc disponível")
        except ImportError as e:
            logger.error(f"jsonToDoc não encontrado: {e}")
            return False
        
        # Cria diretórios necessários
        dirs_to_create = [
            'downloads',
            'resultados_analises', 
            'bot_data',
            'temp_downloads',
            '.cache_processamentos'
        ]
        
        for dir_name in dirs_to_create:
            try:
                Path(dir_name).mkdir(exist_ok=True)
                logger.debug(f"Diretório pronto: {dir_name}")
            except Exception as e:
                logger.error(f"Erro ao criar diretório {dir_name}: {e}")
                return False
        
        logger.info("✅ Todas as dependências estão OK")
        return True
    
    def test_components(self) -> bool:
        """Testa componentes individualmente com retry"""
        logger.info("\n🧪 TESTANDO COMPONENTES...")
        logger.info("-" * 50)
        
        # Testa AgenteResumo
        try:
            from AgenteResumo import ProcessadorFinanceiro, TokenValidator
            processor = ProcessadorFinanceiro(usar_banco_dados=False)
            
            # Testa validador de tokens
            texto_teste = "A" * 1000
            valido, msg = TokenValidator.validar_prompt(texto_teste, "gpt-4o-mini")
            logger.info(f"✅ ProcessadorFinanceiro - {msg}")
        except Exception as e:
            logger.error(f"❌ ProcessadorFinanceiro: {e}")
            return False
        
        # Testa bot com retry
        try:
            from telegram import Bot
            if TOKEN is None:
                raise ValueError("TOKEN do Telegram não está definido no .env")
            
            @retry_with_backoff(RetryConfig(max_retries=2), name="Bot Telegram")
            def test_bot():
                bot = Bot(token=TOKEN)
                return bot
            
            test_bot()
            logger.info("✅ Bot Telegram - OK")
        except Exception as e:
            logger.error(f"❌ Bot Telegram: {e}")
            return False
        
        # Testa Selenium
        try:
            from selenium.webdriver.chrome.options import Options
            options = Options()
            options.add_argument("--headless")
            logger.info("✅ Selenium/Chrome - OK")
        except Exception as e:
            logger.error(f"❌ Selenium/Chrome: {e}")
            return False
        
        logger.info("✅ Todos os componentes testados com sucesso")
        return True
    
    @retry_with_backoff(RetryConfig(max_retries=3, initial_delay=2.0), name="Inicialização do Bot")
    def start_bot(self) -> bool:
        """Inicia o bot do Telegram em processo separado com retry"""
        try:
            logger.info("🤖 Iniciando bot do Telegram...")
            
            # Verifica se já existe processo rodando
            if self.bot_process and self.bot_process.poll() is None:
                logger.info("ℹ️ Bot já está rodando")
                return True
            
            self.bot_process = subprocess.Popen(
                [sys.executable, 'bot.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Monitora saída inicial
            start_time = time.time()
            timeout = 15
            
            while time.time() - start_time < timeout:
                if self.bot_process.poll() is not None:
                    # Processo terminou inesperadamente
                    try:
                        output, _ = self.bot_process.communicate(timeout=2)
                        logger.error(f"Bot falhou ao iniciar:\n{output}")
                    except:
                        pass
                    raise RuntimeError("Bot terminou inesperadamente")
                
                time.sleep(0.5)
            
            logger.info("✅ Bot do Telegram iniciado com sucesso")
            return True
        
        except Exception as e:
            logger.error(f"Erro ao iniciar bot: {e}")
            raise
    
    def save_last_check(self, result: str) -> None:
        """Salva resultado da última verificação"""
        try:
            self.last_check_file.parent.mkdir(exist_ok=True)
            with open(self.last_check_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': time.time(),
                    'result': result[:500],  # Limita tamanho
                    'datetime': datetime.now().isoformat()
                }, f, indent=2)
                logger.debug(f"✅ Última verificação salva")
        except Exception as e:
            logger.warning(f"Erro ao salvar última verificação: {e}")
    
    def load_last_check(self) -> Optional[Dict]:
        """Carrega resultado da última verificação"""
        try:
            if self.last_check_file.exists():
                with open(self.last_check_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Erro ao carregar última verificação: {e}")
        return None
    
    def monitoring_worker(self) -> None:
        """Worker thread para monitoramento periódico com retry"""
        logger.info("📊 Iniciando monitoramento automático...")
        check_interval = 1800  # 30 minutos
        
        while self.running:
            try:
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"🔍 Verificação automática iniciada ({current_time})")
                
                @retry_with_backoff(RetryConfig(max_retries=2), name="Verificação de atualização")
                def verificar():
                    from screnshot import verificar_e_atualizar
                    return verificar_e_atualizar()
                
                try:
                    resultado = verificar()
                    logger.info(f"📊 Resultado: {str(resultado)[:100]}")
                    self.save_last_check(str(resultado))
                    
                    if "Atualizado para" in str(resultado):
                        logger.info("🆕 Novo trimestre detectado!")
                    
                except Exception as e:
                    error_msg = f"Erro na verificação: {e}"
                    logger.error(error_msg)
                    self.save_last_check(error_msg)
                
                # Aguarda próxima verificação
                logger.debug(f"⏰ Próxima verificação em {check_interval//60} minutos")
                for i in range(check_interval):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"❌ Erro crítico no monitoramento: {e}", exc_info=True)
                # Em caso de erro, aguarda menos tempo
                for i in range(300):  # 5 minutos
                    if not self.running:
                        break
                    time.sleep(1)
    
    def start_monitoring(self) -> None:
        """Inicia monitoramento em thread separada"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.warning("⚠️ Monitoramento já está ativo")
            return
        
        self.monitoring_thread = threading.Thread(
            target=self.monitoring_worker,
            daemon=True,
            name="MonitoringThread"
        )
        self.monitoring_thread.start()
        logger.info("✅ Monitoramento iniciado")
    
    def show_status(self) -> None:
        """Mostra status detalhado do sistema"""
        logger.info("\n" + "="*60)
        logger.info("📊 STATUS DO SISTEMA INTEGRADO")
        logger.info("="*60)
        
        # Status do bot
        if self.bot_process:
            if self.bot_process.poll() is None:
                logger.info("🤖 Bot Telegram: ✅ RODANDO")
            else:
                logger.info("🤖 Bot Telegram: ❌ PARADO")
        else:
            logger.info("🤖 Bot Telegram: ❌ NÃO INICIADO")
        
        # Status do monitoramento
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.info("📊 Monitoramento: ✅ ATIVO")
        else:
            logger.info("📊 Monitoramento: ❌ INATIVO")
        
        # Última verificação
        last_check = self.load_last_check()
        if last_check:
            logger.info(f"🕐 Última verificação: {last_check.get('datetime', 'N/A')}")
            logger.info(f"📝 Resultado: {last_check['result'][:80]}...")
        else:
            logger.info("🕐 Última verificação: Nenhuma")
        
        # Informações dos diretórios
        try:
            downloads_dir = Path("downloads")
            if downloads_dir.exists():
                anos = [d for d in downloads_dir.iterdir() if d.is_dir()]
                total_arquivos = 0
                for ano in anos:
                    for trimestre in ano.iterdir():
                        if trimestre.is_dir():
                            arquivos = list(trimestre.glob("*"))
                            total_arquivos += len(arquivos)
                logger.info(f"📁 Downloads: {len(anos)} ano(s), {total_arquivos} arquivo(s)")
            else:
                logger.info("📁 Downloads: 0 arquivos")
            
            resultados_dir = Path("resultados_analises")
            if resultados_dir.exists():
                arquivos = list(resultados_dir.glob("*.json"))
                logger.info(f"📄 Análises: {len(arquivos)} resumo(s) gerado(s)")
            else:
                logger.info("📄 Análises: 0 resumos")
            
            # Status dos assinantes
            subscribers_file = Path("bot_data/subscribers.json")
            if subscribers_file.exists():
                with open(subscribers_file, 'r', encoding='utf-8') as f:
                    subs = json.load(f)
                    logger.info(f"👥 Assinantes: {len(subs)} usuário(s)")
            else:
                logger.info("👥 Assinantes: 0 usuários")
        
        except Exception as e:
            logger.warning(f"Erro ao obter estatísticas: {e}")
        
        logger.info("="*60)
    
    def run(self) -> bool:
        """Executa o sistema completo"""
        logger.info("🚀 INICIANDO SISTEMA INTEGRADO DE ANÁLISE")
        logger.info("="*60)
        logger.info("📊 Positivo Tecnologia - Monitoramento Automático")
        logger.info("🤖 Bot Telegram + Análise de Documentos")
        logger.info("="*60)
        
        # Verifica dependências
        if not self.check_dependencies():
            logger.error("❌ Falha na verificação de dependências")
            return False
        
        # Testa componentes
        if not self.test_components():
            logger.error("❌ Falha no teste de componentes")
            return False
        
        # Inicia bot com retry
        try:
            if not self.start_bot():
                logger.error("❌ Falha ao iniciar bot")
                return False
        except Exception as e:
            logger.error(f"❌ Erro crítico ao iniciar bot: {e}")
            logger.info("Verifique se o TOKEN do Telegram está correto no .env")
            return False
        
        # Inicia monitoramento
        self.start_monitoring()
        
        logger.info("\n✅ SISTEMA COMPLETAMENTE OPERACIONAL")
        logger.info("="*60)
        logger.info("ℹ️ Comandos disponíveis:")
        logger.info("   - 'status': Mostra status do sistema")
        logger.info("   - 'test': Executa verificação manual")
        logger.info("   - 'restart-bot': Reinicia o bot")
        logger.info("   - 'logs': Mostra logs do bot")
        logger.info("   - 'docx': Converte JSONs em DOCX")
        logger.info("   - 'help': Mostra ajuda")
        logger.info("   - 'quit' ou Ctrl+C: Encerra o sistema")
        logger.info("="*60)
        
        # Loop principal para comandos interativos
        try:
            while self.running:
                try:
                    cmd = input("\n🔸 Digite um comando (ou 'quit' para sair): ").strip().lower()
                    
                    if cmd in ['quit', 'exit', 'q']:
                        break
                    elif cmd == 'status':
                        self.show_status()
                    elif cmd == 'test':
                        self.test_system()
                    elif cmd == 'restart-bot':
                        self.restart_bot()
                    elif cmd == 'logs':
                        self.show_bot_logs()
                    elif cmd == 'help':
                        self.show_help()
                    elif cmd == 'docx':
                        self.convert_to_docx()
                    elif cmd:
                        logger.warning(f"❓ Comando desconhecido: {cmd}")
                        logger.info("Digite 'help' para ver comandos disponíveis")
                
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break
        
        finally:
            self.stop()
        
        return True
    
    def restart_bot(self) -> None:
        """Reinicia o bot do Telegram"""
        logger.info("\n🔄 Reiniciando bot...")
        
        # Para o bot atual
        if self.bot_process and self.bot_process.poll() is None:
            self.bot_process.terminate()
            try:
                self.bot_process.wait(timeout=5)
                logger.info("✅ Bot parado graciosamente")
            except subprocess.TimeoutExpired:
                logger.warning("⚡ Forçando encerramento do bot...")
                self.bot_process.kill()
        
        # Inicia novamente
        try:
            if self.start_bot():
                logger.info("✅ Bot reiniciado com sucesso")
            else:
                logger.error("❌ Falha ao reiniciar bot")
        except Exception as e:
            logger.error(f"❌ Erro ao reiniciar: {e}")
    
    def show_bot_logs(self) -> None:
        """Mostra logs do bot"""
        if not self.bot_process:
            logger.warning("❌ Bot não está rodando")
            return
        
        try:
            logger.info("\n📝 LOGS DO BOT:")
            logger.info("-" * 40)
            
            if self.bot_process.poll() is None:
                logger.info("ℹ️ Bot está rodando (logs não disponíveis em tempo real)")
            else:
                try:
                    output, _ = self.bot_process.communicate(timeout=2)
                    if output:
                        lines = output.strip().split('\n')
                        for line in lines[-10:]:
                            logger.info(line)
                    else:
                        logger.info("Nenhum log disponível")
                except subprocess.TimeoutExpired:
                    logger.info("ℹ️ Processo ocupado")
            logger.info("-" * 40)
            
        except Exception as e:
            logger.error(f"❌ Erro ao acessar logs: {e}")
    
    def test_system(self) -> None:
        """Executa teste manual do sistema"""
        logger.info("\n🧪 EXECUTANDO TESTE MANUAL")
        logger.info("-" * 40)
        
        try:
            from screnshot import verificar_e_atualizar
            resultado = verificar_e_atualizar()
            logger.info(f"✅ Teste concluído: {resultado}")
            self.save_last_check(f"TESTE: {resultado}")
            
        except Exception as e:
            error_msg = f"Erro no teste: {e}"
            logger.error(error_msg)
            self.save_last_check(f"TESTE: {error_msg}")
    
    def convert_to_docx(self) -> None:
        """Converte JSONs de análises em DOCX"""
        try:
            logger.info("\n📄 Convertendo JSONs de análises em DOCX...")
            from jsonToDoc import processar_pasta_resultados
            processar_pasta_resultados()
            logger.info("✅ Conversão concluída")
        except Exception as e:
            logger.error(f"❌ Erro na conversão: {e}")
    
    def show_help(self) -> None:
        """Mostra ajuda dos comandos"""
        logger.info("\n📚 COMANDOS DISPONÍVEIS")
        logger.info("-" * 40)
        logger.info("status      - Mostra status detalhado do sistema")
        logger.info("test        - Executa verificação manual")
        logger.info("restart-bot - Reinicia o bot do Telegram") 
        logger.info("logs        - Mostra logs do bot")
        logger.info("docx        - Converte JSONs em DOCX")
        logger.info("help        - Mostra esta ajuda")
        logger.info("quit        - Encerra o sistema")
        logger.info("-" * 40)
    
    def stop(self) -> None:
        """Para o sistema graciosamente"""
        logger.info("\n🛑 Encerrando sistema...")
        self.running = False
        
        # Para o bot
        if self.bot_process and self.bot_process.poll() is None:
            logger.info("⏹️ Parando bot...")
            self.bot_process.terminate()
            
            try:
                self.bot_process.wait(timeout=5)
                logger.info("✅ Bot parado graciosamente")
            except subprocess.TimeoutExpired:
                logger.warning("⚡ Forçando encerramento do bot...")
                self.bot_process.kill()
        
        # Aguarda thread de monitoramento
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.info("⏹️ Parando monitoramento...")
            self.monitoring_thread.join(timeout=2)
            logger.info("✅ Monitoramento parado")
        
        logger.info("✅ Sistema encerrado com sucesso")


def main():
    """Função principal"""
    logger.info("🎯 SISTEMA INTEGRADO DE ANÁLISE DE RESULTADOS")
    logger.info("="*60)
    
    system = IntegratedSystem()
    
    try:
        success = system.run()
        if not success:
            logger.error("❌ Sistema falhou ao inicializar")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("⚡ Interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro crítico: {e}", exc_info=True)
        sys.exit(1)
    finally:
        system.stop()


if __name__ == "__main__":
    main()