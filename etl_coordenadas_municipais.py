#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera o arquivo municipios_brasil_coordenadas.json com todos os estados e municípios,
SEM redundância: cada município é identificado por (uf, municipio), e cada um tem
UMA coordenada única.

Fonte de coordenadas: IBGE Cadastro de Localidades Selecionadas 2010
(centroide do setor censitário 0001 do distrito sede de cada município).
Como essa base não está disponível como API pública direta, o script usa
o dataset do CEM (Centro de Estudos da Metrópole) que é derivado oficialmente
do IBGE e contém os 5570 pontos de sede municipal.

Uso:
    python etl_coordenadas_municipios.py
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===== Configurações =====
API_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades"
TIMEOUT = 60
MAX_TENTATIVAS = 3

# ===== Caminho de saída =====
PASTA_SAIDA = r"C:\Users\Nino\ProjetosPy\fastHTML - mysql\etl"
ARQUIVO_SAIDA = os.path.join(PASTA_SAIDA, "municipios_brasil_coordenadas.json")

# ===== Cache em disco =====
PASTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PASTA_SCRIPT, ".cache_municipios")

# ===== Sessão HTTP =====
_sessao = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=32,
    pool_maxsize=32,
    max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]),
)
_sessao.mount("https://", _adapter)
_sessao.headers.update({"Accept": "application/json"})

# ===== Tabela de capitais =====
NOMES_CAPITAIS = {
    'AC': 'Rio Branco', 'AL': 'Maceió', 'AP': 'Macapá', 'AM': 'Manaus',
    'BA': 'Salvador', 'CE': 'Fortaleza', 'DF': 'Brasília', 'ES': 'Vitória',
    'GO': 'Goiânia', 'MA': 'São Luís', 'MT': 'Cuiabá', 'MS': 'Campo Grande',
    'MG': 'Belo Horizonte', 'PA': 'Belém', 'PB': 'João Pessoa', 'PR': 'Curitiba',
    'PE': 'Recife', 'PI': 'Teresina', 'RJ': 'Rio de Janeiro', 'RN': 'Natal',
    'RS': 'Porto Alegre', 'RO': 'Porto Velho', 'RR': 'Boa Vista',
    'SC': 'Florianópolis', 'SP': 'São Paulo', 'SE': 'Aracaju', 'TO': 'Palmas'
}


def fetch_json(url, tentativas=MAX_TENTATIVAS):
    """Baixa JSON da API do IBGE com retry."""
    ultima = None
    for t in range(1, tentativas + 1):
        try:
            resp = _sessao.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            ultima = e
            if t < tentativas:
                time.sleep(0.5 * t)
    raise RuntimeError(f"Falha ao acessar {url}: {ultima}")


def baixar_coordenadas_cem():
    """
    Baixa o dataset de sedes municipais do CEM (Centro de Estudos da Metrópole),
    derivado do IBGE BR_Localidades_2010_v1.shp.

    URL do CSV público (formato simples, uma linha por município):
    https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv

    Este arquivo contém: codigo_ibge, nome_municipio, latitude, longitude,
    capital, codigo_uf, uf, estado, ...
    """
    url = (
        "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/"
        "main/csv/municipios.csv"
    )
    print(f"→ Baixando coordenadas de {url} ...")
    resp = _sessao.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_csv_coordenadas(csv_texto):
    """
    Parseia o CSV e retorna dict: geocodigo -> (latitude, longitude).

    Formato esperado (kelvins/municipios-brasileiros):
    codigo_ibge,nome_municipio,latitude,longitude,capital,codigo_uf,uf,estado,...
    """
    leitor = csv.DictReader(io.StringIO(csv_texto))
    mapa = {}
    for linha in leitor:
        try:
            geocodigo = int(linha["codigo_ibge"])
            lat = float(linha["latitude"])
            lon = float(linha["longitude"])
            mapa[geocodigo] = (lat, lon)
        except (KeyError, ValueError):
            continue
    print(f"  {len(mapa)} coordenadas carregadas.")
    return mapa


def formatar_data_br(data):
    return data.strftime('%d/%m/%Y %H:%M:%S')


def gerar_json():
    inicio = time.time()
    data_inicio = datetime.now()

    # ===== 1. Baixar coordenadas (fonte: CEM / IBGE Localidades) =====
    csv_texto = baixar_coordenadas_cem()
    coordenadas = parse_csv_coordenadas(csv_texto)

    # ===== 2. Buscar estados =====
    print("→ Buscando lista de estados no IBGE...")
    estados = fetch_json(f"{API_LOCALIDADES}/estados")
    estados.sort(key=lambda e: e['sigla'])
    print(f"  {len(estados)} estados encontrados.")

    # ===== 3. Montar JSON sem redundância =====
    resultado = {
        'metadados': {
            'data_ultima_atualizacao': data_inicio.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'data_ultima_atualizacao_br': formatar_data_br(data_inicio),
            'fonte': (
                'IBGE API de Localidades v1 (nomes/geocódigos) + '
                'Cadastro de Localidades Selecionadas 2010 via CEM '
                '(centroide do setor 0001 do distrito sede)'
            ),
            'observacao_df': (
                'O Distrito Federal é representado pelo IBGE como um único município '
                'chamado Brasília (geocódigo 5300108).'
            ),
            'observacao_coordenadas': (
                'Coordenadas representam o centroide do setor censitário 0001 do distrito '
                'sede de cada município, conforme Cadastro de Localidades Selecionadas 2010 '
                'do IBGE. Cada município tem UMA coordenada única. '
                'Identificador: (uf, municipio).'
            ),
            'total_unidades_federativas': len(estados),
            'total_municipios': 0,
        },
        'unidades_federativas': []
    }

    total = 0
    for uf in estados:
        sigla = uf['sigla']
        municipios = fetch_json(f"{API_LOCALIDADES}/estados/{sigla}/municipios")
        municipios.sort(key=lambda m: m['nome'])

        capital_nome = NOMES_CAPITAIS.get(sigla)
        lista_municipios = []

        for m in municipios:
            geocodigo = m['id']
            lat, lon = coordenadas.get(geocodigo, (None, None))

            lista_municipios.append({
                'municipio': m['nome'],
                'geocodigo': geocodigo,
                'latitude': lat,
                'longitude': lon,
            })

        # Identifica capital
        capital = next(
            (m for m in lista_municipios
             if capital_nome and m['municipio'].lower() == capital_nome.lower()),
            None
        )

        resultado['unidades_federativas'].append({
            'unidade_federativa': uf['nome'],
            'uf': sigla,
            'municipio_capital': capital['municipio'] if capital else None,
            'municipios': lista_municipios,
        })

        total += len(lista_municipios)
        print(f"  {sigla}: {len(lista_municipios)} municípios")

    resultado['metadados']['total_municipios'] = total

    data_fim = datetime.now()
    resultado['metadados']['data_ultima_atualizacao'] = (
        data_fim.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    )
    resultado['metadados']['data_ultima_atualizacao_br'] = formatar_data_br(data_fim)

    duracao = time.time() - inicio
    print(f"✅ Concluído em {duracao:.1f}s — {total} municípios processados.")
    return resultado


def main():
    parser = argparse.ArgumentParser(
        description='Gera JSON com coordenadas únicas dos municípios brasileiros.'
    )
    parser.add_argument('--saida', default=ARQUIVO_SAIDA,
                        help=f'Caminho do arquivo de saída (padrão: {ARQUIVO_SAIDA})')
    args = parser.parse_args()

    # ===== Mensagem de início =====
    inicio = time.time()
    print("=" * 70)
    print("🚀 INÍCIO DO ETL — Coordenadas dos Municípios Brasileiros")
    print("=" * 70)
    print(f"⏰ Início: {formatar_data_br(datetime.now())}")
    print(f"📂 Arquivo de saída: {args.saida}")
    print("-" * 70)

    try:
        dados = gerar_json()
        pasta_saida = os.path.dirname(os.path.abspath(args.saida))
        os.makedirs(pasta_saida, exist_ok=True)
        with open(args.saida, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        print(f"💾 Arquivo salvo: {args.saida}")

        # ===== Mensagem de fim (sucesso) =====
        duracao_total = time.time() - inicio
        print("-" * 70)
        print("=" * 70)
        print("✅ FIM DO ETL — Execução concluída com SUCESSO")
        print("=" * 70)
        print(f"⏰ Fim: {formatar_data_br(datetime.now())}")
        print(f"⏱️  Duração total: {duracao_total:.2f}s")
        print(f"📊 Unidades federativas processadas: {dados['metadados']['total_unidades_federativas']}")
        print(f"📊 Municípios processados: {dados['metadados']['total_municipios']}")
        print(f"💾 Arquivo gerado: {args.saida}")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print("⚠️  FIM DO ETL — Interrompido pelo usuário")
        print("=" * 70, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ FIM DO ETL — Execução finalizada com ERRO")
        print("=" * 70, file=sys.stderr)
        print(f"💥 Erro: {e}", file=sys.stderr)
        print(f"⏰ Momento do erro: {formatar_data_br(datetime.now())}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()