import os
from dotenv import load_dotenv
from langchain.chains.summarize import load_summarize_chain
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema import Document as LangChainDoc
from database_manager import DocumentManager
import json
from datetime import datetime
from pathlib import Path

load_dotenv()

class ProcessadorFinanceiro:
    """Versão corrigida - geração de resumos funcionando"""
    
    def __init__(self, usar_banco_dados: bool = True):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY não encontrada. Configure no arquivo .env")
        
        # CORREÇÃO 1: Modelo válido (gpt-5-nano não existe)
        self.llm = ChatOpenAI(
            temperature=0, 
            model="gpt-4.1-nano",   # Modelo real e mais barato
            max_tokens=2800,
            max_retries=2
        )
        
        self.doc_manager = DocumentManager() if usar_banco_dados else None
        self.prompts = self._criar_prompts()
    
    def _criar_prompts(self):
        """Prompts otimizados para geração consistente de resumos"""

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
  - Atribuído aos controladores: [valor atual] vs [valor anterior]
  - Atribuído aos não controladores: [valor atual] vs [valor anterior]

### BALANÇO PATRIMONIAL - CONSOLIDADO
**Período Atual vs Período Anterior:**
• Ativo Total: [valor atual] vs [valor anterior] - Variação: [%]
• Ativo Circulante: [valor atual] vs [valor anterior]
  - Caixa e Equivalentes: [valor atual] vs [valor anterior]
  - Contas a Receber: [valor atual] vs [valor anterior]
  - Estoques: [valor atual] vs [valor anterior]
• Ativo Não Circulante: [valor atual] vs [valor anterior]
  - Imobilizado: [valor atual] vs [valor anterior]
  - Intangível: [valor atual] vs [valor anterior]
• Passivo Total: [valor atual] vs [valor anterior]
• Passivo Circulante: [valor atual] vs [valor anterior]
  - Empréstimos CP: [valor atual] vs [valor anterior]
  - Fornecedores: [valor atual] vs [valor anterior]
• Passivo Não Circulante: [valor atual] vs [valor anterior]
  - Empréstimos LP: [valor atual] vs [valor anterior]
• Patrimônio Líquido Consolidado: [valor atual] vs [valor anterior]
  - Atribuído aos controladores: [valor atual] vs [valor anterior]
  - Atribuído aos não controladores: [valor atual] vs [valor anterior]

### INDICADORES CALCULADOS

• Margem Bruta: [% atual] vs [% anterior]
• Margem EBITDA: [% atual] vs [% anterior]
• Margem Líquida: [% atual] vs [% anterior]
• ROE Consolidado: [% atual] vs [% anterior]
• Liquidez Corrente: [atual] vs [anterior]
• Endividamento: [% atual] vs [% anterior]

### PRINCIPAIS VARIAÇÕES IDENTIFICADAS

• Maiores crescimentos em receita: [itens e %]
• Maiores variações em custos: [itens e %]
• Mudanças significativas no balanço: [itens e valores]

### OUTROS RESULTADOS ABRANGENTES
• Diferenças de Câmbio: [valores]
• Hedges de Fluxo de Caixa: [valores]
• Resultado Abrangente Total: [consolidado e controladora]

### DADOS PARA BENCHMARKING (IMPORTANTE)

• Faturamento Líquido: 
[valores] - Variação: [%]
• Lucro Bruto: 
[valores]  - Variação: [%]
• Lucro Líquido: 
[valores] - Variação: [%]
• Caixa e Equivalente: 
[valores] - Variação: [%]
• Estoques: 
[valores] - Variação: [%]



### INSTRUÇÕES CRÍTICAS
1. SEPARAR claramente os dados CONSOLIDADOS dos da CONTROLADORA somente no Balanço Patrimonial e nos indicadores relacionados.
2. Nas demais demonstrações, considerar apenas o CONSOLIDADO.
3. Para cada valor, apresentar Período Atual vs Período Anterior.
4. Calcular variações percentuais quando possível.
5. Se algum dado não estiver disponível, escrever “Não informado”.
6. Especificar se os números são trimestrais ou semestrais.
7. Identificar qual coluna é a mais recente (ex.: “30/06/2025” vs “30/06/2024”) e usar como Período Atual.


**DOCUMENTO PARA ANÁLISE:**
{text}

Organize as informações de forma clara, priorizando dados numéricos verificáveis.
"""
        )
        return {
            'release': prompt_release,
            'transcricao': prompt_transcricao,
            'demonstracoes': prompt_demonstracoes  # Placeholder para futuros prompts
        } 
    def processar_demonstracoes_financeiras(self, pdf_path: str, trimestre: str = None) -> dict:
        """Processa demonstrações financeiras com foco em dados contábeis"""

        pdf_path = Path(pdf_path)
        print(f"📊 Processando Demonstrações Financeiras: {pdf_path.name}")

        if not pdf_path.exists():
            return self._erro_resultado('demonstracoes', str(pdf_path), f'Arquivo não encontrado: {pdf_path}')

        try:
            # Carrega o PDF
            loader = PyPDFLoader(str(pdf_path))
            documents = loader.load()

            if not documents:
                return self._erro_resultado('demonstracoes', str(pdf_path), 'PDF vazio ou não pode ser lido')

            # Demonstrações podem ter mais páginas
            docs_limitados = documents[:15]

            # Verifica conteúdo
            conteudo_total = ""
            for doc in docs_limitados:
                conteudo_total += doc.page_content + "\n"

            if len(conteudo_total.strip()) < 50:
                return self._erro_resultado('demonstracoes', str(pdf_path), 'Conteúdo do PDF insuficiente')

            print(f"📄 Conteúdo extraído: {len(conteudo_total)} caracteres")

            # Usa o prompt específico para demonstrações
            chain = load_summarize_chain(
                self.llm, 
                chain_type="stuff",
                prompt=self.prompts['demonstracoes'],
                verbose=True
            )

            print("🤖 Gerando análise das demonstrações financeiras...")
            resumo_response = chain.invoke({"input_documents": docs_limitados})

            # Extrai o resultado
            if isinstance(resumo_response, dict) and 'output_text' in resumo_response:
                resumo = resumo_response['output_text']
            elif hasattr(resumo_response, 'content'):
                resumo = resumo_response.content
            else:
                resumo = str(resumo_response)

            if not resumo or len(resumo.strip()) < 20:
                return self._erro_resultado('demonstracoes', str(pdf_path), 'Análise gerada está vazia')

            resultado = {
                'tipo': 'demonstracoes_financeiras',
                'arquivo': str(pdf_path),
                'trimestre': trimestre,
                'timestamp': datetime.now().isoformat(),
                'resumo': resumo.strip(),
                'num_paginas': len(docs_limitados),
                'tamanho_conteudo': len(conteudo_total),
                'status': 'sucesso'
            }

            # Salva no banco se disponível
            if self.doc_manager:
                self._salvar_processamento(resultado)

            print("✅ Demonstrações financeiras processadas com sucesso")
            print(f"📝 Análise gerada: {len(resumo)} caracteres")
            return resultado

        except Exception as e:
            print(f"❌ Erro no processamento das demonstrações: {e}")
            import traceback
            traceback.print_exc()
            return self._erro_resultado('demonstracoes', str(pdf_path), str(e))
    def processar_release_resultados(self, pdf_path: str, trimestre: str = None) -> dict:
        """CORRIGIDO: Processa release de resultados com melhor tratamento de erros"""
        
        pdf_path = Path(pdf_path)
        print(f"📊 Processando Release: {pdf_path.name}")
        
        if not pdf_path.exists():
            return self._erro_resultado('release', str(pdf_path), f'Arquivo não encontrado: {pdf_path}')
        
        try:
            # CORREÇÃO 2: Melhor tratamento do carregamento do PDF
            loader = PyPDFLoader(str(pdf_path))
            documents = loader.load()
            
            if not documents:
                return self._erro_resultado('release', str(pdf_path), 'PDF vazio ou não pode ser lido')
            
            # CORREÇÃO 3: Limita conteúdo para evitar exceeder limite de tokens
            docs_limitados = documents[:8]  # Máximo 8 páginas
            
            # CORREÇÃO 4: Verifica se há conteúdo válido
            conteudo_total = ""
            for doc in docs_limitados:
                conteudo_total += doc.page_content + "\n"
            
            if len(conteudo_total.strip()) < 50:
                return self._erro_resultado('release', str(pdf_path), 'Conteúdo do PDF insuficiente')
            
            print(f"📄 Conteúdo extraído: {len(conteudo_total)} caracteres")
            
            # CORREÇÃO 5: Melhor configuração da chain
            chain = load_summarize_chain(
                self.llm, 
                chain_type="stuff",
                prompt=self.prompts['release'],
                verbose=True  # Para debug
            )
            
            # CORREÇÃO 6: Executa com tratamento específico
            print("🤖 Gerando resumo com IA...")
            resumo_response = chain.invoke({"input_documents": docs_limitados})
            
            # CORREÇÃO 7: Extrai o resultado corretamente
            if isinstance(resumo_response, dict) and 'output_text' in resumo_response:
                resumo = resumo_response['output_text']
            elif hasattr(resumo_response, 'content'):
                resumo = resumo_response.content
            else:
                resumo = str(resumo_response)
            
            if not resumo or len(resumo.strip()) < 20:
                return self._erro_resultado('release', str(pdf_path), 'Resumo gerado está vazio ou muito curto')
            
            resultado = {
                'tipo': 'release_resultados',
                'arquivo': str(pdf_path),
                'trimestre': trimestre,
                'timestamp': datetime.now().isoformat(),
                'resumo': resumo.strip(),
                'num_paginas': len(docs_limitados),
                'tamanho_conteudo': len(conteudo_total),
                'status': 'sucesso'
            }
            
            # Salva no banco se disponível
            if self.doc_manager:
                self._salvar_processamento(resultado)
            
            print("✅ Release processado com sucesso")
            print(f"📝 Resumo gerado: {len(resumo)} caracteres")
            return resultado
            
        except Exception as e:
            print(f"❌ Erro no processamento do release: {e}")
            import traceback
            traceback.print_exc()
            return self._erro_resultado('release', str(pdf_path), str(e))
    
    def processar_transcricao(self, arquivo_path: str, trimestre: str = None) -> dict:
        """CORRIGIDO: Processa transcrição com suporte a múltiplos formatos"""

        arquivo_path = Path(arquivo_path)
        print(f"🎤 Processando transcrição: {arquivo_path.name}")
    
        if not arquivo_path.exists():
            return self._erro_resultado('transcricao', str(arquivo_path), f'Arquivo não encontrado')
    
        try:
            texto = ""
            extensao = arquivo_path.suffix.lower()
            
            # CORREÇÃO 8: Melhor tratamento por tipo de arquivo
            if extensao == '.docx':
                try:
                    from docx import Document
                    doc = Document(arquivo_path)
                    paragrafos = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                    texto = "\n".join(paragrafos)
                except ImportError:
                    return self._erro_resultado('transcricao', str(arquivo_path), 'Instale: pip install python-docx')
                except Exception as e:
                    return self._erro_resultado('transcricao', str(arquivo_path), f'Erro ao ler DOCX: {e}')
    
            elif extensao == '.pdf':
                try:
                    loader = PyPDFLoader(str(arquivo_path))
                    documentos = loader.load()
                    texto = "\n".join([d.page_content for d in documentos])
                except Exception as e:
                    return self._erro_resultado('transcricao', str(arquivo_path), f'Erro ao ler PDF: {e}')
    
            elif extensao in ['.txt', '.text']:
                try:
                    with open(arquivo_path, 'r', encoding='utf-8') as f:
                        texto = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(arquivo_path, 'r', encoding='latin-1') as f:
                            texto = f.read()
                    except Exception as e:
                        return self._erro_resultado('transcricao', str(arquivo_path), f'Erro de codificação: {e}')
            else:
                return self._erro_resultado('transcricao', str(arquivo_path), f'Formato não suportado: {extensao}')
    
            if not texto or len(texto.strip()) < 50:
                return self._erro_resultado('transcricao', str(arquivo_path), 'Arquivo vazio ou conteúdo insuficiente')
    
            print(f"📄 Conteúdo extraído: {len(texto)} caracteres")
            
            # CORREÇÃO 9: Limita tamanho de forma mais inteligente
            if len(texto) > 25000:  # Limite mais generoso
                texto_limitado = texto[:25000] + "\n... [CONTEÚDO TRUNCADO]"
                print("⚠️ Conteúdo truncado para caber nos limites")
            else:
                texto_limitado = texto
    
            # Cria documento LangChain
            documents = [LangChainDoc(page_content=texto_limitado)]
    
            # CORREÇÃO 10: Executa processamento
            chain = load_summarize_chain(
                self.llm,
                chain_type="stuff",
                prompt=self.prompts['transcricao'],
                verbose=True
            )
    
            print("🤖 Gerando resumo da transcrição...")
            resumo_response = chain.invoke({"input_documents": documents})
            
            # Extrai resultado
            if isinstance(resumo_response, dict) and 'output_text' in resumo_response:
                resumo = resumo_response['output_text']
            elif hasattr(resumo_response, 'content'):
                resumo = resumo_response.content
            else:
                resumo = str(resumo_response)
                
            if not resumo or len(resumo.strip()) < 20:
                return self._erro_resultado('transcricao', str(arquivo_path), 'Resumo gerado está vazio')
    
            resultado = {
                'tipo': 'transcricao',
                'arquivo': str(arquivo_path),
                'trimestre': trimestre,
                'timestamp': datetime.now().isoformat(),
                'resumo': resumo.strip(),
                'tamanho_original': len(texto),
                'tamanho_processado': len(texto_limitado),
                'status': 'sucesso'
            }
    
            if self.doc_manager:
                self._salvar_processamento(resultado)
    
            print("✅ Transcrição processada com sucesso")
            print(f"📝 Resumo gerado: {len(resumo)} caracteres")
            return resultado
    
        except Exception as e:
            print(f"❌ Erro na transcrição: {e}")
            import traceback
            traceback.print_exc()
            return self._erro_resultado('transcricao', str(arquivo_path), str(e))

    def processar_trimestre_completo(self, pasta_trimestre: str, trimestre: str) -> dict:
        """CORRIGIDO: Método que estava faltando - processa pasta completa"""
        
        print(f"🚀 Processamento completo do trimestre: {trimestre}")
        pasta = Path(pasta_trimestre)
        
        if not pasta.exists():
            return {
                'trimestre': trimestre,
                'status': 'erro',
                'erro': f'Pasta não encontrada: {pasta}',
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
        
        # Mapeia todos os arquivos da pasta
        arquivos_release = []
        arquivos_transcricao = []
        outros_pdfs = []
        
        for arquivo in pasta.glob("*"):
            if not arquivo.is_file():
                continue
                
            nome = arquivo.name.lower()
            extensao = arquivo.suffix.lower()
            
            # Classifica por tipo
            if "resultados" in nome and extensao == ".pdf":
                arquivos_release.append(arquivo)
            elif "transcricao" in nome or "transcript" in nome:
                arquivos_transcricao.append(arquivo)
            elif extensao == ".pdf":
                outros_pdfs.append(arquivo)
        
        print(f"📋 Arquivos encontrados:")
        print(f"   📊 Releases: {len(arquivos_release)}")
        print(f"   🎤 Transcrições: {len(arquivos_transcricao)}")  
        print(f"   📄 Outros PDFs: {len(outros_pdfs)}")
        
        # Processa releases
        for arquivo in arquivos_release:
            resultado = self.processar_release_resultados(str(arquivo), trimestre)
            resultados['arquivos_processados'].append(resultado)
        
        # Processa transcrições  
        for arquivo in arquivos_transcricao:
            resultado = self.processar_transcricao(str(arquivo), trimestre)
            resultados['arquivos_processados'].append(resultado)
            
        # Processa as demonstraações financeiras se houver
        for arquivo in outros_pdfs:
            resultado = self.processar_demonstracoes_financeiras(str(arquivo), trimestre)
            resultados['arquivos_processados'].append(resultado)

        
        # Gera resumo consolidado
        resumos_sucesso = [arq['resumo'] for arq in resultados['arquivos_processados'] if arq['status'] == 'sucesso']
        
        if resumos_sucesso:
            if len(resumos_sucesso) > 1:
                resultados['resumo_executivo'] = self._consolidar_com_llm(resumos_sucesso, trimestre)
            else:
                resultados['resumo_executivo'] = self._consolidar_simples(resumos_sucesso, trimestre)
        else:
            resultados['resumo_executivo'] = f"❌ Nenhum arquivo do {trimestre} foi processado com sucesso."
        
        self._salvar_resultado_completo(resultados)
        
        sucessos = len([r for r in resultados['arquivos_processados'] if r['status'] == 'sucesso'])
        print(f"✅ Processamento concluído: {sucessos}/{len(resultados['arquivos_processados'])} arquivos processados")
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
        """CORRIGIDO: Usa LLM para consolidação mais inteligente"""
        
        if len(resumos) == 1:
            return f"**{trimestre}**\n\n{resumos[0]}"
        
        # Prompt para consolidação
        separador = "\n" + "="*50 + "\n"
        texto_resumos = separador.join(resumos)
        
        prompt_consolidacao = f"""
Com base nas análises do {trimestre}, produza um RESUMO EXECUTIVO no estilo de release de resultados corporativos, bem estruturado, coeso e de leitura fluida.  
Use linguagem clara, objetiva e em formato de parágrafos (não apenas bullets), mas preserve a divisão em seções.  

## RESUMO EXECUTIVO - {trimestre.upper()}

### Performance Financeira
- Apresente os principais números de receita, EBITDA, lucro líquido e margens, sempre destacando as variações em relação ao mesmo período do ano anterior.  
- Estruture em formato narrativo, integrando os números com uma análise breve de desempenho.

### Principais Realizações
- Relate os avanços estratégicos, operacionais e de portfólio de forma conectada, mostrando impacto direto nos resultados.  
- Destaque movimentos como expansão de contratos, inovação em produtos, crescimento em determinados segmentos e diversificação de receita.

### Direcionamentos da Gestão
- Explique as prioridades e o posicionamento da companhia para os próximos períodos.  
- Inclua guidance, expectativas de mercado e visão estratégica, sempre em tom institucional e positivo.

### Pontos de Atenção
- Aborde de forma integrada os principais desafios e riscos: pressões de margem, cenário macroeconômico, retrações setoriais ou fatores conjunturais.  
- O tom deve ser de reconhecimento do desafio, mas com viés de superação.

## Estratégias, Transformações e Desafios
- Faça um fechamento analítico, mostrando como a empresa está se transformando, consolidando novas avenidas de crescimento e lidando com o ambiente competitivo.  
- Construa um texto que una indicadores quantitativos (números) e qualitativos (mensagens da gestão).

---

DOCUMENTOS ANALISADOS:
{texto_resumos}

IMPORTANTE:
- O resultado final deve ser um texto coeso e contínuo, no estilo de um press release executivo.  
- Evite apenas listar itens: crie uma narrativa clara, fluida e completa.  
- Seja conciso, mas não superficial.  
"""
        
        try:
            print("🧠 Gerando resumo executivo consolidado...")
            resposta = self.llm.invoke(prompt_consolidacao)
            resultado = resposta.content if hasattr(resposta, 'content') else str(resposta)
            
            if resultado and len(resultado.strip()) > 50:
                return resultado
            else:
                print("⚠️ Consolidação LLM falhou, usando método simples")
                return self._consolidar_simples(resumos, trimestre)
                
        except Exception as e:
            print(f"⚠️ Erro na consolidação LLM: {e}")
            return self._consolidar_simples(resumos, trimestre)
    
    def _erro_resultado(self, tipo: str, arquivo: str, erro: str) -> dict:
        """Padroniza retorno de erro"""
        return {
            'tipo': tipo,
            'arquivo': arquivo,
            'status': 'erro',
            'erro': erro,
            'timestamp': datetime.now().isoformat(),
            'resumo': f'ERRO: {erro}'
        }
    
    def _salvar_processamento(self, resultado: dict):
        """Salva processamento individual"""
        if self.doc_manager:
            try:
                self.doc_manager.salvar_processamento(resultado)
            except Exception as e:
                print(f"Erro ao salvar no banco: {e}")
    
    def _salvar_resultado_completo(self, resultados: dict):
        """Salva resultado em arquivo"""
        try:
            pasta_resultados = Path("resultados_analises")
            pasta_resultados.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            arquivo = pasta_resultados / f"analise_{resultados['trimestre']}_{timestamp}.json"
            
            with open(arquivo, 'w', encoding='utf-8') as f:
                json.dump(resultados, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Resultado salvo: {arquivo}")
            
            if self.doc_manager:
                self.doc_manager.salvar_analise_completa(resultados)
                
        except Exception as e:
            print(f"Erro ao salvar arquivo: {e}")


# Função de compatibilidade melhorada
def resumir_pdf_melhorado(pdf_path, trimestre=None, custom_prompt=None):
    """Função compatível - corrigida"""
    
    try:
        processor = ProcessadorFinanceiro(usar_banco_dados=False)
        
        if custom_prompt:
            # Processa com prompt personalizado
            loader = PyPDFLoader(pdf_path)
            documents = loader.load()[:5]  # Máximo 5 páginas
            
            if not documents:
                return "Erro: PDF vazio"
            
            chain = load_summarize_chain(
                processor.llm, 
                chain_type="stuff", 
                prompt=custom_prompt
            )
            resultado = chain.invoke({"input_documents": documents})
            
            if isinstance(resultado, dict) and 'output_text' in resultado:
                return resultado['output_text']
            return str(resultado)
        else:
            # Usa processamento padrão
            resultado = processor.processar_release_resultados(pdf_path, trimestre)
            return resultado['resumo'] if resultado['status'] == 'sucesso' else f"Erro: {resultado.get('erro')}"
                
    except Exception as e:
        return f"Erro: {str(e)}"


def testar_correcao():
    """Teste das correções"""
    try:
        if not os.getenv("OPENAI_API_KEY"):
            print("❌ Configure OPENAI_API_KEY no arquivo .env")
            return False
        
        processor = ProcessadorFinanceiro(usar_banco_dados=False)
        print("✅ ProcessadorFinanceiro inicializado com sucesso")
        
        # Teste básico do LLM
        resposta = processor.llm.invoke("Teste de conexão: responda apenas 'OK'")
        print(f"✅ LLM respondeu: {resposta.content if hasattr(resposta, 'content') else resposta}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        return False


if __name__ == "__main__":
    print("🔧 TESTE DAS CORREÇÕES")
    print("="*40)
    
    if not testar_correcao():
        print("❌ Teste falhou - verifique configuração")
        exit(1)
    
    print("\n🚀 PROCESSADOR CORRIGIDO PRONTO")
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
            if resultado['resumo_executivo']:
                print(resultado['resumo_executivo'])
                print("-" * 30)
                print("Tranformando dados benchmarking em tabela...")
                from table import  executar_benchmarking_automatico
                tabela = executar_benchmarking_automatico()
                
            else:
                print("❌ Nenhum resumo foi gerado")
                
        else:
            print(f"ℹ️ Pasta de exemplo não encontrada: {pasta_exemplo}")
            print("   Crie uma pasta com arquivos PDF para testar")
            
    except Exception as e:
        print(f"❌ Erro na execução: {e}")
        import traceback
        traceback.print_exc()