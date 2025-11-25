# Sistema Integrado de Analise de Resultados + Bot Telegram

> Sistema completo para monitoramento automatico dos resultados trimestrais da Positivo Tecnologia com notificacoes inteligentes via Telegram.

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://core.telegram.org/bots)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-green.svg)](https://openai.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Visao Geral

Este sistema oferece uma solucao completa e automatizada para:
- **Monitoramento em tempo real** dos resultados trimestrais
- **Processamento inteligente** com IA (GPT-4) para analise de conteudo
- **Notificacoes automaticas** via bot do Telegram
- **Interface interativa** com botoes e downloads diretos

### Principais Funcionalidades

- Bot Telegram inteligente com comandos interativos
- Deteccao automatica de novos trimestres usando IA
- Download automatico de documentos (PDFs, DOCX)
- Resumos executivos gerados por IA
- Sistema de notificacoes para multiplos usuarios
- Arquivo ZIP com documentos originais
- Interface responsiva com botoes inline

## Instalacao

### Pre-requisitos

- Python 3.8+
- Google Chrome (para Selenium WebDriver)
- Conta OpenAI com API key
- Bot do Telegram criado via @BotFather

### 1. Clone o repositorio

```bash
git clone https://github.com/roryhon32/AnalisadorDeDocumentos.git
cd sistema-analise-resultados
```

### 2. Instale as dependencias

```bash
pip install -r requirements.txt
```

### 3. Configure as variaveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# OpenAI API Key
OPENAI_API_KEY=sua_chave_openai_aqui

# Token do Bot Telegram
TOKEN=seu_token_bot_telegram_aqui
```

### 4. Estrutura de diretorios

O sistema criara automaticamente os diretorios necessarios:

```
projeto/
├── downloads/           # Arquivos baixados organizados por ano/trimestre
├── resultados_analises/ # JSONs com resumos e analises geradas
├── bot_data/           # Dados persistentes do bot (assinantes)
├── temp_downloads/     # Arquivos ZIP temporarios para download
└── screenshots/        # Screenshots para analise de mudancas
```

## Como Usar

### Opcao 1: Sistema Completo (Recomendado)

```bash
python run_integrated_system.py
```

**O que faz:**
- Inicia o bot do Telegram
- Ativa monitoramento automatico (verificacoes a cada 30 minutos)
- Fornece interface interativa de comandos
- Logs em tempo real

### Opcao 2: Apenas Bot

```bash
python bot.py
```

Inicia apenas o bot do Telegram (sem monitoramento automatico).

### Opcao 3: Verificacao Manual

```bash
python screenshot.py
```

Executa uma verificacao unica para testar o sistema.

## Comandos do Bot

### Para Usuarios

| Comando | Descricao |
|---------|-----------|
| `/start` | Inicia o bot e exibe boas-vindas |
| `/help` | Lista todos os comandos disponiveis |
| `/lastreport` | Mostra o ultimo resultado com botoes interativos |
| `/download` | Baixa ZIP com arquivos do ultimo trimestre |
| `/subscribe` | Inscreve-se para receber notificacoes automaticas |
| `/unsubscribe` | Cancela as notificacoes |
| `/status` | Verifica o status atual do sistema |

### Para Administradores

| Comando | Descricao |
|---------|-----------|
| `/list_subs` | Lista todos os usuarios inscritos |

## Fluxo de Funcionamento

### 1. Monitoramento Inteligente
- Sistema verifica o site da RI automaticamente
- Usa GPT-4 para analisar screenshots e detectar mudancas
- Compara com ultimo trimestre processado

### 2. Download e Processamento
Quando novo trimestre e detectado:
- Baixa automaticamente: Release, Demonstracoes, Transcricao
- Processa documentos com IA para gerar insights
- Salva resultados em formato JSON estruturado

### 3. Notificacoes Automaticas
- Bot envia para todos os assinantes:
  - **Resumo executivo** (principais destaques)
  - **Botoes interativos** para acoes rapidas
  - **Download direto** dos arquivos originais

## Exemplo de Uso

### 1. Usuario se inscreve
```
Usuario: /subscribe
Bot: Inscrito com sucesso! Voce recebera resumos automaticos quando houver novos resultados.
```

### 2. Sistema detecta novo resultado
```
Sistema detecta: 2T25 (anterior: 1T25)
Baixa arquivos automaticamente
Processa com GPT-4
Salva analises em JSON
```

### 3. Notificacao automatica
```
NOVO RESULTADO DISPONIVEL!
Trimestre: 2T25

[Resumo executivo com principais insights]

[Ver analises detalhadas] [Baixar arquivos ZIP]
```

## Configuracoes Avancadas

### Personalizacao do Monitoramento

Voce pode ajustar a frequencia de verificacao editando `run_integrated_system.py`:

```python
# Intervalo entre verificacoes (em segundos)
INTERVALO_VERIFICACAO = 1800  # 30 minutos (padrao)
```

### Customizacao de Prompts

Os prompts da IA podem ser personalizados nos arquivos:
- `screenshot.py` - Prompt para deteccao de novos trimestres
- `bot.py` - Prompts para geracao de resumos

## Logs e Monitoramento

O sistema gera logs detalhados incluindo:
- Status de verificacoes automaticas
- Sucessos/falhas em downloads
- Resultado do processamento com IA
- Estatisticas de notificacoes enviadas
- Erros e warnings com contexto

## Tratamento de Erros

| Cenario | Comportamento |
|---------|---------------|
| **Falha na IA** | Sistema continua, registra erro nos logs |
| **Problema no download** | Nova tentativa na proxima verificacao |
| **Bot offline** | Monitoramento continua, notificacoes em fila |
| **Arquivo corrompido** | Pula arquivo, processa os demais |
| **Limite de API** | Aguarda reset do limite, continua depois |

## Estrutura do Projeto

```
.
├── bot.py                    # Bot do Telegram com todas as funcionalidades
├── screenshot.py             # Monitoramento e deteccao de novos trimestres
├── run_integrated_system.py  # Orquestrador completo do sistema
├── requirements.txt          # Dependencias do projeto
├── .env.example             # Exemplo de configuracao
├── README.md                # Este arquivo
└── docs/                    # Documentacao adicional
    ├── COMMANDS.md          # Referencia completa de comandos
    ├── API.md               # Documentacao da integracao com APIs
    └── TROUBLESHOOTING.md   # Guia de solucao de problemas
```

## Requirements

```txt
python-telegram-bot>=20.0
selenium>=4.0.0
requests>=2.28.0
python-dotenv>=0.19.0
openai>=1.0.0
langchain>=0.1.0
langchain-openai>=0.1.0
langchain-community>=0.0.10
pathlib2>=2.3.6
```

## Contribuindo

1. Faca um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudancas (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## Configuracao do Bot Telegram

### 1. Criar o Bot
1. Abra o Telegram e procure por `@BotFather`
2. Digite `/newbot` e siga as instrucoes
3. Anote o token fornecido
4. Configure o token no arquivo `.env`

### 2. Comandos do Bot (configurar via BotFather)
```
start - Inicia o bot
help - Lista de comandos disponiveis
lastreport - Ultimo resultado disponivel
download - Baixar arquivos do ultimo trimestre
subscribe - Receber notificacoes automaticas
unsubscribe - Cancelar notificacoes
status - Status do sistema
```

## Deploy

### Usando Docker
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Instalar Chrome para Selenium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable

COPY . .
CMD ["python", "run_integrated_system.py"]
```

### Usando Heroku
1. Crie um `Procfile`:
```
worker: python run_integrated_system.py
```

2. Configure as variaveis de ambiente no Heroku:
```bash
heroku config:set OPENAI_API_KEY=sua_chave
heroku config:set TOKEN=seu_token_bot
```

## License

Este projeto esta licenciado sob a MIT License - veja o arquivo [LICENSE](LICENSE) para detalhes.



## Features Futuras

- [ ] Dashboard web para visualizacao de metricas
- [ ] Integracao com outros sistemas de RI
- [X] Analise de sentimento dos resultados
- [X] Comparacoes automaticas entre trimestres
- [ ] Alertas por WhatsApp
- [ ] API REST para integracao externa
- [ ] Machine Learning para previsoes
- [ ] Relatorios em PDF automaticos

---

**Se este projeto foi util, deixe uma estrela no GitHub!**


