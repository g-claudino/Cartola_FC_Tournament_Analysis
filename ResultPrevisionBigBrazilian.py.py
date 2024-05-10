import pandas as pd
import requests as rq
import io
from scipy.stats import poisson
import json

pd.options.mode.chained_assignment = None

def obter_tabelas():
    """
    Obtém a tabela de classificação e de jogos (já jogados e futuros), bem como gols feitos do WikiPedia
    """
    requisicao = rq.get("https://pt.wikipedia.org/wiki/Campeonato_Brasileiro_de_Futebol_de_2024_-_S%C3%A9rie_A")
    tabelas = pd.read_html(io.StringIO(str(requisicao.text)))
    return tabelas[6], tabelas[7]

def formatar_tabela_jogos(tabela_jogos, dic_para_times):
    """
    Formata a tabela de jogos, ajustando os nomes dos times
    """
    tabela_jogos_ajustada = tabela_jogos.set_index(r'Casa \ Fora').unstack().reset_index()
    tabela_jogos_ajustada = tabela_jogos_ajustada.rename(columns={'level_0': "fora", r'Casa \ Fora': "casa", 0: 'resultado'})

    def ajustar_apelido_times(linha):
        apelido = linha["fora"]
        nome = dic_para_times[apelido]
        return nome

    tabela_jogos_ajustada['fora'] = tabela_jogos_ajustada.apply(ajustar_apelido_times, axis=1)
    tabela_jogos_ajustada = tabela_jogos_ajustada[tabela_jogos_ajustada['fora'] != tabela_jogos_ajustada['casa']]

    return tabela_jogos_ajustada

def obter_partidas_rodadas():
    """
    Obtém as partidas da rodada atual no CartolaFC e ajusta os nomes dos times para equivaler à tabela de estatísticas
    """
    data = rq.get("https://api.cartola.globo.com/partidas").json()

    partidas = [{'rodada': data['rodada']}, []]
    x = 0
    substituicoes ={
        'Atlético-MG':'Atlético Mineiro',
         'Vasco': 'Vasco da Gama',
           'Athlético-PR': 'Athletico Paranaense',
            'Atlético-GO': 'Atlético Goianiense',
            'Bragantino':'Red Bull Bragantino' }

    for partida in data['partidas']:
        x+=1
        clube_visitante = data['clubes'][str(partida['clube_visitante_id'])]['nome']
        clube_casa = data['clubes'][str(partida['clube_casa_id'])]['nome']
        if clube_visitante in substituicoes:
            clube_visitante = substituicoes[clube_visitante]
        if clube_casa in substituicoes:
            clube_casa = substituicoes[clube_casa]

        partidas[1].append({'jogo': x, 'clube_casa': clube_casa, 'clube_visitante': clube_visitante})

    return partidas

def calcular_estatisticas(tabela_jogos_realizados):
    """"
    Separa os gols fora e dentro de casa e relaciona para cada time do campeonato
    """
    colunas = ['gols_casa', 'gols_fora']
    tabela_jogos_realizados[colunas] = tabela_jogos_realizados['resultado'].str.split('–', expand=True)
    tabela_jogos_realizados = tabela_jogos_realizados.drop(columns=['resultado'])
    tabela_jogos_realizados['gols_casa'] = tabela_jogos_realizados['gols_casa'].astype(int)
    tabela_jogos_realizados['gols_fora'] = tabela_jogos_realizados['gols_fora'].astype(int)

    media_gols_casa = tabela_jogos_realizados.groupby('casa').mean(numeric_only=True)
    media_gols_casa = media_gols_casa.rename(columns={"gols_casa": "gols_feitos_casa", 'gols_fora': "gols_sofridos_casa"})

    media_gols_fora = tabela_jogos_realizados.groupby('fora').mean(numeric_only=True)
    media_gols_fora = media_gols_fora.rename(columns={"gols_casa": "gols_sofridos_fora", 'gols_fora': "gols_feitos_fora"})

    tabela_estatistica = media_gols_casa.merge(media_gols_fora, left_index=True, right_index=True).reset_index()
    tabela_estatistica = tabela_estatistica.rename(columns={'casa': 'time'})

    return tabela_estatistica

def calcular_probabilidade_resultados(time_casa, time_fora, tabela_estatistica):
    """
    Usa o método de Poison para simular os todas as probabilidades de resultados nos jogos até o 
    máximo de 7 gols para cada time.

    Usa para o time de casa: gols feitos dentro de casa * gols sofridos fora de casa do adversário

    Usa para o time fora de casa: gols feitos fora de casa * gols tomados dentro de casa do time adversário

    Ao final calcula a probabilidade de vitória do time da casa, empate e vitória do time de fora
    """
    lambda_casa = (tabela_estatistica.loc[tabela_estatistica['time'] == time_casa, 'gols_feitos_casa'].iloc[0] * 
                   tabela_estatistica.loc[tabela_estatistica['time'] == time_fora, 'gols_sofridos_fora'].iloc[0])
    
    lambda_fora = (tabela_estatistica.loc[tabela_estatistica['time'] == time_fora, 'gols_feitos_fora'].iloc[0] *
                   tabela_estatistica.loc[tabela_estatistica['time'] == time_casa, 'gols_sofridos_casa'].iloc[0])

    pv_casa = 0
    p_empate = 0
    pv_fora = 0

    for gols_casa in range(7):
        for gols_fora in range(7):
            probabilidade_resultado = poisson.pmf(gols_casa, lambda_casa) * poisson.pmf(gols_fora, lambda_fora)
            if gols_casa == gols_fora:
                p_empate += probabilidade_resultado
            elif gols_casa > gols_fora:
                pv_casa += probabilidade_resultado
            else:
                pv_fora += probabilidade_resultado

    return pv_casa, p_empate, pv_fora

def prever_gols(time_casa, time_fora, tabela_estatistica):
    """
    Usando a média de gols fora e dentro de casa, calcula uma expectativa de gols para cada time.
    """
    media_gols_casa = tabela_estatistica.loc[tabela_estatistica['time'] == time_casa, 'gols_feitos_casa'].iloc[0]
    media_gols_fora = tabela_estatistica.loc[tabela_estatistica['time'] == time_fora, 'gols_feitos_fora'].iloc[0]

    return media_gols_casa, media_gols_fora

def main():
    tabela_classificacao, tabela_jogos = obter_tabelas()
    # Ajustando a tabela de jogos, substituindo as abreviações dos times pelo nome
    nomes_times = list(tabela_jogos[r'Casa \ Fora'])
    abreviacao_time = list(tabela_jogos.columns)
    abreviacao_time.pop(0)
    dic_para_times = dict(zip(abreviacao_time, nomes_times))
    tabela_jogos_ajustada = formatar_tabela_jogos(tabela_jogos, dic_para_times)
    # Tratamento de dados de dados em branco e separação dos jogos que já foram jogados dos jogos que faltam jogar
    tabela_jogos_ajustada['resultado'] = tabela_jogos_ajustada['resultado'].fillna('a jogar')
    tabela_jogos_realizados = tabela_jogos_ajustada[tabela_jogos_ajustada['resultado'].str.contains("–")]
    tabela_jogos_faltantes = tabela_jogos_ajustada[~tabela_jogos_ajustada['resultado'].str.contains("–")]
    tabela_jogos_faltantes = tabela_jogos_faltantes.drop(columns=['resultado'])
    # Cálculo de estatística das médias de gols feitos e sofridos  fora e dentro de casa de cada time
    tabela_estatistica = calcular_estatisticas(tabela_jogos_realizados)

    partidas = obter_partidas_rodadas()
    print("🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨")
    print("ATENÇÃO ISSO É UMA FASE DE TESTE")
    print("🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧")
    print("PROTÓTIPO DE PREVISÃO DE RESULTADO LEVANDO EM CONSIDERAÇÃO APENAS GOLS FORA E DENTRO DE CASA")
    print("")
    print(f"RODADA: {partidas[0]['rodada']}")

    # Para cada jogo na rodada, calcular probabilidade de resultado usando Poison e uma expectativa de golsusando a média de gols dentro e fora de casa
    
    for partida in partidas[1]:
        jogo = partida['jogo']
        time_casa = partida['clube_casa']
        time_fora = partida['clube_visitante']
        print("")
        print(f"Jogo {jogo}: {time_casa} x {time_fora}")
        print("")

        pv_casa, p_empate, pv_fora = calcular_probabilidade_resultados(time_casa, time_fora, tabela_estatistica)
        print("Vitória de", time_casa + ":", round(pv_casa * 100, 2), "%")
        print("Empate:", round(p_empate * 100, 2), "%")
        print("Vitória de", time_fora + ":", round(pv_fora * 100, 2), "%")

        media_gols_casa, media_gols_fora = prever_gols(time_casa, time_fora, tabela_estatistica)
        print("Média de gols esperados para", time_casa + ":", round(media_gols_casa, 2))
        print("Média de gols esperados para", time_fora + ":", round(media_gols_fora, 2))

        lambda_casa = tabela_estatistica.loc[tabela_estatistica['time'] == time_casa, 'gols_feitos_casa'].iloc[0] * tabela_estatistica.loc[tabela_estatistica['time'] == time_fora, 'gols_sofridos_fora'].iloc[0]
        lambda_fora = tabela_estatistica.loc[tabela_estatistica['time'] == time_fora, 'gols_feitos_fora'].iloc[0] * tabela_estatistica.loc[tabela_estatistica['time'] == time_casa, 'gols_sofridos_casa'].iloc[0]
        print("")
        print('#############################################################')


if __name__ == "__main__":
    main()
