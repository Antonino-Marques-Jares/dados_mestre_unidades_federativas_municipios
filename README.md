# dados_mestre_unidades_federativas_municipios

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

Visualize:
[Unidades Federativas e Municípios](https://www.areadetrampo.com.br/municipios-brasileiros/)
