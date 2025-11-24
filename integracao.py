
#!/usr/bin/env python3
"""
Sistema de integração corrigido para análise de resultados com bot Telegram
Corrige problemas de importação, dependências e execução
"""
# -*- coding: utf-8 -*-

import os
import sys
import time
import signal
import threading
import subprocess
import json
from pathlib import Path
from dotenv import load_dotenv
# Garante encoding UTF-8 no terminal do Windows
if sys.platform == "win32":
    os.system("chcp 65001")
# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv('TOKEN')
class IntegratedSystem:
    """Sistema integrado corrigido de monitoramento e bot Telegram"""
    
    def __init__(self):
        self.bot_process = None
        self.monitoring_thread = None
        self.running = True
        self.setup_signal_handlers()
        self.last_check_file = Path("bot_data/last_check.json")
    
    def setup_signal_handlers(self):
        """Configura handlers para encerramento gracioso"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handler para sinais de encerramento"""
        print(f"\n🛑 Recebido sinal {signum}. Encerrando sistema...")
        self.stop()
        sys.exit(0)
    
    def check_dependencies(self):
        """Verifica se todas as dependências estão disponíveis"""
        print("🔍 Verificando dependências...")
        
        # Verifica variáveis de ambiente essenciais
        required_env = ['OPENAI_API_KEY', 'TOKEN']
        missing_env = [var for var in required_env if not os.getenv(var)]
        
        if missing_env:
            print(f"❌ Variáveis de ambiente faltando: {', '.join(missing_env)}")
            print("Configure-as no arquivo .env com:")
            print("OPENAI_API_KEY=sua_chave_openai")
            print("TOKEN=seu_token_telegram")
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
        
        if missing_files:
            print(f"❌ Arquivos faltando: {', '.join(missing_files)}")
            return False
        
        # Testa importações críticas
        try:
            import telegram
            print("✅ python-telegram-bot disponível")
        except ImportError:
            print("❌ Instale: pip install python-telegram-bot")
            return False
        try:
            from jsonToDoc import processar_pasta_resultados
        except ImportError:
            print("❌ jsonToDoc não encontrado. Verifique o arquivo.")
            return False
        try:
            import selenium
            print("✅ selenium disponível")
        except ImportError:
            print("❌ Instale: pip install selenium")
            return False
        
        try:
            import openai
            print("✅ openai disponível")
        except ImportError:
            print("❌ Instale: pip install openai")
            return False
        
        # Cria diretórios necessários
        dirs_to_create = [
            'downloads',
            'resultados_analises', 
            'bot_data',
            'temp_downloads'
        ]
        
        for dir_name in dirs_to_create:
            Path(dir_name).mkdir(exist_ok=True)
        
        print("✅ Todas as dependências estão OK")
        return True
    
    def test_components(self):
        """Testa componentes individualmente"""
        print("\n🧪 TESTANDO COMPONENTES...")
        print("-" * 50)
        
        # Testa AgenteResumo
        try:
            from AgenteResumo import ProcessadorFinanceiro
            processor = ProcessadorFinanceiro(usar_banco_dados=False)
            print("✅ ProcessadorFinanceiro - OK")
        except Exception as e:
            print(f"❌ ProcessadorFinanceiro - Erro: {e}")
            return False
        
        # Testa bot básico
        try:
            from telegram import Bot
            if TOKEN is None:
                raise ValueError("TOKEN do Telegram não está definido. Verifique o arquivo .env.")
            bot = Bot(token=TOKEN)
            print("✅ Bot Telegram - OK")
        except Exception as e:
            print(f"❌ Bot Telegram - Erro: {e}")
            return False
        
        # Testa screenshot (sem execução completa)
        try:
            from selenium.webdriver.chrome.options import Options
            options = Options()
            options.add_argument("--headless")
            print("✅ Selenium/Chrome - OK")
        except Exception as e:
            print(f"❌ Selenium/Chrome - Erro: {e}")
            return False
        
        return True
    
    def start_bot(self):
        """Inicia o bot do Telegram em processo separado"""
        try:
            print(" Iniciando bot do Telegram...")
            
            # Verifica se já existe processo rodando
            if self.bot_process and self.bot_process.poll() is None:
                print(" Bot já está rodando")
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
            while time.time() - start_time < 10:  # Aguarda até 10 segundos
                if self.bot_process.poll() is not None:
                    # Processo terminou
                    output, _ = self.bot_process.communicate()
                    print(f" Bot falhou ao iniciar:")
                    print(output)
                    return False
                
                time.sleep(0.5)
            
            print(" Bot do Telegram iniciado com sucesso")
            return True
        
        except Exception as e:
            print(f" Erro ao iniciar bot: {e}")
            return False
    
    def save_last_check(self, result):
        """Salva resultado da última verificação"""
        try:
            self.last_check_file.parent.mkdir(exist_ok=True)
            with open(self.last_check_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': time.time(),
                    'result': result,
                    'datetime': time.strftime('%Y-%m-%d %H:%M:%S')
                }, f, indent=2)
        except Exception as e:
            print(f"Erro ao salvar última verificação: {e}")
    
    def load_last_check(self):
        """Carrega resultado da última verificação"""
        try:
            if self.last_check_file.exists():
                with open(self.last_check_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None
    
    def monitoring_worker(self):
        """Worker thread para monitoramento periódico"""
        print("📊 Iniciando monitoramento automático...")
        check_interval = 1800  # 30 minutos
        
        while self.running:
            try:
                current_time = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n🔍 Verificação automática iniciada ({current_time})")
                
                # Importa e executa verificação
                try:
                    from screnshot import verificar_e_atualizar
                    resultado = verificar_e_atualizar()
                    print(f"📊 Resultado: {resultado}")
                    
                    # Salva resultado
                    self.save_last_check(resultado)
                    
                    # Se detectou novo trimestre, notifica
                    if "Atualizado para" in str(resultado):
                        print("🆕 Novo trimestre detectado! Notificações automáticas serão enviadas pelo bot.")
                    
                except Exception as e:
                    error_msg = f"Erro na verificação: {e}"
                    print(f"❌ {error_msg}")
                    self.save_last_check(error_msg)
                
                # Aguarda próxima verificação
                print(f"⏰ Próxima verificação em {check_interval//60} minutos")
                for i in range(check_interval):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                print(f"❌ Erro crítico no monitoramento: {e}")
                # Em caso de erro, aguarda menos tempo
                for i in range(300):  # 5 minutos
                    if not self.running:
                        break
                    time.sleep(1)
    
    def start_monitoring(self):
        """Inicia monitoramento em thread separada"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("⚠️ Monitoramento já está ativo")
            return
        
        self.monitoring_thread = threading.Thread(
            target=self.monitoring_worker,
            daemon=True,
            name="MonitoringThread"
        )
        self.monitoring_thread.start()
        print("✅ Monitoramento iniciado")
    
    def show_status(self):
        """Mostra status detalhado do sistema"""
        print("\n" + "="*60)
        print("📊 STATUS DO SISTEMA INTEGRADO")
        print("="*60)
        
        # Status do bot
        if self.bot_process:
            if self.bot_process.poll() is None:
                print("🤖 Bot Telegram: ✅ RODANDO")
            else:
                print("🤖 Bot Telegram: ❌ PARADO")
                try:
                    output, _ = self.bot_process.communicate()
                    if output:
                        print(f"   Última saída: {output[:100]}...")
                except:
                    pass
        else:
            print("🤖 Bot Telegram: ❌ NÃO INICIADO")
        
        # Status do monitoramento
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("📊 Monitoramento: ✅ ATIVO")
        else:
            print("📊 Monitoramento: ❌ INATIVO")
        
        # Última verificação
        last_check = self.load_last_check()
        if last_check:
            print(f"🕐 Última verificação: {last_check['datetime']}")
            print(f"📝 Resultado: {last_check['result'][:80]}...")
        else:
            print("🕐 Última verificação: Nenhuma")
        
        # Informações dos diretórios
        downloads_dir = Path("downloads")
        if downloads_dir.exists():
            anos = [d for d in downloads_dir.iterdir() if d.is_dir()]
            total_arquivos = 0
            for ano in anos:
                for trimestre in ano.iterdir():
                    if trimestre.is_dir():
                        arquivos = list(trimestre.glob("*"))
                        total_arquivos += len(arquivos)
            print(f"📁 Downloads: {len(anos)} ano(s), {total_arquivos} arquivo(s)")
        else:
            print("📁 Downloads: 0 arquivos")
        
        resultados_dir = Path("resultados_analises")
        if resultados_dir.exists():
            arquivos = list(resultados_dir.glob("*.json"))
            print(f"📄 Análises: {len(arquivos)} resumo(s) gerado(s)")
        else:
            print("📄 Análises: 0 resumos")
        
        # Status dos assinantes
        try:
            subscribers_file = Path("bot_data/subscribers.json")
            if subscribers_file.exists():
                with open(subscribers_file, 'r') as f:
                    subs = json.load(f)
                    print(f"👥 Assinantes: {len(subs)} usuário(s)")
            else:
                print("👥 Assinantes: 0 usuários")
        except:
            print("👥 Assinantes: N/A")
        
        print("="*60)
    
    def run(self):
        """Executa o sistema completo"""
        print("🚀 INICIANDO SISTEMA INTEGRADO DE ANÁLISE")
        print("="*60)
        print("📊 Positivo Tecnologia - Monitoramento Automático")
        print("🤖 Bot Telegram + Análise de Documentos")
        print("="*60)
        
        # Verifica dependências
        if not self.check_dependencies():
            print("❌ Falha na verificação de dependências")
            return False
        
        # Testa componentes
        if not self.test_components():
            print("❌ Falha no teste de componentes")
            return False
        
        # Inicia bot
        if not self.start_bot():
            print("❌ Falha ao iniciar bot")
            print("Verifique se o TOKEN do Telegram está correto no .env")
            return False
        
        # Inicia monitoramento
        self.start_monitoring()
        
        print("\n✅ SISTEMA COMPLETAMENTE OPERACIONAL")
        print("="*60)
        print("ℹ️ Comandos disponíveis:")
        print("   - 'status': Mostra status do sistema")
        print("   - 'test': Executa verificação manual")
        print("   - 'restart-bot': Reinicia o bot")
        print("   - 'logs': Mostra logs do bot")
        print("   - 'quit' ou Ctrl+C: Encerra o sistema")
        print("   - 'docx - Converte JSONs de análises em arquivos DOCX")

        print("="*60)
        
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
                        from jsonToDoc import processar_pasta_resultados
                        print("📄 Convertendo JSONs de análises em DOCX...")
                        processar_pasta_resultados()
                    
                    elif cmd:
                        print(f"❓ Comando desconhecido: {cmd}")
                        print("Digite 'help' para ver comandos disponíveis")
                
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break
        
        finally:
            self.stop()
    
    def restart_bot(self):
        """Reinicia o bot do Telegram"""
        print("\n🔄 Reiniciando bot...")
        
        # Para o bot atual
        if self.bot_process and self.bot_process.poll() is None:
            self.bot_process.terminate()
            try:
                self.bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
        
        # Inicia novamente
        if self.start_bot():
            print("✅ Bot reiniciado com sucesso")
        else:
            print("❌ Falha ao reiniciar bot")
    
    def show_bot_logs(self):
        """Mostra logs do bot (últimas linhas)"""
        if not self.bot_process:
            print("❌ Bot não está rodando")
            return
        
        try:
            # Tenta ler stdout do processo
            print("\n📝 LOGS DO BOT (últimas linhas):")
            print("-" * 40)
            
            if self.bot_process.poll() is None:
                print("ℹ️ Bot está rodando (logs não disponíveis em tempo real)")
            else:
                output, _ = self.bot_process.communicate()
                if output:
                    lines = output.strip().split('\n')
                    for line in lines[-10:]:  # Últimas 10 linhas
                        print(line)
                else:
                    print("Nenhum log disponível")
            print("-" * 40)
            
        except Exception as e:
            print(f"❌ Erro ao acessar logs: {e}")
    
    def test_system(self):
        """Executa teste manual do sistema"""
        print("\n🧪 EXECUTANDO TESTE MANUAL")
        print("-" * 40)
        
        try:
            # Importa e executa teste
            from screnshot import verificar_e_atualizar
            resultado = verificar_e_atualizar()
            print(f"✅ Teste concluído: {resultado}")
            
            # Salva resultado do teste
            self.save_last_check(f"TESTE MANUAL: {resultado}")
            
        except Exception as e:
            error_msg = f"Erro no teste: {e}"
            print(f"❌ {error_msg}")
            self.save_last_check(f"TESTE MANUAL: {error_msg}")
    
    def show_help(self):
        """Mostra ajuda dos comandos"""
        print("\n📚 COMANDOS DISPONÍVEIS")
        print("-" * 40)
        print("status      - Mostra status detalhado do sistema")
        print("test        - Executa verificação manual")
        print("restart-bot - Reinicia o bot do Telegram") 
        print("logs        - Mostra logs do bot")
        print("help        - Mostra esta ajuda")
        print("quit        - Encerra o sistema")
        print("-" * 40)
    
    def stop(self):
        """Para o sistema graciosamente"""
        print("\n🛑 Encerrando sistema...")
        self.running = False
        
        # Para o bot
        if self.bot_process and self.bot_process.poll() is None:
            print("⏹️ Parando bot...")
            self.bot_process.terminate()
            
            # Aguarda encerramento gracioso
            try:
                self.bot_process.wait(timeout=5)
                print("✅ Bot parado graciosamente")
            except subprocess.TimeoutExpired:
                print("⚡ Forçando encerramento do bot...")
                self.bot_process.kill()
        
        # Aguarda thread de monitoramento
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("⏹️ Parando monitoramento...")
            self.monitoring_thread.join(timeout=2)
            print("✅ Monitoramento parado")
        
        print("✅ Sistema encerrado com sucesso")


def main():
    """Função principal"""
    print("🎯 SISTEMA INTEGRADO DE ANÁLISE DE RESULTADOS")
    print("="*60)
    
    system = IntegratedSystem()
    
    try:
        success = system.run()
        if not success:
            print("\n❌ Sistema falhou ao inicializar")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚡ Interrompido pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro crítico: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        system.stop()


if __name__ == "__main__":
    main()