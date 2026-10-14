# Cartola_FC_Tournament_Analysis

Para rodar, você precisa de um arquivo chamado "config.txt" com o seguinte conteúdo:

![image](https://github.com/g-claudino/Cartola_FC_Tournament_Analysis/assets/34245682/99ac5ef9-8732-4204-9ea9-823b479323f2)

Lembre de trocar o conteúdo da linha 1 e 2 do txt pelos valores do "Authorization" e "X-GLB-Tag" que você consegue pegar inspecionando uma request do tipo get dentro do site do cartola. Exemplo:
![image](https://github.com/g-claudino/Cartola_FC_Tournament_Analysis/assets/34245682/d449d44b-cee8-4384-891f-e60b6c61a01b)

As principais rotinas virão a partir da primeira rodada. 

## Segunda fase (rodadas 31–38)

16 times divididos em duas chaves de 8 pela classificação após a rodada 30:
**Chave Principal** (1º–8º) e **Chave dos Perdedores** (9º–16º). Em cada chave,
todos jogam contra todos uma vez nas rodadas 31–37 (confronto direto: mais pontos
no Cartola na rodada vence; vitória 3, empate 1). Na rodada 38: final 1º x 2º e
disputas de 3º, 5º e 7º lugar. Empate na rodada 38 favorece o melhor colocado.

1. Uma vez, com o `config.txt` preenchido: `python segunda_fase.py ids` (salva os `time_id` em `segunda_fase/config_fase2.json`) e commite o JSON.
2. Ative o GitHub Pages em *Settings → Pages → Deploy from branch → main /docs*.
3. A action `.github/workflows/segunda_fase.yml` roda a cada 2 h, busca as pontuações em endpoints públicos (sem token) e atualiza `docs/index.html`.

Outros comandos: `python segunda_fase.py tabela` (confrontos) e `python segunda_fase.py simular 34` (teste offline).
