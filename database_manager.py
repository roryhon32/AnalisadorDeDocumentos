# database_manager.py

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

class DocumentManager:
    """Versão simplificada do gerenciador de documentos - só SQLite por enquanto"""
    
    def __init__(self, db_path: str = "positivo_ri.db"):
        self.db_path = db_path
        self._init_sqlite()
    
    def _init_sqlite(self):
        """Inicializa banco SQLite com tabelas básicas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de processamentos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                arquivo TEXT NOT NULL,
                trimestre TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resumo TEXT,
                status TEXT DEFAULT 'sucesso',
                metadados JSON
            )
        ''')
        
        # Tabela de análises completas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analises_completas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trimestre TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resumo_executivo TEXT,
                num_arquivos INTEGER,
                metadados JSON
            )
        ''')
        
        # Índices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_processamentos_trimestre ON processamentos(trimestre)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_analises_trimestre ON analises_completas(trimestre)')
        
        conn.commit()
        conn.close()
        
        print("✅ SQLite inicializado")
    
    def salvar_processamento(self, resultado: Dict) -> int:
        """Salva resultado de processamento individual"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO processamentos 
                (tipo, arquivo, trimestre, resumo, status, metadados)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                resultado['tipo'],
                resultado['arquivo'],
                resultado.get('trimestre'),
                resultado.get('resumo', ''),
                resultado['status'],
                json.dumps(resultado, ensure_ascii=False)
            ))
            
            processamento_id = cursor.lastrowid
            conn.commit()
            
            return processamento_id
            
        except Exception as e:
            print(f"Erro ao salvar processamento: {e}")
            return -1
        finally:
            conn.close()
    
    def salvar_analise_completa(self, resultados: Dict) -> int:
        """Salva análise completa de trimestre"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO analises_completas 
                (trimestre, resumo_executivo, num_arquivos, metadados)
                VALUES (?, ?, ?, ?)
            ''', (
                resultados['trimestre'],
                resultados.get('resumo_executivo', ''),
                len(resultados.get('arquivos_processados', [])),
                json.dumps(resultados, ensure_ascii=False)
            ))
            
            analise_id = cursor.lastrowid
            conn.commit()
            
            return analise_id
            
        except Exception as e:
            print(f"Erro ao salvar análise completa: {e}")
            return -1
        finally:
            conn.close()
    
    def buscar_analises(self, trimestre: str = None, limit: int = 10) -> List[Dict]:
        """Busca análises salvas"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if trimestre:
            cursor.execute('''
                SELECT * FROM analises_completas 
                WHERE trimestre = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (trimestre, limit))
        else:
            cursor.execute('''
                SELECT * FROM analises_completas 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
        
        colunas = [desc[0] for desc in cursor.description]
        resultados = []
        
        for row in cursor.fetchall():
            resultado = dict(zip(colunas, row))
            # Converte JSON de volta
            if resultado['metadados']:
                try:
                    resultado['dados_completos'] = json.loads(resultado['metadados'])
                except:
                    pass
            resultados.append(resultado)
        
        conn.close()
        return resultados
    
    def obter_estatisticas(self) -> Dict:
        """Retorna estatísticas básicas do banco"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Total de processamentos
        cursor.execute('SELECT COUNT(*) FROM processamentos')
        stats['total_processamentos'] = cursor.fetchone()[0]
        
        # Processamentos por tipo
        cursor.execute('''
            SELECT tipo, COUNT(*) 
            FROM processamentos 
            GROUP BY tipo
        ''')
        stats['por_tipo'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Trimestres analisados
        cursor.execute('''
            SELECT DISTINCT trimestre, COUNT(*) 
            FROM analises_completas 
            WHERE trimestre IS NOT NULL
            GROUP BY trimestre
            ORDER BY trimestre DESC
        ''')
        stats['trimestres'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        return stats


# Versão ainda mais simples se você não quiser banco por enquanto
class DocumentManagerSimples:
    """Versão que só salva em arquivos JSON - sem banco de dados"""
    
    def __init__(self, pasta_resultados: str = "resultados_analises"):
        self.pasta_resultados = Path(pasta_resultados)
        self.pasta_resultados.mkdir(exist_ok=True)
    
    def salvar_processamento(self, resultado: Dict) -> str:
        """Salva em arquivo JSON"""
        arquivo = self.pasta_resultados / f"processamento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(arquivo, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, indent=2, ensure_ascii=False)
        
        return str(arquivo)
    
    def salvar_analise_completa(self, resultados: Dict) -> str:
        """Salva análise completa em arquivo JSON"""
        arquivo = self.pasta_resultados / f"analise_{resultados['trimestre']}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        
        with open(arquivo, 'w', encoding='utf-8') as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
        
        return str(arquivo)
    
    def buscar_analises(self, trimestre: str = None) -> List[Dict]:
        """Busca análises em arquivos JSON"""
        analises = []
        
        for arquivo in self.pasta_resultados.glob("analise_*.json"):
            if trimestre and trimestre not in arquivo.name:
                continue
                
            try:
                with open(arquivo, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    dados['arquivo_origem'] = str(arquivo)
                    analises.append(dados)
            except Exception as e:
                print(f"Erro ao ler {arquivo}: {e}")
        
        return sorted(analises, key=lambda x: x.get('timestamp', ''), reverse=True)
    
    def obter_estatisticas(self) -> Dict:
        """Estatísticas básicas dos arquivos"""
        arquivos = list(self.pasta_resultados.glob("*.json"))
        
        return {
            'total_arquivos': len(arquivos),
            'analises_completas': len(list(self.pasta_resultados.glob("analise_*.json"))),
            'processamentos': len(list(self.pasta_resultados.glob("processamento_*.json")))
        }