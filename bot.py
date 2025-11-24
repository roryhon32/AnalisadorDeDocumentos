import json
import os
import zipfile
from pathlib import Path
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

# Importa funções do seu projeto
from screnshot import verificar_e_atualizar

# Carrega variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("TOKEN")

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


def split_message(text: str, limit: int = MAX_CHARS):
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def load_latest_summary():
    """Carrega o JSON mais recente gerado pelo pipeline de análise."""
    pasta_resultados = Path("resultados_analises")
    arquivos_json = sorted(pasta_resultados.glob("*.json"), reverse=True)

    if not arquivos_json:
        return None, None

    with open(arquivos_json[0], "r", encoding="utf-8") as f:
        dados = json.load(f)

    return arquivos_json[0].name, dados


def get_latest_downloads_info():
    """Busca informações sobre os últimos downloads realizados"""
    try:
        # Busca na pasta downloads a pasta mais recente
        downloads_dir = Path("downloads")
        if not downloads_dir.exists():
            return None
        
        # Encontra o ano mais recente
        anos = sorted([d for d in downloads_dir.iterdir() if d.is_dir()], reverse=True)
        if not anos:
            return None
        
        ano_recente = anos[0]
        
        # Encontra o trimestre mais recente dentro do ano
        trimestres = sorted([d for d in ano_recente.iterdir() if d.is_dir()], 
                          key=lambda x: x.name, reverse=True)
        if not trimestres:
            return None
        
        trimestre_recente = trimestres[0]
        
        # Lista arquivos no trimestre
        arquivos = []
        for arquivo in trimestre_recente.iterdir():
            if arquivo.is_file() and arquivo.suffix.lower() in ['.pdf', '.docx', '.doc']:
                arquivos.append({
                    'nome': arquivo.name,
                    'caminho': str(arquivo),
                    'tamanho': arquivo.stat().st_size,
                    'tipo': arquivo.suffix.lower()
                })
        
        if arquivos:
            return {
                'pasta': str(trimestre_recente),
                'trimestre': trimestre_recente.name,
                'ano': ano_recente.name,
                'arquivos': arquivos
            }
    
    except Exception as e:
        print(f"Erro ao buscar downloads: {e}")
    
    return None


def create_download_zip(download_info):
    """Cria um arquivo ZIP com todos os downloads do trimestre"""
    try:
        if not download_info or not download_info['arquivos']:
            return None
        
        zip_dir = Path("temp_downloads")
        zip_dir.mkdir(exist_ok=True)
        
        trimestre = download_info['trimestre']
        ano = download_info['ano']
        zip_filename = zip_dir / f"resultados_{trimestre}_{ano}.zip"
        
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for arquivo_info in download_info['arquivos']:
                arquivo_path = Path(arquivo_info['caminho'])
                if arquivo_path.exists():
                    # Adiciona arquivo ao ZIP mantendo apenas o nome do arquivo
                    zipf.write(arquivo_path, arquivo_path.name)
        
        if zip_filename.exists() and zip_filename.stat().st_size > 0:
            return str(zip_filename)
    
    except Exception as e:
        print(f"Erro ao criar ZIP: {e}")
    
    return None


def build_more_summaries_text(dados: dict) -> str:
    """Monta um texto com os demais resumos/partes além do executivo."""
    if not dados:
        return ""

    ignore_keys = {"resumo_executivo", "trimestre", "arquivo", "created_at", "timestamp", "status", "pasta"}
    
    partes = []
    
    # Processa arquivos_processados se existir
    if 'arquivos_processados' in dados and isinstance(dados['arquivos_processados'], list):
        partes.append("\n\n— DETALHES POR ARQUIVO —")
        for i, arquivo in enumerate(dados['arquivos_processados'], 1):
            if arquivo.get('status') == 'sucesso' and arquivo.get('resumo'):
                tipo = arquivo.get('tipo', 'documento').replace('_', ' ').title()
                nome_arquivo = Path(arquivo.get('arquivo', '')).name if arquivo.get('arquivo') else f"Arquivo {i}"
                partes.append(f"\n\n{i}. {tipo} ({nome_arquivo}):\n{arquivo['resumo']}")
    
    # Processa outros campos relevantes
    for k, v in dados.items():
        if k in ignore_keys or k == 'arquivos_processados':
            continue
        if not v or (isinstance(v, str) and len(v.strip()) < 10):
            continue
        
        titulo = k.replace("_", " ").title()
        if isinstance(v, (dict, list)):
            try:
                v_text = json.dumps(v, ensure_ascii=False, indent=2)
            except Exception:
                v_text = str(v)
        else:
            v_text = str(v)
        
        partes.append(f"\n\n— {titulo} —\n{v_text}")

    return "".join(partes).strip()


# Funções auxiliares para arquivos JSON
def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# Handlers de comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Eu sou o bot da Central de Resultados da Positivo Tecnologia.\n"
        "Use /help para ver os comandos disponíveis."
    )


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Eu monitoro a Central de Resultados da Positivo Tecnologia. "
        "Quando um novo relatório trimestral for publicado, envio automaticamente "
        "o resumo executivo para assinantes e disponibilizo downloads dos arquivos originais."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandos disponíveis:\n"
        "/start - Inicia o bot\n"
        "/description - Explica o que o bot faz\n"
        "/lastreport - Mostra o último resultado trimestral (interativo)\n"
        "/download - Baixa os arquivos do último trimestre\n"
        "/subscribe - Receber automaticamente novos resumos executivos\n"
        "/unsubscribe - Cancelar notificações automáticas\n"
        "/list_subs - (admin) lista assinantes\n"
        "/status - Verifica status do sistema\n"
        "/docx - Envia os ultimos resumos gerados em Docx\n"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para verificar status do sistema"""
    filename, dados = load_latest_summary()
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
        status_text += f"📋 {len(download_info['arquivos'])} arquivos disponíveis\n"
    else:
        status_text += "❌ Nenhum download encontrado\n"
    
    subs = read_json(SUBSCRIBERS_FILE, [])
    user_id = update.effective_user.id
    if not await is_admin(user_id):  # 🔒 Verifica no .env
        pass
    else:
        status_text += f"👥 Assinantes: {len(subs)}\n"

    await update.message.reply_text(status_text)


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para download dos arquivos do último trimestre"""
    download_info = get_latest_downloads_info()
    
    if not download_info:
        await update.message.reply_text(
            "❌ Nenhum arquivo de download disponível no momento."
        )
        return
    
    await update.message.reply_text("📦 Preparando arquivos para download...")
    
    # Cria ZIP com os arquivos
    zip_path = create_download_zip(download_info)
    
    if not zip_path:
        await update.message.reply_text(
            "❌ Erro ao preparar arquivos para download."
        )
        return
    
    try:
        trimestre = download_info['trimestre']
        ano = download_info['ano']
        
        # Informações sobre os arquivos
        info_text = f"📊 ARQUIVOS DO {trimestre} ({ano})\n\n"
        for arquivo in download_info['arquivos']:
            tamanho_mb = arquivo['tamanho'] / (1024 * 1024)
            info_text += f"📄 {arquivo['nome']} ({tamanho_mb:.1f} MB)\n"
        
        await update.message.reply_text(info_text)
        
        # Envia o arquivo ZIP
        with open(zip_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=Path(zip_path).name,
                caption=f"📦 Arquivos completos do {trimestre} {ano}"
            )
        
        # Remove arquivo temporário
        Path(zip_path).unlink()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar arquivos: {str(e)}")

async def docx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filename, dados = load_latest_summary()
    
    if not dados:
        await update.message.reply_text("⚠️ Nenhum resumo disponível para converter.")
        return
    
    pasta_resultados = Path("resultados_analises")
    json_path = pasta_resultados / filename

    # Define pasta onde estarão os DOCX
    pasta_docx = json_path.parent / f"documentos_{json_path.stem}"

    # Se não existir DOCX, converte
    if not pasta_docx.exists() or not any(pasta_docx.glob("*.docx")):
        await update.message.reply_text("🔄 Convertendo JSON para DOCX...")
        resultado = converter_json_para_docx(str(json_path))
        
        if resultado['status'] != 'sucesso':
            await update.message.reply_text(f"❌ Erro na conversão: {resultado['erro']}")
            return
    
    # Agora envia os DOCX
    arquivos_docx = list(pasta_docx.glob("*.docx"))
    if not arquivos_docx:
        await update.message.reply_text("❌ Nenhum DOCX encontrado após conversão.")
        return
    
    await update.message.reply_text(f"📂 Enviando {len(arquivos_docx)} arquivos DOCX...")
    for docx_file in arquivos_docx:
        with open(docx_file, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=docx_file.name,
                caption=f"📄 {docx_file.name}"
            )

async def lastreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Verificando se há novo trimestre disponível...")

    # Atualiza/detecta novo trimestre
    status = verificar_e_atualizar()

    filename, dados = load_latest_summary()
    if not dados:
        await update.message.reply_text(
            "⚠️ Nenhum resumo encontrado ainda. Tente novamente mais tarde."
        )
        return ConversationHandler.END

    trimestre = dados.get("trimestre", "N/A")
    resumo_exec = dados.get("resumo_executivo") or "Resumo executivo não disponível."

    await update.message.reply_text(f"📊 Último resultado: {trimestre}\n{status}")

    # Envia o resumo executivo (em partes, se necessário)
    for parte in split_message(resumo_exec):
        await update.message.reply_text(parte)

    # Prepara os demais resumos
    outros = build_more_summaries_text(dados)
    
    # Cria botões inline para opções
    keyboard = []
    
    if outros:
        context.user_data["outros_resumos_texto"] = outros
        outros_map = read_json(OUTROS_MAP_FILE, {})
        outros_map[str(update.effective_chat.id)] = {"filename": filename, "outros": outros}
        write_json(OUTROS_MAP_FILE, outros_map)
        keyboard.append([InlineKeyboardButton("📄 Ver resumos detalhados", callback_data="resumos_detalhados")])
    
    # Adiciona botão de download se há arquivos disponíveis
    download_info = get_latest_downloads_info()
    if download_info and download_info['arquivos']:
        keyboard.append([InlineKeyboardButton("📥 Baixar arquivos originais", callback_data="download_arquivos")])
    
    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Escolha uma opção:", 
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("Não há opções adicionais disponíveis.")
    
    return ConversationHandler.END


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula cliques em botões inline"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "resumos_detalhados":
        texto = context.user_data.get("outros_resumos_texto")
        if not texto:
            outros_map = read_json(OUTROS_MAP_FILE, {})
            entry = outros_map.get(str(update.effective_chat.id))
            if entry:
                texto = entry.get("outros")
        
        if texto:
            await query.edit_message_text("📄 Enviando resumos detalhados...")
    
            # 🔧 Adaptado: pegar os arquivos DOCX e enviar manualmente
            filename, dados = load_latest_summary()
            if dados:
                pasta_resultados = Path("resultados_analises")
                json_path = pasta_resultados / filename
                pasta_docx = json_path.parent / f"documentos_{json_path.stem}"
    
                if not pasta_docx.exists() or not any(pasta_docx.glob("*.docx")):
                    resultado = converter_json_para_docx(str(json_path))
                    if resultado['status'] != 'sucesso':
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"❌ Erro na conversão: {resultado['erro']}"
                        )
                        return
                
                arquivos_docx = list(pasta_docx.glob("*.docx"))
                if not arquivos_docx:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ Nenhum DOCX encontrado após conversão."
                    )
                    return
    
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"📂 Enviando {len(arquivos_docx)} arquivos DOCX..."
                )
                for docx_file in arquivos_docx:
                    with open(docx_file, "rb") as f:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,
                            document=f,
                            filename=docx_file.name,
                            caption=f"📄 {docx_file.name}"
                        )
    
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✅ Resumos detalhados enviados!"
            )
        else:
            await query.edit_message_text("❌ Resumos detalhados não encontrados.")
    elif query.data == "download_arquivos":
        await query.edit_message_text("📦 Preparando download...")
        
        download_info = get_latest_downloads_info()
        if not download_info:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Arquivos não disponíveis."
            )
            return
        
        zip_path = create_download_zip(download_info)
        if zip_path:
            try:
                with open(zip_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=Path(zip_path).name,
                        caption=f"📦 Arquivos do {download_info['trimestre']} {download_info['ano']}"
                    )
                Path(zip_path).unlink()
            except Exception as e:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ Erro ao enviar: {str(e)}"
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Erro ao preparar arquivos."
            )


# Handlers de confirmação (mantidos para compatibilidade)
async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resposta = (update.message.text or "").strip().lower()
    
    texto = context.user_data.get("outros_resumos_texto")
    if not texto:
        outros_map = read_json(OUTROS_MAP_FILE, {})
        entry = outros_map.get(str(update.effective_chat.id))
        if entry:
            texto = entry.get("outros")

    if resposta in {"sim", "s", "yes", "y"}:
        if not texto:
            await update.message.reply_text(
                "Ops, não encontrei os demais resumos agora. Tente /lastreport novamente.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END

        for parte in split_message(texto):
            await update.message.reply_text(parte)

        await update.message.reply_text(
            "✅ Enviado!", reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Tudo bem! Se mudar de ideia, é só mandar /lastreport novamente.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def fallback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Fluxo cancelado. Você pode recomeçar com /lastreport.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# Subscribe / Unsubscribe / Job
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = read_json(SUBSCRIBERS_FILE, [])
    if chat_id in subs:
        await update.message.reply_text("Você já está inscrito para receber novos resumos automáticos.")
        return
    subs.append(chat_id)
    write_json(SUBSCRIBERS_FILE, subs)
    await update.message.reply_text(
        "✅ Inscrito com sucesso! Você receberá o resumo executivo automaticamente quando houver novo relatório."
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = read_json(SUBSCRIBERS_FILE, [])
    if chat_id not in subs:
        await update.message.reply_text("Você não estava inscrito.")
        return
    subs.remove(chat_id)
    write_json(SUBSCRIBERS_FILE, subs)
    await update.message.reply_text("✅ Cancelado. Você não receberá mais notificações automáticas.")

async def is_admin(user_id):
    admin_ids = os.getenv("ADMIN_IDS", "")
    admin_list = [int(uid.strip()) for uid in admin_ids.split(",") if uid.strip().isdigit()]
    return user_id in admin_list
async def list_subs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_admin(user_id):  # 🔒 Verifica no .env
        await update.message.reply_text("❌ VOCÊ NÃO TEM PERMISSÃO PARA VER OS IDS.")
        return

    subs = read_json(SUBSCRIBERS_FILE, [])
    await update.message.reply_text(f"Assinantes atuais: {len(subs)} usuários\nIDs: {subs}")

async def send_new_summary_notification():
    """Função para enviar notificação de novo resumo (chamada externamente)"""
    filename, dados = load_latest_summary()
    if not dados:
        return False
    
    # Verifica se já foi enviado
    last = read_json(LAST_SENT_FILE, {})
    if filename == last.get("filename"):
        return False  # Já foi enviado
    
    # Marca como enviado
    write_json(LAST_SENT_FILE, {"filename": filename})
    
    # Prepara conteúdo
    trimestre = dados.get("trimestre", "N/A")
    resumo_exec = dados.get("resumo_executivo") or "Resumo executivo não disponível."
    outros = build_more_summaries_text(dados)
    download_info = get_latest_downloads_info()
    
    # Envia para todos os assinantes
    subs = read_json(SUBSCRIBERS_FILE, [])
    outros_map = read_json(OUTROS_MAP_FILE, {})
    
    success_count = 0
    
    # Esta função precisa ser chamada de dentro do contexto do bot
    # Por isso vou criar uma função que pode ser chamada pelo periodic_check
    return {
        'should_send': True,
        'filename': filename,
        'trimestre': trimestre,
        'resumo_exec': resumo_exec,
        'outros': outros,
        'download_available': bool(download_info and download_info.get('arquivos')),
        'subscribers': subs
    }


async def periodic_check(context: ContextTypes.DEFAULT_TYPE):
    """Função chamada periodicamente pelo job queue."""
    try:
        # Checa se há novo conteúdo
        notification_data = await send_new_summary_notification()
        
        if not notification_data or not notification_data['should_send']:
            return
        
        # Envia para todos os assinantes
        outros_map = read_json(OUTROS_MAP_FILE, {})
        
        for chat_id in notification_data['subscribers']:
            try:
                bot = context.application.bot
                
                # Envia notificação inicial
                await bot.send_message(
                    chat_id=chat_id, 
                    text=f"🆕 NOVO RESULTADO DISPONÍVEL!\n📊 Trimestre: {notification_data['trimestre']}"
                )
                
                # Envia o resumo executivo
                for parte in split_message(notification_data['resumo_exec']):
                    await bot.send_message(chat_id=chat_id, text=parte)
                
                # Prepara botões para ações adicionais
                keyboard = []
                
                if notification_data['outros']:
                    outros_map[str(chat_id)] = {
                        "filename": notification_data['filename'], 
                        "outros": notification_data['outros']
                    }
                    keyboard.append([InlineKeyboardButton("📄 Ver resumos detalhados", callback_data="resumos_detalhados")])
                
                if notification_data['download_available']:
                    keyboard.append([InlineKeyboardButton("📥 Baixar arquivos originais", callback_data="download_arquivos")])
                
                if keyboard:
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await bot.send_message(
                        chat_id=chat_id,
                        text="Opções adicionais:",
                        reply_markup=reply_markup
                    )
                
            except Exception as e:
                print(f"Falha ao enviar para {chat_id}: {e}")
        
        # Salva o mapa atualizado
        write_json(OUTROS_MAP_FILE, outros_map)
        print(f"✅ Notificação enviada para {len(notification_data['subscribers'])} assinantes")
        
    except Exception as e:
        print(f"Erro em periodic_check: {e}")

import threading
import asyncio
import time

def iniciar_verificacao_periodica(app):
    async def loop():
        # espera o bot subir
        await asyncio.sleep(10)
        while True:
            try:
                await periodic_check(app.bot)
            except Exception as e:
                print("Erro no verificador:", e)
            await asyncio.sleep(300)  # 5 minutos

    asyncio.run(loop())
# Função principal do bot
def main():
    app = Application.builder().token(TOKEN).build()

    # Handlers básicos
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

    # Inline buttons
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Conversa do /lastreport
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

    # Handler geral de confirmação
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation))

    # === JOB QUE VERIFICA NOVOS RELATÓRIOS ===
    thread = threading.Thread(target=iniciar_verificacao_periodica, args=(app,), daemon=True)
    thread.start()


    print("🤖 Bot rodando com verificação automática e sistema de downloads...")
    app.run_polling()


if __name__ == "__main__":
    main()