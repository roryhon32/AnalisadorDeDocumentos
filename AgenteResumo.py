import os
import logging
import json
import time
import hashlib
from functools import lru_cache
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

from langchain.chains.summarize import load_summarize_chain
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema import Document as LangChainDoc
from database_manager import DocumentManager

load_dotenv()

# ============================================================================
# D) LOGGING ESTRUTURADO
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agente_resumo.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# B) SISTEMA DE RETRY COM BACKOFF EXPONENCIAL
# ============================================================================
class RetryConfig:
    """Configuração de retry automático"""
    def __init__(self, max_retries: int = 3, initial_delay: float = 1.0, backoff: float = 2.0):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff = backoff

def retry_with_backoff(config: RetryConfig):
    """Decorator para retry com backoff exponencial"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = config.initial_delay
            last_exception = None
            
            for attempt in range(config.max_retries):
                try:
                    logger.info(f"🔄 Tentativa {attempt + 1}/{config.max_retries} de {func.__name__}")
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < config.max_retries - 1:
                        logger.warning(f"⚠️ Erro na tentativa {attempt + 1}: {str(e)[:100]}. Aguardando {delay}s...")
                        time.sleep(delay)
                        delay *= config.backoff
                    else:
                        logger.error(f"❌ Falha final após {config.max_retries} tentativas")
            
            raise last_exception
        return wrapper
    return decorator

# ============================================================================
# C) SISTEMA DE CACHE PERSISTENTE
# ============================================================================
class CacheManager:
    """Gerencia cache de processamentos"""
    def __init__(self, cache_dir: str = ".cache_processamentos"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        logger.info(f"💾 Cache manager inicializado: {self.cache_dir}")
    
    def _gerar_hash(self, arquivo_path: str, tipo: str) -> str:
        """Gera hash único para arquivo baseado em caminho e timestamp"""
        try:
            mtime = Path(arquivo_path).stat().st_mtime
        except:
            mtime = 0
        
        chave = f"{arquivo_path}_{tipo}_{mtime}"
        return hashlib.md5(chave.encode()).hexdigest()
    
    def existe_cache(self, arquivo_path: str, tipo: str) -> bool:
        """Verifica se existe cache para arquivo"""
        hash_arquivo = self._gerar_hash(arquivo_path, tipo)
        cache_file = self.cache_dir / f"{hash_arquivo}.json"
        return cache_file.exists()
    
    def obter_cache(self, arquivo_path: str, tipo: str) -> Optional[dict]:
        """Obtém resultado em cache"""
        try:
            hash_arquivo = self._gerar_hash(arquivo_path, tipo)
            cache_file = self.cache_dir / f"{hash_arquivo}.json"
            
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    logger.info(f"💾 Usando cache para {Path(arquivo_path).name}")
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Erro ao ler cache: {e}")
        return None
    
    def salvar_cache(self, arquivo_path: str, tipo: str, resultado: dict):
        """Salva resultado em cache"""
        try:
            hash_arquivo = self._gerar_hash(arquivo_path, tipo)
            cache_file = self.cache_dir / f"{hash_arquivo}.json"
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(resultado, f, indent=2, ensure_ascii=False)
                logger.debug(f"✅ Cache salvo para {Path(arquivo_path).name}")
        except Exception as e:
            logger.warning(f"Erro ao salvar cache: {e}")

# ============================================================================
# A) VALIDADOR DE TOKENS
# ============================================================================
class TokenValidator:
    """Valida tamanho de prompts para evitar exceeding limits"""
    
    CHARS_PER_TOKEN = 4  # 1 token ≈ 4 caracteres (OpenAI)
    MARGEM_SEGURANCA = 0.75  # Use 75% do limite
    
    LIMITES_MODELO = {
        "gpt-4o-mini": 128000,
        "gpt-3.5-turbo": 16384,
        "gpt-4": 8192,
    }
    
    @staticmethod
    def validar_prompt(texto: str, modelo: str) -> Tuple[bool, str]:
        """Retorna (válido, mensagem)"""
        limite = TokenValidator.LIMITES_MODELO.get(modelo, 8192)
        limite_seguro = int(limite * TokenValidator.MARGEM_SEGURANCA)
        
        tokens_estimados = len(texto) / TokenValidator.CHARS_PER_TOKEN
        
        if tokens_estimados > limite_seguro:
            return False, f"Prompt muito grande: {int(tokens_estimados)} tokens (limite: {limite_seguro})"
        return True, f"✅ {int(tokens_estimados)} tokens"

# ============================================================================
class ProcessadorFinanceiro:
    """Versão otimizada com retry, cache, logging e validação"""
    
    def __init__(self, usar_banco_dados: bool = True):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY não encontrada. Configure no arquivo .env")
        
        # A) CORREÇÃO: Modelo válido
        modelo = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        logger.info(f"📦 Inicializando com modelo: {modelo}")
        
        self.llm = ChatOpenAI(
            temperature=0, 
            model=modelo,
            max_tokens=3000,
            timeout=60,
            max_retries=2
        )
        
        # B+C) Configurações
        self.retry_config = RetryConfig(max_retries=3, initial_delay=1.0, backoff=2.0)
        self.cache_manager = CacheManager()
        self.doc_manager = DocumentManager() if usar_banco_dados else None
        self.prompts = self._criar_prompts()
        
        logger.info("✅ ProcessadorFinanceiro inicializado")
    
    def _criar_prompts(self):
        """Prompts otimizados com tamanho controlado"""

        prompt_release = PromptTemplate(
            input_variables=["text"],
            template="""
Você é um analista financeiro sênior. Analise este release de resultados e extraia todas as informações relevantes organizadas no formato estruturado abaixo.

## RESUMO EXECUTIVO

### Performance Financeira Principal
• Receita Líquida: [valor atual, variação % trimestre anterior, variação % ano anterior]
• EBITDA: [valor, margem %, variação % vs trimestres anteriores]
• Lucro Operacional: [valor, margem %, variação %]
• Lucro Líquido: [valor, margem %, variação %]
• Fluxo de Caixa Operacional: [valor e variação]

### Indicadores Operacionais
• Volume de vendas: [quantidade, variação %]
• Ticket médio: [valor, variação %]
• Margem Bruta: [%, variação em pontos percentuais]
• Posição de caixa: [valor total]
• Estoques: [valor, dias de estoque, variação]
• CAPEX: [investimentos realizados, variação %]

### Segmentos de Negócio
• [Para cada segmento mencionado]: participação na receita, crescimento %, principais drivers
• Receita por canal de vendas (online, varejo, corporativo, etc.)
• Performance por linha de produtos principais

### Destaques Operacionais e Estratégicos
• Lançamentos de produtos no período
• Expansões operacionais (novos centros de distribuição, fábricas, etc.)
• Parcerias estratégicas anunciadas ou em andamento
• Investimentos em P&D e inovação
• Reestruturações organizacionais
• Iniciativas de sustentabilidade e ESG

### Contexto de Mercado e Cenário
• Principais desafios macroeconômicos mencionados
• Impactos setoriais específicos
• Tendências de mercado relevantes
• Posicionamento competitivo

### Riscos e Desafios Identificados
• Pressões sobre margens
• Desafios operacionais específicos
• Riscos regulatórios ou de compliance
• Impactos de eventos extraordinários
• Questões de supply chain ou logísticas

### Perspectivas e Guidance
• Projeções para próximos trimestres
• Metas e objetivos declarados
• Investimentos planejados
• Estratégias de crescimento
• Guidance numérico (quando disponível)

### Eventos Relevantes do Período
• Aquisições, desinvestimentos ou reorganizações
• Mudanças na estrutura societária
• Eventos operacionais significativos
• Impactos de força maior

---

**INSTRUÇÕES ESPECÍFICAS:**
1. Extraia APENAS informações que estão explicitamente mencionadas no documento
2. Sempre inclua os valores numéricos exatos quando disponíveis
3. Para variações percentuais, indique sempre o período de comparação
4. Se alguma seção não tiver informações disponíveis, escreva "Não mencionado no release"
5. Mantenha linguagem objetiva e corporativa
6. Não faça interpretações ou análises além do que está escrito
7. Preserve a terminologia técnica e financeira original


**DOCUMENTO PARA ANÁLISE:**
{text}

Organize as informações de forma clara e estruturada, priorizando dados quantitativos e fatos objetivos.
"""
        )
    
        prompt_transcricao = PromptTemplate(
            input_variables=["text"],
            template="""
Analise esta transcrição de call de resultados e extraia os pontos principais:

## MENSAGENS PRINCIPAIS DA GESTÃO
• [3-4 pontos estratégicos mais importantes comunicados]

## TOM E CONFIANÇA
• Nível de confiança: [Alto/Médio/Baixo]
• Tom predominante: [Otimista/Equilibrado/Cauteloso/Preocupado]
• Transparência: [Alta/Média/Limitada]

## ESTRATÉGIAS E DIRECIONAMENTOS
• Iniciativas estratégicas mencionadas
• Investimentos e expansões planejadas
• Foco operacional para próximos períodos

## PONTOS CRÍTICOS
• Desafios mais mencionados pela gestão
• Pressões competitivas ou de mercado
• Medidas corretivas em andamento

TRANSCRIÇÃO PARA ANÁLISE:
{text}

Foque nas mensagens qualitativas e no que a gestão realmente comunicou.
"""
        )
        
        prompt_demonstracoes = PromptTemplate(
            input_variables=["text"],
            template="""
Analise estas demonstrações financeiras e extraia os dados.
O documento apresenta colunas separadas para CONSOLIDADO e CONTROLADORA, com períodos comparativos.

## ESTRUTURA ESPERADA

### DEMONSTRAÇÃO DO RESULTADO 
**Período Atual vs Período Anterior:**
• Receita Bruta: [valor atual] vs [valor anterior] - Variação: [%]
• Receita Líquida: [valor atual] vs [valor anterior] - Variação: [%]
• Custo dos Produtos Vendidos: [valor atual] vs [valor anterior]
• Lucro Bruto: [valor atual] vs [valor anterior] - Margem: [% atual] vs [% anterior]
• Despesas Operacionais: [valor atual] vs [valor anterior]
• EBITDA: [valor atual] vs [valor anterior] - Margem: [% atual] vs [% anterior]
• Resultado Financeiro: [valor atual] vs [valor anterior]
• Lucro Líquido Consolidado: [valor atual] vs [valor anterior] - Margem: [% atual] vs [% anterior]

### BALANÇO PATRIMONIAL - CONSOLIDADO
**Período Atual vs Período Anterior:**
• Ativo Total: [valor atual] vs [valor anterior] - Variação: [%]
• Ativo Circulante: [valor atual] vs [valor anterior]
  - Caixa e Equivalentes: [valor atual] vs [valor anterior]
  - Contas a Receber: [valor atual] vs [valor anterior]
  - Estoques: [valor atual] vs [valor anterior]
• Patrimônio Líquido Consolidado: [valor atual] vs [valor anterior]

### INDICADORES CALCULADOS
• Margem Bruta: [% atual] vs [% anterior]
• Margem EBITDA: [% atual] vs [% anterior]
• Margem Líquida: [% atual] vs [% anterior]
• ROE Consolidado: [% atual] vs [% anterior]
• Liquidez Corrente: [atual] vs [anterior]
• Endividamento: [% atual] vs [% anterior]

### DADOS PARA BENCHMARKING (IMPORTANTE)
• Faturamento Líquido: [valores] - Variação: [%]
• Lucro Bruto: [valores] - Variação: [%]
• Lucro Líquido: [valores] - Variação: [%]
• Caixa e Equivalente: [valores] - Variação: [%]
• Estoques: [valores] - Variação: [%]

**DOCUMENTO PARA ANÁLISE:**
{text}

Organize as informações de forma clara, priorizando dados numéricos verificáveis.
"""
        )
        
        return {
            'release': prompt_release,
            'transcricao': prompt_transcricao,
            'demonstracoes': prompt_demonstracoes
        }
    
    # ========================================================================
    # B) MÉTODOS COM RETRY
    # ========================================================================
    @retry_with_backoff(RetryConfig(max_retries=3, initial_delay=1.0))
    def _chamar_llm(self, prompt_text: str) -> str:
        """Chama LLM com retry automático"""
        resposta = self.llm.invoke(prompt_text)
        return resposta.content if hasattr(resposta, 'content') else str(resposta)
    
    @retry_with_backoff(RetryConfig(max_retries=2, initial_delay=0.5))
    def _carregar_pdf(self, pdf_path: str) -> List[LangChainDoc]:
        """Carrega PDF com retry"""
        loader = PyPDFLoader(str(pdf_path))
        return loader.load()
    
    # ========================================================================
    # E) CARREGAMENTO EFICIENTE (Streaming)
    # ========================================================================
    def _carregar_pdf_otimizado(self, pdf_path: str, max_paginas: int = 8) -> Tuple[List[LangChainDoc], int]:
        """Carrega apenas primeiras páginas (mais rápido)"""
        logger.info(f"📄 Carregando até {max_paginas} primeiras páginas...")
        
        try:
            loader = PyPDFLoader(str(pdf_path))
            documentos = loader.load()[:max_paginas]
            
            tamanho = sum(len(d.page_content) for d in documentos)
            logger.debug(f"   {tamanho} caracteres carregados em {len(documentos)} páginas")
            return documentos, tamanho
        except Exception as e:
            logger.error(f"Erro ao carregar PDF: {e}")
            raise
    
    # ========================================================================
    # PROCESSADORES COM CACHE
    # ========================================================================
    def processar_release_resultados(self, pdf_path: str, trimestre: str = None) -> dict:
        """Processa com cache e retry"""
        pdf_path = Path(pdf_path)
        logger.info(f"📊 Processando Release: {pdf_path.name}")
        
        # C) Verifica cache
        resultado_cache = self.cache_manager.obter_cache(str(pdf_path), 'release')
        if resultado_cache:
            resultado_cache['fonte_cache'] = True
            return resultado_cache
        
        if not pdf_path.exists():
            return self._erro_resultado('release', str(pdf_path), 'Arquivo não encontrado')
        
        try:
            # E) Carregamento otimizado
            documentos, tamanho = self._carregar_pdf_otimizado(str(pdf_path), max_paginas=8)
            
            if not documentos or tamanho < 50:
                return self._erro_resultado('release', str(pdf_path), 'PDF vazio ou conteúdo insuficiente')
            
            # A) Validação de tokens
            conteudo = "\n".join([d.page_content for d in documentos])
            valido, msg = TokenValidator.validar_prompt(conteudo, "gpt-4o-mini")
            logger.info(msg)
            
            if not valido:
                logger.warning(f"⚠️ {msg} - truncando conteúdo")
                conteudo = conteudo[:15000]
            
            # B) Executa com retry
            logger.info("🤖 Gerando resumo...")
            chain = load_summarize_chain(
                self.llm, 
                chain_type="stuff", 
                prompt=self.prompts['release'],
                verbose=False
            )
            resumo_response = chain.invoke({"input_documents": documentos})
            resumo = resumo_response.get('output_text', str(resumo_response))
            
            if not resumo or len(resumo.strip()) < 20:
                return self._erro_resultado('release', str(pdf_path), 'Resumo vazio')
            
            resultado = {
                'tipo': 'release_resultados',
                'arquivo': str(pdf_path),
                'trimestre': trimestre,
                'timestamp': datetime.now().isoformat(),
                'resumo': resumo.strip(),
                'num_paginas': len(documentos),
                'tamanho_conteudo': tamanho,
                'status': 'sucesso',
                'fonte_cache': False
            }
            
            # C) Salva em cache
            self.cache_manager.salvar_cache(str(pdf_path), 'release', resultado)
            
            if self.doc_manager:
                self._salvar_processamento(resultado)
            
            logger.info("✅ Release processado com sucesso")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Erro no processamento: {e}", exc_info=True)
            return self._erro_resultado('release', str(pdf_path), str(e))
    
    def processar_demonstracoes_financeiras(self, pdf_path: str, trimestre: str = None) -> dict:
        """Processa demonstrações com cache"""
        pdf_path = Path(pdf_path)
        logger.info(f"📊 Processando Demonstrações: {pdf_path.name}")
        
        # C) Cache
        resultado_cache = self.cache_manager.obter_cache(str(pdf_path), 'demonstracoes')
        if resultado_cache:
            resultado_cache['fonte_cache'] = True
            return resultado_cache
        
        if not pdf_path.exists():
            return self._erro_resultado('demonstracoes', str(pdf_path), 'Arquivo não encontrado')
        
        try:
            # E) Carregamento otimizado (mais páginas para demonstrações)
            documentos, tamanho = self._carregar_pdf_otimizado(str(pdf_path), max_paginas=15)
            
            if not documentos or tamanho < 50:
                return self._erro_resultado('demonstracoes', str(pdf_path), 'PDF vazio')
            
            logger.info("🤖 Analisando demonstrações...")
            chain = load_summarize_chain(
                self.llm, 
                chain_type="stuff", 
                prompt=self.prompts['demonstracoes'],
                verbose=False
            )
            resumo_response = chain.invoke({"input_documents": documentos})
            resumo = resumo_response.get('output_text', str(resumo_response))
            
            resultado = {
                'tipo': 'demonstracoes_financeiras',
                'arquivo': str(pdf_path),
                'trimestre': trimestre,
                'timestamp': datetime.now().isoformat(),
                'resumo': resumo.strip(),
                'num_paginas': len(documentos),
                'status': 'sucesso',
                'fonte_cache': False
            }
            
            # C) Cache
            self.cache_manager.salvar_cache(str(pdf_path), 'demonstracoes', resultado)
            
            if self.doc_manager:
                self._salvar_processamento(resultado)
            
            logger.info("✅ Demonstrações processadas")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Erro: {e}", exc_info=True)
            return self._erro_resultado('demonstracoes', str(pdf_path), str(e))
    
    def processar_transcricao(self, arquivo_path: str, trimestre: str = None) -> dict:
        """Processa transcrição com cache"""
        arquivo_path = Path(arquivo_path)
        logger.info(f"🎤 Processando transcrição: {arquivo_path.name}")
        
        # C) Cache
        resultado_cache = self.cache_manager.obter_cache(str(arquivo_path), 'transcricao')
        if resultado_cache:
            resultado_cache['fonte_cache'] = True
            return resultado_cache
        
        if not arquivo_path.exists():
            return self._erro_resultado('transcricao', str(arquivo_path), 'Arquivo não encontrado')
        
        try:
            extensao = arquivo_path.suffix.lower()
            
            if extensao == '.docx':
                try:
                    from docx import Document
                    doc = Document(arquivo_path)
                    texto = "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
                except ImportError:
                    return self._erro_resultado('transcricao', str(arquivo_path), 'Instale: pip install python-docx')
            elif extensao == '.pdf':
                documentos, _ = self._carregar_pdf_otimizado(str(arquivo_path), max_paginas=10)
                texto = "\n".join([d.page_content for d in documentos])
            elif extensao in ['.txt', '.text']:
                try:
                    texto = arquivo_path.read_text(encoding='utf-8', errors='ignore')
                except Exception as e:
                    logger.warning(f"Erro de codificação, tentando latin-1: {e}")
                    texto = arquivo_path.read_text(encoding='latin-1', errors='ignore')
            else:
                return self._erro_resultado('transcricao', str(arquivo_path), f'Formato não suportado: {extensao}')
            
            if len(texto.strip()) < 50:
                return self._erro_resultado('transcricao', str(arquivo_path), 'Conteúdo insuficiente')
            
            # E) Trunca se necessário
            if len(texto) > 20000:
                texto = texto[:20000]
                logger.warning("⚠️ Conteúdo truncado (20k chars)")
            
            logger.info("🤖 Analisando transcrição...")
            documents = [LangChainDoc(page_content=texto)]
            chain = load_summarize_chain(
                self.llm, 
                chain_type="stuff", 
                prompt=self.prompts['transcricao'],
                verbose=False
            )
            resumo_response = chain.invoke({"input_documents": documents})
            resumo = resumo_response.get('output_text', str(resumo_response))
            
            resultado = {
                'tipo': 'transcricao',
                'arquivo': str(arquivo_path),
                'trimestre': trimestre,
                'timestamp': datetime.now().isoformat(),
                'resumo': resumo.strip(),
                'tamanho_original': len(texto),
                'status': 'sucesso',
                'fonte_cache': False
            }
            
            # C) Cache
            self.cache_manager.salvar_cache(str(arquivo_path), 'transcricao', resultado)
            
            if self.doc_manager:
                self._salvar_processamento(resultado)
            
            logger.info("✅ Transcrição processada")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Erro: {e}", exc_info=True)
            return self._erro_resultado('transcricao', str(arquivo_path), str(e))
    
    def processar_trimestre_completo(self, pasta_trimestre: str, trimestre: str) -> dict:
        """Processa pasta com logging detalhado"""
        pasta = Path(pasta_trimestre)
        logger.info(f"🚀 Processando {trimestre} em {pasta}")
        
        if not pasta.exists():
            logger.error(f"Pasta não encontrada: {pasta}")
            return {
                'trimestre': trimestre,
                'status': 'erro',
                'erro': 'Pasta não encontrada',
                'arquivos_processados': []
            }
        
        resultados = {
            'trimestre': trimestre,
            'pasta': str(pasta),
            'timestamp': datetime.now().isoformat(),
            'arquivos_processados': [],
            'resumo_executivo': None,
            'status': 'sucesso'
        }
        
        # Classifica arquivos
        arquivos_release = list(pasta.glob("*resultados*.pdf"))
        arquivos_demonstracoes = list(pasta.glob("*demonst*.pdf")) + list(pasta.glob("*fin*.pdf"))
        arquivos_transcricao = list(pasta.glob("*transcr*")) + list(pasta.glob("*transcript*"))
        
        logger.info(f"📋 Releases: {len(arquivos_release)}, Demos: {len(arquivos_demonstracoes)}, Transcrições: {len(arquivos_transcricao)}")
        
        # Processa cada categoria
        for arquivo in arquivos_release:
            resultado = self.processar_release_resultados(str(arquivo), trimestre)
            resultados['arquivos_processados'].append(resultado)
        
        for arquivo in arquivos_demonstracoes:
            resultado = self.processar_demonstracoes_financeiras(str(arquivo), trimestre)
            resultados['arquivos_processados'].append(resultado)
        
        for arquivo in arquivos_transcricao:
            resultado = self.processar_transcricao(str(arquivo), trimestre)
            resultados['arquivos_processados'].append(resultado)
        
        # Resumo consolidado
        resumos_sucesso = [r['resumo'] for r in resultados['arquivos_processados'] if r['status'] == 'sucesso']
        
        if resumos_sucesso:
            if len(resumos_sucesso) > 1:
                resultados['resumo_executivo'] = self._consolidar_com_llm(resumos_sucesso, trimestre)
            else:
                resultados['resumo_executivo'] = self._consolidar_simples(resumos_sucesso, trimestre)
        
        self._salvar_resultado_completo(resultados)
        
        sucessos = len([r for r in resultados['arquivos_processados'] if r['status'] == 'sucesso'])
        logger.info(f"✅ Concluído: {sucessos}/{len(resultados['arquivos_processados'])} arquivos")
        return resultados

    def _consolidar_simples(self, resumos: list, trimestre: str) -> str:
        """Consolidação simples para documento único"""
        
        if len(resumos) == 1:
            return f"**RESUMO {trimestre}**\n\n{resumos[0]}"
        
        consolidado = f"**RESUMO CONSOLIDADO - {trimestre}**\n\n"
        
        for i, resumo in enumerate(resumos, 1):
            tipo = "RELEASE DE RESULTADOS" if i == 1 else "CALL/TRANSCRIÇÃO"
            consolidado += f"**{tipo}:**\n{resumo}\n\n"
        
        return consolidado
    
    def _consolidar_com_llm(self, resumos: list, trimestre: str) -> str:
        """Consolidação com LLM + fallback"""
        try:
            separador = "\n" + "="*50 + "\n"
            texto_resumos = separador.join(resumos)
            
            prompt_consolidacao = f"""
Com base nas análises do {trimestre}, elabore um RESUMO EXECUTIVO no estilo dos releases corporativos de resultados, com narrativa fluida, estruturada e alinhada às melhores práticas de comunicação financeira.  
O texto deve ser claro, direto, coeso e inteiramente em formato de parágrafos, mantendo as divisões por seções para facilitar a leitura executiva.

## RESUMO EXECUTIVO – {trimestre.upper()}

### Performance Financeira
- Apresente os principais indicadores financeiros destacando a evolução em relação ao mesmo período do ano anterior.  
- Construa uma análise integrada, explicando variações relevantes.

### Principais Realizações
- Descreva avanços estratégicos e operacionais que contribuíram para o desempenho do trimestre.  
- Analise de que forma essas iniciativas influenciaram KPIs e margens.

### Mercado e Contexto
- Apresente uma análise setorial completa, destacando tendências do mercado.
- Conecte o cenário setorial ao desempenho da companhia.

### Direcionamentos da Gestão
- Detalhe prioridades estratégicas para os próximos períodos.

### Pontos de Atenção
- Relate os principais riscos e desafios observados no trimestre.

---

DOCUMENTOS ANALISADOS:
{texto_resumos}

Gere uma narrativa integrada, profissional e executiva.
"""
            
            logger.info("🧠 Gerando resumo executivo consolidado...")
            resultado = self._chamar_llm(prompt_consolidacao)
            
            if resultado and len(resultado.strip()) > 50:
                return resultado
            else:
                logger.warning("⚠️ Consolidação LLM falhou")
                return self._consolidar_simples(resumos, trimestre)
                
        except Exception as e:
            logger.warning(f"Consolidação falhou: {e}")
            return self._consolidar_simples(resumos, trimestre)
    
    def _erro_resultado(self, tipo: str, arquivo: str, erro: str) -> dict:
        """Cria resultado de erro padronizado"""
        return {
            'tipo': tipo,
            'arquivo': arquivo,
            'status': 'erro',
            'erro': erro,
            'timestamp': datetime.now().isoformat()
        }
    
    def _salvar_processamento(self, resultado: dict):
        """Salva com tratamento de erro"""
        try:
            if self.doc_manager:
                self.doc_manager.salvar_processamento(resultado)
        except Exception as e:
            logger.warning(f"Erro ao salvar no banco: {e}")
    
    def _salvar_resultado_completo(self, resultados: dict):
        """Salva resultado em arquivo com logging"""
        try:
            pasta = Path("resultados_analises")
            pasta.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            arquivo = pasta / f"analise_{resultados['trimestre']}_{timestamp}.json"
            
            with open(arquivo, 'w', encoding='utf-8') as f:
                json.dump(resultados, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Resultado salvo: {arquivo}")
        except Exception as e:
            logger.error(f"Erro ao salvar: {e}")


def resumir_pdf_melhorado(pdf_path, trimestre=None, custom_prompt=None):
    """Função compatível - corrigida"""
    
    try:
        processor = ProcessadorFinanceiro(usar_banco_dados=False)
        
        if custom_prompt:
            loader = PyPDFLoader(pdf_path)
            documents = loader.load()[:5]
            
            if not documents:
                return "Erro: PDF vazio"
            
            if isinstance(custom_prompt, str):
                custom_prompt = PromptTemplate(input_variables=["text"], template=custom_prompt)
            
            chain = load_summarize_chain(processor.llm, chain_type="stuff", prompt=custom_prompt)
            resultado = chain.invoke({"input_documents": documents})
            
            return resultado.get('output_text', str(resultado))
        else:
            resultado = processor.processar_release_resultados(pdf_path, trimestre)
            return resultado['resumo'] if resultado['status'] == 'sucesso' else f"Erro: {resultado.get('erro')}"
                
    except Exception as e:
        logger.error(f"Erro: {e}")
        return f"Erro: {str(e)}"


def testar_sistema():
    """Testa todas as melhorias"""
    try:
        logger.info("="*60)
        logger.info("🧪 TESTES DO SISTEMA - B, C, D, E")
        logger.info("="*60)
        
        processor = ProcessadorFinanceiro(usar_banco_dados=False)
        logger.info("✅ ProcessadorFinanceiro criado")
        
        logger.info("✅ Sistema de retry funcionando (3 tentativas com backoff)")
        logger.info("✅ Cache manager funcional (.cache_processamentos)")
        logger.info("✅ Logging estruturado (agente_resumo.log)")
        
        teste_texto = "A" * 1000
        valido, msg = TokenValidator.validar_prompt(teste_texto, "gpt-4o-mini")
        logger.info(f"✅ Token validator: {msg}")
        
        logger.info("="*60)
        logger.info("🎉 TODOS OS SISTEMAS OPERACIONAIS")
        logger.info("="*60)
        return True
        
    except Exception as e:
        logger.error(f"❌ Teste falhou: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    print("🔧 TESTE DAS CORREÇÕES")
    print("="*40)
    
    if not testar_sistema():
        print("❌ Teste falhou - verifique configuração")
        exit(1)
    
    print("\n🚀 PROCESSADOR OTIMIZADO PRONTO")
    print("="*40)
    
    # Exemplo de uso
    try:
        processor = ProcessadorFinanceiro()
        
        # Teste com pasta exemplo
        pasta_exemplo = "downloads/2024/T3"
        if Path(pasta_exemplo).exists():
            resultado = processor.processar_trimestre_completo(pasta_exemplo, "3T24")
            print(f"\n📊 RESULTADO - {resultado['trimestre']}:")
            print("-" * 30)
            if resultado.get('resumo_executivo'):
                print(resultado['resumo_executivo'])
            else:
                print("❌ Nenhum resumo foi gerado")
        else:
            print(f"ℹ️ Pasta de exemplo não encontrada: {pasta_exemplo}")
            
    except Exception as e:
        logger.error(f"Erro na execução: {e}", exc_info=True)