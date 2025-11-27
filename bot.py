import json
import os
import sys
import time
import zipfile
import logging
import threading
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from jsonToDoc import converter_json_para_docx
from screnshot import verificar_e_atualizar

# ============================================================================
# D) LOGGING ESTRUTURADO
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Garante encoding UTF-8 no Windows
if sys.platform == "win32":
    os.system("chcp 65001")

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

# ============================================================================
# VALIDAÇÃO DE CONFIGURAÇÃO
# ============================================================================
if not TOKEN:
    logger.error("❌ TOKEN do Telegram não configurado no .env")
    sys.exit(1)

logger.info("✅ Bot configurado com sucesso")

# Estados da conversa
AWAIT_CONFIRMATION = 1

# Utilitários
MAX_CHARS = 4000
DATA_DIR = Path("bot_data")
DATA_DIR.mkdir(exist_ok=True)
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
LAST_SENT_FILE = DATA_DIR / "last_sent.json"
OUTROS_MAP_FILE = DATA_DIR / "outros_map.json"
DOWNLOADS_MAP_FILE = DATA_DIR / "downloads_map.json"

# ============================================================================
# B) CONFIGURAÇÃO DE RETRY
# ============================================================================
class RetryConfig:
    """Configuração de retry automático"""
    def __init__(self, max_retries: int = 3, initial_delay: float = 0.5, backoff: float = 2.0):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff = backoff

def retry_with_backoff(config: RetryConfig, name: str = "operação"):
    """Decorator para retry com backoff exponencial"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            delay = config.initial_delay
            last_exception = None
            
            for attempt in range(config.max_retries):
                try:
                    logger.debug(f"🔄 Tentativa {attempt + 1}/{config.max_retries} de {name}")
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < config.max_retries - 1:
                        logger.warning(f"⚠️ Erro em {name} (tentativa {attempt + 1}): {str(e)[:100]}. Aguardando {delay}s...")
                        await asyncio.sleep(delay)
                        delay *= config.backoff
                    else:
                        logger.error(f"❌ Falha final em {name} após {config.max_retries} tentativas")
            
            raise last_exception
        return wrapper
    return decorator

# ============================================================================
# FUNÇÕES AUXILIARES COM MELHOR TRATAMENTO DE ERRO
# ============================================================================
def split_message(text: str, limit: int = MAX_CHARS) -> list:
    """Divide mensagem em partes menores"""
    if not text:
        return ["(vazio)"]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


@retry_with_backoff(RetryConfig(max_retries=2), name="Carregamento de resumo")
async def load_latest_summary() -> tuple:
    """Carrega o JSON mais recente gerado pelo pipeline de análise."""
    try:
        pasta_resultados = Path("resultados_analises")
        if not pasta_resultados.exists():
            logger.warning("Pasta de resultados não encontrada")
            return None, None
        
        arquivos_json = sorted(pasta_resultados.glob("*.json"), reverse=True)
        
        if not arquivos_json:
            logger.warning("Nenhum arquivo JSON encontrado")
            return None, None
        
        arquivo_mais_recente = arquivos_json[0]
        logger.info(f"Carregando: {arquivo_mais_recente.name}")
        
        with open(arquivo_mais_recente, "r", encoding="utf-8") as f:
            dados = json.load(f)
        
        return arquivo_mais_recente.name, dados
    
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro ao carregar resumo: {e}")
        raise


def get_latest_downloads_info() -> dict:
    """Busca informações sobre os últimos downloads realizados"""
    try:
        downloads_dir = Path("downloads")
        if not downloads_dir.exists():
            logger.debug("Diretório de downloads não existe")
            return None
        
        # Encontra o ano mais recente
        anos = sorted([d for d in downloads_dir.iterdir() if d.is_dir()], reverse=True)
        if not anos:
            logger.debug("Nenhum ano encontrado em downloads")
            return None
        
        ano_recente = anos[0]
        
        # Encontra o trimestre mais recente
        trimestres = sorted([d for d in ano_recente.iterdir() if d.is_dir()], 
                          key=lambda x: x.name, reverse=True)
        if not trimestres:
            logger.debug("Nenhum trimestre encontrado")
            return None
        
        trimestre_recente = trimestres[0]
        
        # Lista arquivos
        arquivos = []
        for arquivo in trimestre_recente.iterdir():
            if arquivo.is_file() and arquivo.suffix.lower() in ['.pdf', '.docx', '.doc']:
                arquivos.append({
                    'nome': arquivo.name,
                    'caminho': str(arquivo),
                    'tamanho': arquivo.stat().st_size,
                    'tipo': arquivo.suffix.lower()
                })
        
        if not arquivos:
            logger.debug(f"Nenhum arquivo encontrado em {trimestre_recente}")
            return None
        
        info = {
            'pasta': str(trimestre_recente),
            'trimestre': trimestre_recente.name,
            'ano': ano_recente.name,
            'arquivos': arquivos
        }
        
        logger.info(f"✅ {len(arquivos)} arquivo(s) encontrado(s)")
        return info
    
    except Exception as e:
        logger.error(f"Erro ao buscar downloads: {e}")
        return None


def create_download_zip(download_info: dict) -> str:
    """Cria um arquivo ZIP com todos os downloads do trimestre"""
    try:
        if not download_info or not download_info.get('arquivos'):
            logger.warning("Dados de download inválidos")
            return None
        
        zip_dir = Path("temp_downloads")
        zip_dir.mkdir(exist_ok=True)
        
        trimestre = download_info['trimestre']
        ano = download_info['ano']
        zip_filename = zip_dir / f"resultados_{trimestre}_{ano}.zip"
        
        logger.info(f"Criando ZIP: {zip_filename}")
        
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for arquivo_info in download_info['arquivos']:
                arquivo_path = Path(arquivo_info['caminho'])
                if arquivo_path.exists():
                    zipf.write(arquivo_path, arquivo_path.name)
                    logger.debug(f"  ✓ {arquivo_path.name} adicionado")
        
        tamanho_mb = zip_filename.stat().st_size / (1024 * 1024)
        logger.info(f"✅ ZIP criado ({tamanho_mb:.1f} MB)")
        return str(zip_filename)
    
    except Exception as e:
        logger.error(f"Erro ao criar ZIP: {e}")
        return None


def build_more_summaries_text(dados: dict) -> str:
    """Monta um texto com os demais resumos/partes além do executivo."""
    try:
        if not dados:
            return ""
        
        ignore_keys = {"resumo_executivo", "trimestre", "arquivo", "created_at", "timestamp", "status", "pasta", "arquivos_processados"}
        
        partes = []
        
        # Processa arquivos_processados
        if 'arquivos_processados' in dados and isinstance(dados['arquivos_processados'], list):
            partes.append("\n\n— DETALHES POR ARQUIVO —")
            for i, arquivo in enumerate(dados['arquivos_processados'], 1):
                if arquivo.get('status') == 'sucesso' and arquivo.get('resumo'):
                    tipo = arquivo.get('tipo', 'documento').replace('_', ' ').title()
                    nome_arquivo = Path(arquivo.get('arquivo', '')).name if arquivo.get('arquivo') else f"Arquivo {i}"
                    resumo_trunc = arquivo['resumo'][:500] + "..." if len(arquivo['resumo']) > 500 else arquivo['resumo']
                    partes.append(f"\n\n{i}. {tipo} ({nome_arquivo}):\n{resumo_trunc}")
        
        # Processa outros campos
        for k, v in dados.items():
            if k in ignore_keys or not v:
                continue
            if isinstance(v, str) and len(v.strip()) < 10:
                continue
            
            titulo = k.replace("_", " ").title()
            if isinstance(v, (dict, list)):
                try:
                    v_text = json.dumps(v, ensure_ascii=False, indent=2)[:500]
                except Exception:
                    v_text = str(v)[:500]
            else:
                v_text = str(v)[:500]
            
            partes.append(f"\n\n— {titulo} —\n{v_text}")
        
        return "".join(partes).strip()
    
    except Exception as e:
        logger.warning(f"Erro ao construir outros resumos: {e}")
        return ""


# ============================================================================
# FUNÇÕES JSON COM MELHOR TRATAMENTO
# ============================================================================
def read_json(path: Path, default) -> dict:
    """Lê arquivo JSON com tratamento de erro"""
    try:
        if not path.exists():
            return default
        
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.warning(f"Erro ao parsear {path}, usando padrão")
        return default
    except Exception as e:
        logger.warning(f"Erro ao ler {path}: {e}")
        return default


def write_json(path: Path, obj) -> bool:
    """Escreve arquivo JSON com tratamento de erro"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        logger.debug(f"✅ JSON salvo: {path}")
        return True
    except Exception as e:
        logger.error(f"Erro ao escrever {path}: {e}")
        return False


async def is_admin(user_id: int) -> bool:
    """Verifica se usuário é admin"""
    try:
        admin_ids = [int(uid.strip()) for uid in ADMIN_IDS_STR.split(",") if uid.strip().isdigit()]
        return user_id in admin_ids
    except Exception as e:
        logger.warning(f"Erro ao verificar admin: {e}")
        return False


# ============================================================================
# HANDLERS DE COMANDOS
# ============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    try:
        user = update.effective_user
        logger.info(f"👤 Novo usuário: {user.id} (@{user.username})")
        
        await update.message.reply_text(
            "👋 Olá! Eu sou o bot da Central de Resultados da Positivo Tecnologia.\n"
            "Use /help para ver os comandos disponíveis."
        )
    except Exception as e:
        logger.error(f"Erro em start: {e}")


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /description"""
    try:
        await update.message.reply_text(
            "📊 Eu monitoro a Central de Resultados da Positivo Tecnologia. "
            "Quando um novo relatório trimestral for publicado, envio automaticamente "
            "o resumo executivo para assinantes e disponibilizo downloads dos arquivos originais."
        )
    except Exception as e:
        logger.error(f"Erro em description: {e}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    try:
        help_text = (
            "📚 COMANDOS DISPONÍVEIS:\n\n"
            "/start - Inicia o bot\n"
            "/description - Explica o que o bot faz\n"
            "/lastreport - Mostra o último resultado trimestral\n"
            "/download - Baixa arquivos do último trimestre\n"
            "/subscribe - Recebe novos resumos automaticamente\n"
            "/unsubscribe - Cancela notificações\n"
            "/status - Verifica status do sistema\n"
            "/docx - Envia resumos em DOCX\n"
        )
        
        if await is_admin(update.effective_user.id):
            help_text += "/list_subs - Lista assinantes (ADMIN)\n"
        
        await update.message.reply_text(help_text)
    except Exception as e:
        logger.error(f"Erro em help_command: {e}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /status"""
    try:
        filename, dados = await load_latest_summary()
        download_info = get_latest_downloads_info()
        
        status_text = "📊 STATUS DO SISTEMA\n\n"
        
        if dados:
            trimestre = dados.get("trimestre", "N/A")
            status_text += f"✅ Último resumo: {trimestre}\n"
            status_text += f"📄 Arquivo: {filename}\n"
        else:
            status_text += "❌ Nenhum resumo encontrado\n"
        
        if download_info:
            status_text += f"📁 Últimos downloads: {download_info['trimestre']} ({download_info['ano']})\n"
            status_text += f"📋 {len(download_info['arquivos'])} arquivo(s) disponível(is)\n"
        else:
            status_text += "❌ Nenhum download encontrado\n"
        
        subs = read_json(SUBSCRIBERS_FILE, [])
        
        if await is_admin(update.effective_user.id):
            status_text += f"👥 Assinantes: {len(subs)}\n"
        
        await update.message.reply_text(status_text)
    except Exception as e:
        logger.error(f"Erro em status_command: {e}")
        await update.message.reply_text(f"❌ Erro: {str(e)[:100]}")


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /download"""
    try:
        download_info = get_latest_downloads_info()
        
        if not download_info:
            await update.message.reply_text(
                "❌ Nenhum arquivo de download disponível no momento."
            )
            return
        
        await update.message.reply_text("📦 Preparando arquivos para download...")
        
        zip_path = create_download_zip(download_info)
        
        if not zip_path:
            await update.message.reply_text(
                "❌ Erro ao preparar arquivos para download."
            )
            return
        
        try:
            trimestre = download_info['trimestre']
            ano = download_info['ano']
            
            # Informações
            info_text = f"📊 ARQUIVOS DO {trimestre} ({ano})\n\n"
            for arquivo in download_info['arquivos']:
                tamanho_mb = arquivo['tamanho'] / (1024 * 1024)
                info_text += f"📄 {arquivo['nome']} ({tamanho_mb:.1f} MB)\n"
            
            await update.message.reply_text(info_text)
            
            # Envia ZIP
            with open(zip_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=Path(zip_path).name,
                    caption=f"📦 Arquivos completos do {trimestre} {ano}"
                )
            
            logger.info(f"✅ ZIP enviado a {update.effective_user.id}")
            
            # Remove arquivo
            Path(zip_path).unlink()
            
        except Exception as e:
            logger.error(f"Erro ao enviar ZIP: {e}")
            await update.message.reply_text(f"❌ Erro ao enviar: {str(e)[:100]}")


async def docx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /docx"""
    try:
        await update.message.reply_text("🔄 Processando...")
        
        filename, dados = await load_latest_summary()
        
        if not dados:
            await update.message.reply_text("⚠️ Nenhum resumo disponível.")
            return
        
        pasta_resultados = Path("resultados_analises")
        json_path = pasta_resultados / filename
        pasta_docx = json_path.parent / f"documentos_{json_path.stem}"
        
        # Converte se necessário
        if not pasta_docx.exists() or not any(pasta_docx.glob("*.docx")):
            await update.message.reply_text("⏳ Convertendo JSON para DOCX...")
            resultado = converter_json_para_docx(str(json_path))
            
            if resultado['status'] != 'sucesso':
                await update.message.reply_text(f"❌ Erro: {resultado.get('erro', 'desconhecido')}")
                return
        
        # Envia DOCX
        arquivos_docx = list(pasta_docx.glob("*.docx"))
        if not arquivos_docx:
            await update.message.reply_text("❌ Nenhum DOCX encontrado.")
            return
        
        await update.message.reply_text(f"📂 Enviando {len(arquivos_docx)} arquivo(s)...")
        
        for docx_file in arquivos_docx:
            try:
                with open(docx_file, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=docx_file.name,
                        caption=f"📄 {docx_file.name}"
                    )
            except Exception as e:
                logger.error(f"Erro ao enviar {docx_file.name}: {e}")
        
        logger.info(f"✅ DOCX(s) enviado(s) a {update.effective_user.id}")
    
    except Exception as e:
        logger.error(f"Erro em docx_command: {e}")
        await update.message.reply_text(f"❌ Erro: {str(e)[:100]}")


async def lastreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /lastreport"""
    try:
        await update.message.reply_text("🔎 Verificando se há novo trimestre...")
        
        # Atualiza
        status = verificar_e_atualizar()
        
        filename, dados = await load_latest_summary()
        if not dados:
            await update.message.reply_text(
                "⚠️ Nenhum resumo encontrado ainda. Tente mais tarde."
            )
            return ConversationHandler.END
        
        trimestre = dados.get("trimestre", "N/A")
        resumo_exec = dados.get("resumo_executivo") or "Resumo não disponível."
        
        await update.message.reply_text(f"📊 Último resultado: {trimestre}\n{status}")
        
        # Envia resumo executivo
        for parte in split_message(resumo_exec):
            await update.message.reply_text(parte)
        
        # Prepara outros resumos
        outros = build_more_summaries_text(dados)
        keyboard = []
        
        if outros:
            context.user_data["outros_resumos_texto"] = outros
            outros_map = read_json(OUTROS_MAP_FILE, {})
            outros_map[str(update.effective_chat.id)] = {"filename": filename, "outros": outros}
            write_json(OUTROS_MAP_FILE, outros_map)
            keyboard.append([InlineKeyboardButton("📄 Ver resumos detalhados", callback_data="resumos_detalhados")])
        
        # Download
        download_info = get_latest_downloads_info()
        if download_info and download_info.get('arquivos'):
            keyboard.append([InlineKeyboardButton("📥 Baixar arquivos", callback_data="download_arquivos")])
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Escolha uma opção:", reply_markup=reply_markup)
        
        logger.info(f"✅ Relatório enviado a {update.effective_user.id}")
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Erro em lastreport: {e}")
        await update.message.reply_text(f"❌ Erro: {str(e)[:100]}")
        return ConversationHandler.END


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula cliques em botões inline"""
    query = update.callback_query
    
    try:
        await query.answer()
        
        if query.data == "resumos_detalhados":
            await _enviar_resumos_detalhados(query, context)
        
        elif query.data == "download_arquivos":
            await _enviar_download_arquivos(query, context)
        
        else:
            logger.warning(f"Callback desconhecido: {query.data}")
    
    except Exception as e:
        logger.error(f"Erro em callback: {e}")
        try:
            await query.edit_message_text(f"❌ Erro: {str(e)[:100]}")
        except:
            pass


async def _enviar_resumos_detalhados(query, context):
    """Envia resumos detalhados"""
    try:
        filename, dados = await load_latest_summary()
        if not dados:
            await query.edit_message_text("❌ Resumo não encontrado.")
            return
        
        pasta_resultados = Path("resultados_analises")
        json_path = pasta_resultados / filename
        pasta_docx = json_path.parent / f"documentos_{json_path.stem}"
        
        # Converte se necessário
        if not pasta_docx.exists() or not any(pasta_docx.glob("*.docx")):
            resultado = converter_json_para_docx(str(json_path))
            if resultado['status'] != 'sucesso':
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ Erro: {resultado.get('erro')}"
                )
                return
        
        # Envia DOCX
        arquivos_docx = list(pasta_docx.glob("*.docx"))
        if not arquivos_docx:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ DOCX não encontrado."
            )
            return
        
        await query.edit_message_text(f"📂 Enviando {len(arquivos_docx)} arquivo(s)...")
        
        for docx_file in arquivos_docx:
            with open(docx_file, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=docx_file.name,
                    caption=f"📄 {docx_file.name}"
                )
        
        logger.info(f"✅ Resumos detalhados enviados")
    
    except Exception as e:
        logger.error(f"Erro ao enviar resumos: {e}")


async def _enviar_download_arquivos(query, context):
    """Envia arquivos para download"""
    try:
        download_info = get_latest_downloads_info()
        if not download_info:
            await query.edit_message_text("❌ Arquivos não disponíveis.")
            return
        
        await query.edit_message_text("📦 Preparando...")
        
        zip_path = create_download_zip(download_info)
        if not zip_path:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Erro ao preparar arquivos."
            )
            return
        
        try:
            with open(zip_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=f,
                    filename=Path(zip_path).name,
                    caption=f"📦 {download_info['trimestre']} {download_info['ano']}"
                )
            Path(zip_path).unlink()
            logger.info(f"✅ Download enviado")
        except Exception as e:
            logger.error(f"Erro ao enviar ZIP: {e}")
    
    except Exception as e:
        logger.error(f"Erro em download callback: {e}")


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler de confirmação (legacy)"""
    try:
        resposta = (update.message.text or "").strip().lower()
        
        if resposta in {"sim", "s", "yes", "y"}:
            await update.message.reply_text("✅ OK!", reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text(
                "Tudo bem! Use /lastreport quando quiser.",
                reply_markup=ReplyKeyboardRemove(),
            )
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Erro em handle_confirmation: {e}")
        return ConversationHandler.END


async def fallback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela conversa"""
    try:
        await update.message.reply_text(
            "❌ Cancelado. Use /lastreport para recomeçar.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as e:
        logger.error(f"Erro em fallback_cancel: {e}")
    
    return ConversationHandler.END


# ============================================================================
# ASSINATURAS
# ============================================================================
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /subscribe"""
    try:
        chat_id = update.effective_chat.id
        subs = read_json(SUBSCRIBERS_FILE, [])
        
        if chat_id in subs:
            await update.message.reply_text("✅ Você já está inscrito!")
            return
        
        subs.append(chat_id)
        if write_json(SUBSCRIBERS_FILE, subs):
            await update.message.reply_text(
                "✅ Inscrito! Você receberá novos resumos automaticamente."
            )
            logger.info(f"✅ Novo assinante: {chat_id}")
        else:
            await update.message.reply_text("❌ Erro ao se inscrever.")
    
    except Exception as e:
        logger.error(f"Erro em subscribe: {e}")
        await update.message.reply_text(f"❌ Erro: {str(e)[:100]}")


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /unsubscribe"""
    try:
        chat_id = update.effective_chat.id
        subs = read_json(SUBSCRIBERS_FILE, [])
        
        if chat_id not in subs:
            await update.message.reply_text("❌ Você não estava inscrito.")
            return
        
        subs.remove(chat_id)
        if write_json(SUBSCRIBERS_FILE, subs):
            await update.message.reply_text("✅ Desinscrito!")
            logger.info(f"❌ Assinante removido: {chat_id}")
        else:
            await update.message.reply_text("❌ Erro ao desinscrever.")
    
    except Exception as e:
        logger.error(f"Erro em unsubscribe: {e}")
        await update.message.reply_text(f"❌ Erro: {str(e)[:100]}")


async def list_subs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /list_subs (ADMIN)"""
    try:
        if not await is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sem permissão.")
            logger.warning(f"Tentativa de acesso admin: {update.effective_user.id}")
            return
        
        subs = read_json(SUBSCRIBERS_FILE, [])
        
        if not subs:
            await update.message.reply_text("Nenhum assinante.")
            return
        
        message = f"👥 Assinantes: {len(subs)}\n\n"
        message += "\n".join([f"• {sub_id}" for sub_id in subs])
        
        for parte in split_message(message):
            await update.message.reply_text(parte)
        
        logger.info(f"Lista de assinantes acessada por {update.effective_user.id}")
    
    except Exception as e:
        logger.error(f"Erro em list_subs: {e}")
        await update.message.reply_text(f"❌ Erro: {str(e)[:100]}")


# ============================================================================
# NOTIFICAÇÕES AUTOMÁTICAS
# ============================================================================
async def send_new_summary_notification(app) -> dict:
    """Verifica e prepara notificação de novo resumo"""
    try:
        filename, dados = await load_latest_summary()
        if not dados:
            return None
        
        # Verifica se já foi enviado
        last = read_json(LAST_SENT_FILE, {})
        if filename == last.get("filename"):
            return None  # Já foi enviado
        
        logger.info(f"🆕 Novo resumo detectado: {filename}")
        
        # Marca como enviado
        write_json(LAST_SENT_FILE, {"filename": filename, "timestamp": datetime.now().isoformat()})
        
        return {
            'filename': filename,
            'trimestre': dados.get('trimestre', 'N/A'),
            'resumo_exec': dados.get('resumo_executivo') or "Resumo não disponível.",
            'outros': build_more_summaries_text(dados),
            'download_info': get_latest_downloads_info()
        }
    
    except Exception as e:
        logger.error(f"Erro ao preparar notificação: {e}")
        return None


async def periodic_check(app) -> None:
    """Verifica periodicamente novos resumos"""
    try:
        notification_data = await send_new_summary_notification(app)
        
        if not notification_data:
            return
        
        subs = read_json(SUBSCRIBERS_FILE, [])
        if not subs:
            logger.info("Nenhum assinante para notificar")
            return
        
        logger.info(f"📤 Enviando para {len(subs)} assinante(s)...")
        success_count = 0
        
        for chat_id in subs:
            try:
                # Notificação inicial
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"🆕 NOVO RESULTADO DISPONÍVEL!\n📊 Trimestre: {notification_data['trimestre']}"
                )
                
                # Resumo executivo
                for parte in split_message(notification_data['resumo_exec']):
                    await app.bot.send_message(chat_id=chat_id, text=parte)
                
                # Botões
                keyboard = []
                if notification_data['outros']:
                    keyboard.append([InlineKeyboardButton("📄 Ver detalhes", callback_data="resumos_detalhados")])
                if notification_data['download_info']:
                    keyboard.append([InlineKeyboardButton("📥 Baixar", callback_data="download_arquivos")])
                
                if keyboard:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text="Opções:",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                
                success_count += 1
            
            except Exception as e:
                logger.error(f"Erro ao notificar {chat_id}: {str(e)[:100]}")
        
        logger.info(f"✅ {success_count}/{len(subs)} notificações enviadas")
    
    except Exception as e:
        logger.error(f"Erro crítico em periodic_check: {e}")


async def monitor_loop(app) -> None:
    """Verifica periodicamente novos resumos"""
    logger.info("📊 Iniciando verificação automática...")
    
    while True:
        try:
            await periodic_check(app)
            await asyncio.sleep(300)  # 5 minutos
        except Exception as e:
            logger.error(f"Erro no loop: {e}")
            await asyncio.sleep(60)


def main():
    """Função principal do bot"""
    logger.info("="*60)
    logger.info("🤖 INICIANDO BOT TELEGRAM")
    logger.info("="*60)
    
    try:
        app = Application.builder().token(TOKEN).build()
        
        # Handlers de comando
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("description", description))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("download", download_command))
        app.add_handler(CommandHandler("docx", docx_command))
        
        # Assinaturas
        app.add_handler(CommandHandler("subscribe", subscribe))
        app.add_handler(CommandHandler("unsubscribe", unsubscribe))
        app.add_handler(CommandHandler("list_subs", list_subs))
        
        # Callbacks
        app.add_handler(CallbackQueryHandler(handle_callback_query))
        
        # Conversa /lastreport
        conv = ConversationHandler(
            entry_points=[CommandHandler("lastreport", lastreport)],
            states={
                AWAIT_CONFIRMATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation)
                ]
            },
            fallbacks=[CommandHandler("cancel", fallback_cancel)],
            allow_reentry=True,
        )
        app.add_handler(conv)
        
        # Handler de mensagens genérico (fallback)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation))
        
        # Task de monitoramento
        async def post_init(app):
            asyncio.create_task(monitor_loop(app))
        
        app.post_init = post_init
        
        logger.info("✅ Bot configurado com sucesso")
        logger.info("📊 Monitoramento automático ativo")
        logger.info("="*60)
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    except Exception as e:
        logger.error(f"❌ Erro crítico: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n⏹️ Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro não tratado: {e}", exc_info=True)
        sys.exit(1)