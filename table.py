import json
import pandas as pd
import re
from pathlib import Path
from datetime import datetime

class FlexibleBenchmarkingExtractor:
    """
    Extrator que funciona com JSON estruturado ou texto formatado de benchmarking
    """
    
    def __init__(self, pasta_resultados=None):
        if pasta_resultados is None:
            self.pasta_resultados = Path(r"C:\Users\Casa\Documents\RAPHAEL-0.1\Projeto1\resultados_analises")
        else:
            self.pasta_resultados = Path(pasta_resultados)
    
    def encontrar_ultimo_json(self):
        """Encontra o arquivo JSON mais recente na pasta"""
        try:
            if not self.pasta_resultados.exists():
                print(f"❌ Pasta não encontrada: {self.pasta_resultados}")
                return None
            
            arquivos_json = list(self.pasta_resultados.glob("*.json"))
            
            if not arquivos_json:
                print(f"❌ Nenhum arquivo JSON encontrado em: {self.pasta_resultados}")
                return None
            
            ultimo_arquivo = max(arquivos_json, key=lambda x: x.stat().st_mtime)
            
            print(f"📁 Arquivo mais recente: {ultimo_arquivo.name}")
            print(f"📅 Data: {datetime.fromtimestamp(ultimo_arquivo.stat().st_mtime).strftime('%d/%m/%Y %H:%M')}")
            
            return ultimo_arquivo
            
        except Exception as e:
            print(f"❌ Erro ao buscar arquivos: {e}")
            return None
    
    def carregar_conteudo(self, arquivo_path):
        """Carrega conteúdo do arquivo"""
        try:
            with open(arquivo_path, 'r', encoding='utf-8') as file:
                content = file.read()
            return content
        except Exception as e:
            print(f"❌ Erro ao carregar arquivo: {e}")
            return None
    
    def extrair_benchmarking_de_texto(self, texto):
        """
        Extrai dados de benchmarking de texto formatado como o seu exemplo
        """
        dados = {}
        
        # Padrões para capturar os dados
        padroes = {
            'faturamento_liquido': r'Faturamento Líquido.*?R\$\s*([\d.,]+)\s*mil.*?vs.*?R\$\s*([\d.,]+)\s*mil.*?Variação:\s*([+-]?[\d,]+%)',
            'receita_liquida': r'Receita Líquida.*?R\$\s*([\d.,]+)\s*mil.*?vs.*?R\$\s*([\d.,]+)\s*mil.*?Variação:\s*([+-]?[\d,]+%)',
            'lucro_bruto': r'Lucro Bruto.*?R\$\s*([\d.,]+)\s*mil.*?vs.*?R\$\s*([\d.,]+)\s*mil.*?Variação:\s*([+-]?[\d,]+%)',
            'lucro_liquido': r'Lucro Líquido.*?R\$\s*\(([\d.,]+)\)\s*mil.*?vs.*?R\$\s*([\d.,]+)\s*mil|Lucro Líquido.*?R\$\s*([\d.,]+)\s*mil.*?vs.*?R\$\s*([\d.,]+)\s*mil.*?Variação:\s*([+-]?[\d,]+%)',
            'caixa': r'Caixa e equivalentes.*?R\$\s*([\d.,]+)\s*mil.*?vs.*?R\$\s*([\d.,]+)\s*mil.*?Variação:\s*([+-]?[\d,]+%)',
            'estoques': r'Estoques.*?R\$\s*([\d.,]+)\s*mil.*?vs.*?R\$\s*([\d.,]+)\s*mil.*?Variação:\s*([+-]?[\d,]+%)'
        }
        
        for metrica, padrao in padroes.items():
            match = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
            if match:
                groups = match.groups()
                
                # Tratamento especial para lucro líquido (pode ter valores negativos)
                if metrica == 'lucro_liquido':
                    if len(groups) >= 3 and groups[2]:  # Formato com variação explícita
                        atual = self.limpar_numero(groups[0])
                        anterior = self.limpar_numero(groups[1])
                        variacao = groups[2]
                    elif len(groups) >= 2:  # Formato com prejuízo
                        atual = -self.limpar_numero(groups[0])  # Negativo porque estava entre parênteses
                        anterior = self.limpar_numero(groups[1])
                        variacao = self.calcular_variacao(atual, anterior)
                else:
                    if len(groups) >= 3:
                        atual = self.limpar_numero(groups[0])
                        anterior = self.limpar_numero(groups[1])
                        variacao = groups[2]
                    else:
                        continue
                
                dados[metrica] = {
                    'atual': atual,
                    'anterior': anterior,
                    'variacao': variacao
                }
        
        return dados if dados else None
    
    def limpar_numero(self, numero_str):
        """Converte string de número para float"""
        if not numero_str:
            return 0
        
        # Remove pontos de milhares e converte vírgula para ponto
        numero_limpo = numero_str.replace('.', '').replace(',', '.')
        
        try:
            return float(numero_limpo)
        except:
            return 0
    
    def calcular_variacao(self, atual, anterior):
        """Calcula variação percentual"""
        if anterior == 0:
            return "N/A"
        
        variacao = ((atual - anterior) / anterior) * 100
        sinal = "+" if variacao > 0 else ""
        return f"{sinal}{variacao:.1f}%"
    
    def extrair_benchmarking_de_json(self, data):
        """Extrai benchmarking de JSON estruturado"""
        # Procura por benchmarking em diferentes locais
        benchmarking_data = None
        
        if "benchmarking" in data:
            benchmarking_data = data["benchmarking"]
        elif "resumo_executivo" in data:
            resumo = data["resumo_executivo"]
            if isinstance(resumo, str):
                # Tenta extrair JSON do texto
                json_match = re.search(r'\{.*"benchmarking".*\}', resumo, re.DOTALL)
                if json_match:
                    try:
                        benchmarking_json = json.loads(json_match.group())
                        benchmarking_data = benchmarking_json.get("benchmarking")
                    except:
                        pass
        
        return benchmarking_data
    
    def processar_conteudo(self, conteudo):
        """Processa conteúdo detectando automaticamente o formato"""
        
        # Tenta primeiro como JSON
        try:
            data = json.loads(conteudo)
            benchmarking_data = self.extrair_benchmarking_de_json(data)
            
            if benchmarking_data:
                print("✅ Dados de benchmarking extraídos do JSON estruturado")
                return benchmarking_data, 'json'
        except json.JSONDecodeError:
            pass
        
        # Se não for JSON válido, tenta extrair de texto
        benchmarking_data = self.extrair_benchmarking_de_texto(conteudo)
        if benchmarking_data:
            print("✅ Dados de benchmarking extraídos do texto formatado")
            return benchmarking_data, 'texto'
        
        # Procura por seção "DADOS PARA BENCHMARKING" no texto
        match = re.search(r'DADOS PARA BENCHMARKING.*?(?=\n\n|\Z)', conteudo, re.DOTALL | re.IGNORECASE)
        if match:
            secao_benchmarking = match.group()
            benchmarking_data = self.extrair_benchmarking_de_texto(secao_benchmarking)
            if benchmarking_data:
                print("✅ Dados extraídos da seção 'DADOS PARA BENCHMARKING'")
                return benchmarking_data, 'secao_texto'
        
        return None, None
    
    def converter_para_tabela(self, dados, formato):
        """Converte dados extraídos para DataFrame"""
        
        tabela_dados = []
        
        # Mapeia nomes das métricas
        nomes_metricas = {
            'faturamento_liquido': 'Faturamento Líquido',
            'receita_liquida': 'Receita Líquida',
            'lucro_bruto': 'Lucro Bruto',
            'lucro_liquido': 'Lucro Líquido', 
            'caixa': 'Caixa e Equivalentes',
            'estoques': 'Estoques',
            'ativo_total': 'Ativo Total',
            'patrimonio_liquido': 'Patrimônio Líquido',
            'ebitda': 'EBITDA'
        }
        
        if formato == 'json':
            # Processa formato JSON estruturado
            for metrica_key, nome_metrica in nomes_metricas.items():
                if metrica_key in dados:
                    dados_metrica = dados[metrica_key]
                    
                    if isinstance(dados_metrica, dict) and 'atual' in dados_metrica:
                        atual = dados_metrica.get('atual', {})
                        anterior = dados_metrica.get('anterior', {})
                        variacao = dados_metrica.get('variacao', {})
                        
                        # Dados consolidados
                        if isinstance(atual, dict) and 'consolidado' in atual:
                            tabela_dados.append({
                                'Métrica': nome_metrica,
                                'Tipo': 'Consolidado',
                                'Período Atual': atual.get('consolidado', 'N/A'),
                                'Período Anterior': anterior.get('consolidado', 'N/A'),
                                'Variação': variacao.get('consolidado', 'N/A')
                            })
                        
                        # Dados controladora
                        if isinstance(atual, dict) and 'controladora' in atual:
                            tabela_dados.append({
                                'Métrica': nome_metrica,
                                'Tipo': 'Controladora',
                                'Período Atual': atual.get('controladora', 'N/A'),
                                'Período Anterior': anterior.get('controladora', 'N/A'),
                                'Variação': variacao.get('controladora', 'N/A')
                            })
        
        else:
            # Processa formato de texto (sem divisão consolidado/controladora)
            for metrica_key, nome_metrica in nomes_metricas.items():
                if metrica_key in dados:
                    dados_metrica = dados[metrica_key]
                    
                    tabela_dados.append({
                        'Métrica': nome_metrica,
                        'Tipo': 'Consolidado',
                        'Período Atual': dados_metrica.get('atual', 'N/A'),
                        'Período Anterior': dados_metrica.get('anterior', 'N/A'),
                        'Variação': dados_metrica.get('variacao', 'N/A')
                    })
        
        if tabela_dados:
            df = pd.DataFrame(tabela_dados)
            print(f"✅ Tabela criada com {len(tabela_dados)} linhas")
            return df
        else:
            print("⚠️ Nenhum dado válido encontrado para criar tabela")
            return None
    
    def formatar_valores(self, df):
        """Formata valores numéricos na tabela"""
        def formatar_valor(valor):
            if valor == "N/A" or valor is None or valor == "":
                return "N/A"
            
            try:
                if isinstance(valor, str):
                    # Remove formatação se houver
                    valor_limpo = valor.replace(".", "").replace(",", ".")
                    if valor_limpo.replace("-", "").replace("+", "").replace(".", "").isdigit():
                        valor = float(valor_limpo)
                
                if isinstance(valor, (int, float)):
                    if abs(valor) >= 1000000:
                        return f"{valor/1000000:.1f}M"
                    elif abs(valor) >= 1000:
                        return f"{valor/1000:.1f}K"
                    else:
                        return f"{valor:.0f}"
                
                return str(valor)
            except:
                return str(valor)
        
        df_formatado = df.copy()
        df_formatado["Período Atual"] = df_formatado["Período Atual"].apply(formatar_valor)
        df_formatado["Período Anterior"] = df_formatado["Período Anterior"].apply(formatar_valor)
        
        return df_formatado
    
    def exibir_tabela(self, df):
        """Exibe tabela formatada"""
        if df is None or df.empty:
            print("❌ Nenhum dado para exibir")
            return
        
        print("\n" + "="*80)
        print("📊 TABELA DE BENCHMARKING - ÚLTIMO ARQUIVO")
        print("="*80)
        
        df_formatado = self.formatar_valores(df)
        print(df_formatado.to_string(index=False, max_colwidth=20))
        print("="*80)
    
    def salvar_tabela(self, df, nome_arquivo=None):
        """Salva tabela em Excel"""
        if df is None or df.empty:
            print("❌ Nenhum dado para salvar")
            return
        
        if nome_arquivo is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nome_arquivo = f"benchmarking_tabela_{timestamp}.xlsx"
        
        try:
            caminho_salvar = self.pasta_resultados / nome_arquivo
            df.to_excel(caminho_salvar, index=False, engine='openpyxl')
            print(f"✅ Tabela salva como: {caminho_salvar}")
        except ImportError:
            # Fallback para CSV
            nome_csv = nome_arquivo.replace('.xlsx', '.csv')
            caminho_csv = self.pasta_resultados / nome_csv
            df.to_csv(caminho_csv, index=False, encoding='utf-8')
            print(f"✅ Tabela salva como: {caminho_csv}")
        except Exception as e:
            print(f"❌ Erro ao salvar: {e}")
    
    def processar_ultimo_arquivo(self, exibir=True, salvar=True):
        """Método principal: processa o último arquivo JSON da pasta"""
        
        print("🚀 PROCESSANDO ÚLTIMO ARQUIVO DE BENCHMARKING")
        print("="*60)
        
        # 1. Encontra último arquivo
        ultimo_arquivo = self.encontrar_ultimo_json()
        if not ultimo_arquivo:
            return None
        
        # 2. Carrega conteúdo
        conteudo = self.carregar_conteudo(ultimo_arquivo)
        if not conteudo:
            return None
        
        # 3. Processa conteúdo (detecta formato automaticamente)
        dados, formato = self.processar_conteudo(conteudo)
        if not dados:
            print("❌ Nenhum dado de benchmarking encontrado")
            return None
        
        # 4. Converte para tabela
        df = self.converter_para_tabela(dados, formato)
        if df is None:
            return None
        
        # 5. Exibe tabela
        if exibir:
            self.exibir_tabela(df)
        
        # 6. Salva tabela
        if salvar:
            self.salvar_tabela(df)
        
        return df


def processar_texto_direto(texto_benchmarking):
    """
    Função auxiliar para processar diretamente um texto de benchmarking
    """
    extrator = FlexibleBenchmarkingExtractor()
    dados, formato = extrator.processar_conteudo(texto_benchmarking)
    
    if dados:
        df = extrator.converter_para_tabela(dados, formato)
        if df is not None:
            extrator.exibir_tabela(df)
            return df
    
    print("❌ Não foi possível extrair dados de benchmarking do texto")
    return None


def executar_benchmarking_automatico(pasta_personalizada=None):
    """Função principal para executar o processo automaticamente"""
    
    extrator = FlexibleBenchmarkingExtractor(pasta_personalizada)
    tabela = extrator.processar_ultimo_arquivo()
    
    if tabela is not None:
        print(f"\n✅ Processo concluído com sucesso!")
        print(f"📊 {len(tabela)} linhas de dados processadas")
    else:
        print("\n❌ Não foi possível processar os dados")
    
    return tabela


if __name__ == "__main__":
    print("🎯 EXTRATOR AUTOMÁTICO DE BENCHMARKING")
    print("Compatível com JSON estruturado e texto formatado")
    print("="*60)
    
    # Exemplo com o texto que você forneceu
    texto_exemplo = """
    DADOS PARA BENCHMARKING
    • Faturamento Líquido:
    • Consolidação: R$ 1.557.657 mil (30/06/2025) vs R$ 1.822.656 mil (30/06/2024)
    • Variação: -14,5%
    • Lucro Bruto:
    • R$ 375.655 mil vs R$ 455.418 mil
    • Variação: -17,6%
    • Lucro Líquido:
    • R$ (10.357) mil vs R$ 69.207 mil
    • Variação: queda de 115,8% (prejuízo em 2025)
    • Caixa e equivalentes:
    • R$ 675.876 mil vs R$ 566.929 mil
    • Variação: +19,2%
    • Estoques:
    • R$ 1.002.041 mil vs R$ 1.096.246 mil
    • Variação: -8,6%
    """
    
    print("\n📝 TESTE COM TEXTO DE EXEMPLO:")
    tabela_teste = processar_texto_direto(texto_exemplo)
    
    print("\n" + "="*60)
    print("🔄 PROCESSANDO ÚLTIMO ARQUIVO DA PASTA:")
    
    # Executa o processo principal
    resultado = executar_benchmarking_automatico()
    
    if resultado is not None:
        print("\n💡 Tabela pronta para análise!")
    
    input("\nPressione Enter para sair...")