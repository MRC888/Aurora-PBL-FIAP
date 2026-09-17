# =====================================================================
# PROJETO AURORA - VERIFICACAO DE DECOLAGEM E SIMULACAO DE MISSAO
# =====================================================================
# ESTE E O UNICO PROGRAMA DO PROJETO. ELE RODA DE CIMA PARA BAIXO, COMO UM
# ROTEIRO, EM NOVE ETAPAS:
#
#   ETAPA 0  introducao e identificacao do capitao
#   ETAPA 1  leitura de cinco dados e avaliacao automatica da integridade
#   ETAPA 2  analise energetica (item 1.4)
#   ETAPA 3  verificacoes de seguranca (item 1.2)
#   ETAPA 4  analise assistida por IA (item 1.5)
#   ETAPA 5  parecer da IA e veredito final
#   ETAPA 6  registro do cenario (pasta cenarios/)
#   ETAPA 7  simulacao da missao Terra -> Marte (so se a decolagem foi autorizada)
#   ETAPA 8  registro da missao (pasta missoes/)
#
# NAO HA FUNCOES. TODAS AS CONSTANTES ESTAO NO TOPO, E CADA VARIAVEL NASCE
# NA ETAPA EM QUE E USADA PELA PRIMEIRA VEZ. O PROGRAMA E AUTOSSUFICIENTE:
# ESTE SCRIPT NAO DEPENDE DE ARQUIVOS AUXILIARES PARA EXECUTAR.
#
# COMO USAR:  python scripts/main.py
# =====================================================================

# BIBLIOTECAS PARA VALIDAR MEDIDAS E GRAVAR OS RESULTADOS EM DISCO.
import math                     # VALIDA SE AS MEDIDAS SAO FINITAS
import csv                      # ESCREVE PLANILHAS NO FORMATO CSV (ABRE NO EXCEL)
import os                       # LIDA COM PASTAS E CAMINHOS DE ARQUIVO
from datetime import datetime   # CARIMBA A DATA E HORA DE CADA EXECUCAO


# =====================================================================
# CONSTANTES DO PROJETO
# =====================================================================
# EM MAIUSCULO POR CONVENCAO: SAO VALORES FIXOS, DEFINIDOS ANTES DO PROGRAMA
# COMECAR. PARA MUDAR UMA REGRA DA NAVE, MUDA-SE AQUI, E NAO NO MEIO DO CODIGO.

# --- A NAVE (ROADMAP 1.4) ---
CAPACIDADE_TOTAL = 1000.0   # kWh - capacidade total da bateria
CONSUMO_DECOLAGEM = 300.0   # kWh - consumo estimado na fase de decolagem
PERDAS = 0.08               # 8% da energia armazenada se perde (conversao do inversor + aquecimento)
RESERVA_MINIMA = 0.10       # 10% da capacidade deve sobrar como reserva de pouso

# --- FAIXAS SEGURAS DA TELEMETRIA (ROADMAP 1.1) ---
TEMP_INTERNA_MIN = 15.0     # C
TEMP_INTERNA_MAX = 30.0     # C
TEMP_EXTERNA_MIN = -10.0    # C
TEMP_EXTERNA_MAX = 45.0     # C
PRESSAO_MIN = 450.0         # psi
PRESSAO_MAX = 550.0         # psi
ENERGIA_MINIMA = 80.0       # % - abaixo disso a decolagem e abortada

# --- LIMIARES DA ANALISE ASSISTIDA POR IA ---
TEMP_EXTERNA_FRIA = 0.0         # C - abaixo disso a bateria de litio perde capacidade utilizavel
ENERGIA_CONFORTAVEL = 90.0      # % - energia abaixo disso no frio gera alerta
PRESSAO_ALTA = 520.0            # psi - pressao acima disso com cabine quente gera alerta
TEMP_INTERNA_QUENTE = 27.0      # C - cabine quente (lei dos gases)
TEMP_INTERNA_ALERTA = 28.0      # C - proxima do teto, e os motores ainda vao aquecer
DIFERENCIAL_TERMICO_MAX = 35.0  # C - diferenca interna/externa que sugere falha de isolamento
FRONTEIRA_ENERGIA = 2.0         # % - energia entre 80 e 82 esta no limiar (incerteza tipica do sensor)
FRONTEIRA_PRESSAO = 10.0        # psi - faixa de "fronteira" junto aos limites 450 e 550
AUTONOMIA_BAIXA = 20.0          # % - reserva pos-decolagem abaixo disso e pouca folga

# A TELEMETRIA "PERFEITA" QUE LEVANTA SUSPEITA DE VALOR PADRAO DE FABRICA:
NOMINAL_TEMP_INTERNA = 22.0
NOMINAL_TEMP_EXTERNA = 25.0
NOMINAL_PRESSAO = 500.0
NOMINAL_ENERGIA = 100.0

# --- MISSAO: CUSTOS PONTUAIS APOS A DECOLAGEM, EM % DA BATERIA ---
# A decolagem NAO e descontada novamente aqui: o item 1.4 ja aplicou as perdas
# e subtraiu CONSUMO_DECOLAGEM em kWh. A missao parte de autonomia_restante.
CUSTO_MANOBRA = 5.0      # cada ajuste de rota durante o cruzeiro
CUSTO_FRENAGEM = 5.0     # ASSUMIDO: o documento nao da o numero; usei o de uma manobra
CUSTO_POUSO = 10.0       # retropropulsao "para nao virar um meteoro"

# --- MISSAO: RESERVA E ESTADOS ---
RESERVA_CRITICA = 30.0   # % minima para a manobra de volta a Terra
LIMIAR_VERDE = 70.0      # ASSUMIDO: bateria >= 70%  -> VERDE
LIMIAR_AMARELO = 50.0    # ASSUMIDO: 50% <= bateria < 70% -> AMARELO; abaixo -> VERMELHO
FOLGA_MARGEM = 10.0      # ASSUMIDO: o alerta de margem so desliga acima de 30 + 10, para nao piscar

# QUANTAS HORAS ENTRE UMA LINHA DE TELEMETRIA E OUTRA NA TELA.
# O ARQUIVO TXT GUARDA TODAS AS HORAS; SO A TELA E REDUZIDA.
FREQUENCIA_TELEMETRIA = {"VERDE": 1, "AMARELO": 2, "VERMELHO": 4}

DESCRICAO_ESTADO = {
    "VERDE":    "performance maxima, todos os sistemas ativos",
    "AMARELO":  "MODO DE OTIMIZACAO: prioridade 3 desligada, comunicacao economica, telemetria a cada 2 h",
    "VERMELHO": "MODO DE SOBREVIVENCIA: prioridades 2 e 3 desligadas, so o essencial, telemetria a cada 4 h",
}

# --- MISSAO: SISTEMAS DA NAVE, CONSUMO EM % POR HORA ---
# UMA LISTA DE DICIONARIOS: CADA SISTEMA E UMA "FICHA" COM NOME, CONSUMO E PRIORIDADE.
SISTEMAS = [
    {"nome": "Suporte a vida",        "consumo": 0.5, "prioridade": 1},
    {"nome": "Navegacao e IA",        "consumo": 0.3, "prioridade": 1},
    {"nome": "Comunicacao",           "consumo": 0.2, "prioridade": 2, "economico": 0.1},  # ASSUMIDO: modo economico = metade
    {"nome": "Sensores e cameras",    "consumo": 0.2, "prioridade": 3},
    {"nome": "Iluminacao e internos", "consumo": 0.1, "prioridade": 3},
]

# --- MISSAO: RECARGA SOLAR, GANHO EM % POR HORA ---
RECARGA = {
    "total":   0.8,   # espaco aberto
    "parcial": 0.2,   # sombra parcial ou poeira nos paineis
    "eclipse": 0.0,   # sombra total (atras de um planeta)
    "fechado": 0.0,   # paineis recolhidos (atmosfera ou tempestade solar)
}

# --- MISSAO: ROTAS E ROTEIRO (5.1) ---
# ASSUMIDO: as duracoes sao uma escala didatica, em "horas de simulacao".
LIMIAR_ROTA_RAPIDA = 90.0   # bateria >= 90% -> rota rapida; abaixo -> economica
ROTAS = {
    "RAPIDA":    {"nome": "Rota Rapida",              "horas_cruzeiro": 60,  "manobras": 4},
    "ECONOMICA": {"nome": "Rota Economica (Hohmann)", "horas_cruzeiro": 100, "manobras": 2},
}
HORAS_ATMOSFERA = 2
HORAS_ORBITA_MARTE = 10
HORAS_SUPERFICIE = 24
TEMPESTADE_SOLAR = {"inicio": 30, "duracao": 6}    # hora do cruzeiro em que comeca, e quantas horas dura
TEMPESTADE_POEIRA = {"inicio": 8, "duracao": 12}   # hora na superficie em que comeca, e quantas horas dura

# --- O QUE APARECE NA TELA DURANTE A MISSAO ---
# False = A TELA MOSTRA SO O CABECALHO DA MISSAO E O RESUMO FINAL.
# True  = MOSTRA TAMBEM O VOO HORA A HORA (fases, decisoes da IA, eventos e a tabela).
# A CAIXA PRETA (missoes/missao_XX_STATUS.txt) GUARDA TUDO NOS DOIS CASOS.
MOSTRAR_VOO_NA_TELA = False

# --- ONDE OS REGISTROS SAO GRAVADOS ---
# DESCOBRE A PASTA DO PROJETO A PARTIR DESTE ARQUIVO, PARA SALVAR SEMPRE NO
# MESMO LUGAR, INDEPENDENTE DE ONDE O PROGRAMA TENHA SIDO EXECUTADO.
PASTA_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PASTA_PROJETO = os.path.normpath(os.path.join(PASTA_SCRIPTS, ".."))
PASTA_CENARIOS = os.path.join(PASTA_PROJETO, "cenarios")
PASTA_MISSOES = os.path.join(PASTA_PROJETO, "missoes")


# =====================================================================
# ETAPA 0 - INTRODUCAO E IDENTIFICACAO DO CAPITAO
# =====================================================================
print("=" * 62)
print("EXPEDICAO AURORA - CONTROLE DE MISSAO")
print("=" * 62)
print("Seja bem-vindo a Expedicao Aurora.")
nome_capitao = input("Identifique-se, capitao: ").strip()
if nome_capitao == "":
    nome_capitao = "Anonimo"   # SE A PESSOA SO APERTAR ENTER, O REGISTRO NAO FICA VAZIO

print("")
print("Capitao {}, estamos preparando todas as metricas da nave.".format(nome_capitao))
print("Para isso precisamos de algumas informacoes da telemetria.")
print("Informe cada valor conforme for pedido. Use ponto para decimais (ex: 22.5).")
print("")


# =====================================================================
# ETAPA 1 - LEITURA DA TELEMETRIA
# =====================================================================
# O OPERADOR INFORMA MEDIDAS, E O SISTEMA CALCULA A INTEGRIDADE.
# REJEITA TEXTO, NaN E INFINITO ANTES DE USAR OS DADOS NO DIAGNOSTICO.
telemetria = []
for pergunta in ["Digite a temperatura interna: ",
                 "Digite a temperatura externa: ",
                 "Digite a pressão dos tanques: ",
                 "Digite a porcentagem de energia: "]:
    while True:
        try:
            valor = float(input(pergunta))
            if math.isfinite(valor):
                telemetria.append(valor)
                break
        except ValueError:
            pass
        print("Valor inválido: informe um número finito. Use ponto para decimais.")

temp_interna, temp_externa, pressao_tanques, energia = telemetria
entrada_modulos = input("Módulos online? (S/N): ").strip().upper()
while entrada_modulos not in ("S", "N"):
    print("Valor inválido: informe S ou N para o estado dos módulos.")
    entrada_modulos = input("Módulos online? (S/N): ").strip().upper()
modulos_online = entrada_modulos == "S"

# INTEGRIDADE OPERACIONAL ESTIMADA, DERIVADA DA TELEMETRIA.
# ESTES CRITERIOS DIDATICOS NAO SUBSTITUEM SENSORES DE DANOS NO CASCO.
# ENERGIA E RESERVA SAO AVALIADAS SEPARADAMENTE NA ETAPA ENERGETICA.
motivos_integridade = []
if not TEMP_INTERNA_MIN <= temp_interna <= TEMP_INTERNA_MAX:
    motivos_integridade.append("temperatura interna fora da faixa segura")
if not TEMP_EXTERNA_MIN <= temp_externa <= TEMP_EXTERNA_MAX:
    motivos_integridade.append("temperatura externa fora da faixa segura")
if not PRESSAO_MIN <= pressao_tanques <= PRESSAO_MAX:
    motivos_integridade.append("pressão dos tanques fora da faixa segura")
if not modulos_online:
    motivos_integridade.append("módulos críticos offline")
integridade = int(not motivos_integridade)
if motivos_integridade:
    diagnostico_integridade = "; ".join(motivos_integridade)
else:
    diagnostico_integridade = "temperaturas e pressão nas faixas seguras; módulos críticos online"

# CONVERTE OS DOIS INDICADORES PARA TEXTO LEGIVEL (USADO NA TELA E NOS REGISTROS).
if integridade == 1:
    integridade_texto = "1 (Preservada no modelo)"
else:
    integridade_texto = "0 (Comprometida no modelo)"

if modulos_online:
    modulos_texto = "SIM"
else:
    modulos_texto = "NAO"

# MOSTRA AS LEITURAS E O DIAGNOSTICO CALCULADO PELO SISTEMA.
print("")
print("=" * 62)
print("TELEMETRIA E DIAGNOSTICO AUTOMATICO")
print("=" * 62)
print("  Temperatura interna : {:.1f} C".format(temp_interna))
print("  Temperatura externa : {:.1f} C".format(temp_externa))
print("  Integridade calculada: {}".format(integridade_texto))
print("  Diagnostico         : {}".format(diagnostico_integridade))
print("  Pressao dos tanques : {:.1f} psi".format(pressao_tanques))
print("  Energia             : {:.1f} %".format(energia))
print("  Modulos online      : {}".format(modulos_texto))


# =====================================================================
# ETAPA 2 - ANALISE ENERGETICA (item 1.4)
# =====================================================================
# OS TERMOS E A ORDEM DAS CONTAS SEGUEM O MATERIAL DA DISCIPLINA:
#   energia disponivel  = capacidade total x carga atual (a "energia" digitada esta em %)
#   energia perdida     = parcela da energia disponivel que o sistema nao aproveita
#   energia util        = o que sobra da energia disponivel depois das perdas
#   energia restante    = energia util menos o consumo estimado na decolagem
energia_disponivel = CAPACIDADE_TOTAL * (energia / 100)            # ex: 1000 * 0.80 = 800 kWh
energia_perdida = energia_disponivel * PERDAS                       # ex: 800 * 0.08  = 64 kWh
energia_util = energia_disponivel - energia_perdida                 # ex: 800 - 64    = 736 kWh
energia_restante = energia_util - CONSUMO_DECOLAGEM                 # ex: 736 - 300   = 436 kWh
autonomia_restante = (energia_restante / CAPACIDADE_TOTAL) * 100   # a mesma sobra, em % da bateria

print("")
print("=" * 62)
print("ANALISE ENERGETICA")
print("=" * 62)
print("  Capacidade total            : {:.1f} kWh".format(CAPACIDADE_TOTAL))
print("  Carga atual                 : {:.1f} %".format(energia))
print("  Energia disponivel          : {:.1f} kWh".format(energia_disponivel))
print("  Perdas energeticas          : {:.0f} %".format(PERDAS * 100))
print("  Energia perdida             : {:.1f} kWh".format(energia_perdida))
print("  Energia util                : {:.1f} kWh".format(energia_util))
print("  Consumo na decolagem        : {:.1f} kWh".format(CONSUMO_DECOLAGEM))
print("  Energia apos a decolagem    : {:.1f} kWh ({:.1f}% da bateria)".format(energia_restante, autonomia_restante))
if energia_restante > 0:
    print("  Resultado: energia suficiente para a decolagem.")
else:
    print("  Resultado: energia insuficiente para a decolagem.")


# =====================================================================
# ETAPA 3 - VERIFICACOES DE SEGURANCA (item 1.2)
# =====================================================================
# CADA IF COMPARA UM PARAMETRO COM A FAIXA SEGURA DEFINIDA NAS CONSTANTES.
# FORA DA FAIXA, A CHAVE DE DECOLAGEM E DESLIGADA E O ERRO E INFORMADO.
# AS VERIFICACOES NAO PARAM NA PRIMEIRA FALHA: TODAS SAO EXECUTADAS, PARA O
# OPERADOR ENXERGAR TODOS OS PROBLEMAS DE UMA VEZ.
erros_seguranca = []       # MOTIVOS PERSISTIDOS NO RELATORIO TXT
decolagem_autorizada = True   # A CHAVE COMECA LIGADA; QUALQUER VERIFICACAO PODE DESLIGAR.

print("")
print("=" * 62)
print("VERIFICACOES DE SEGURANCA")
print("=" * 62)

# Verificacao 1 - TEMPERATURA INTERNA E EXTERNA
if temp_interna > TEMP_INTERNA_MAX or temp_interna < TEMP_INTERNA_MIN:
    print("Erro: Temperatura Interna fora do range!")
    erros_seguranca.append("Erro: Temperatura Interna fora do range!")
    decolagem_autorizada = False
else:
    print("Temperatura Interna: OK")

if temp_externa > TEMP_EXTERNA_MAX or temp_externa < TEMP_EXTERNA_MIN:
    print("Erro: Temperatura Externa fora do range!")
    erros_seguranca.append("Erro: Temperatura Externa fora do range!")
    decolagem_autorizada = False
else:
    print("Temperatura Externa: OK")

# Verificacao 2 - INTEGRIDADE
# O RESULTADO FOI CALCULADO NA ETAPA 1, SEM PERGUNTAR A INTEGRIDADE AO CAPITAO.
if integridade != 1:
    print("Erro: Integridade operacional comprometida no modelo!")
    erros_seguranca.append("Erro: Integridade operacional comprometida no modelo!")
    decolagem_autorizada = False
else:
    print("Integridade operacional: Preservada no modelo")

# Verificacao 3 - PRESSAO DOS TANQUES
if pressao_tanques < PRESSAO_MIN or pressao_tanques > PRESSAO_MAX:
    print("Erro: Pressão dos tanques fora do range!")
    erros_seguranca.append("Erro: Pressão dos tanques fora do range!")
    decolagem_autorizada = False
else:
    print("Pressão dos Tanques: OK")

# Verificacao 4 - ENERGIA
if energia < ENERGIA_MINIMA:
    print("Erro: Energia insuficiente!")
    erros_seguranca.append("Erro: Energia insuficiente!")
    decolagem_autorizada = False
elif energia_restante < CAPACIDADE_TOTAL * RESERVA_MINIMA:
    # DECOLA MAS NAO SOBRA CARGA PARA MANOBRA/POUSO -> TAMBEM ABORTA.
    # PROTECAO: COM AS CONSTANTES ATUAIS ESTE RAMO NUNCA RODA, PORQUE 80% DE CARGA
    # JA DEIXA 43,6% DE SOBRA. ELE PASSA A VALER SE CONSUMO_DECOLAGEM SUBIR
    # (EX: 600 kWh) OU SE ENERGIA_MINIMA DESCER.
    print("Erro: Reserva pós-decolagem insuficiente ({:.1f} kWh)!".format(energia_restante))
    erros_seguranca.append("Erro: Reserva pós-decolagem insuficiente ({:.1f} kWh)!".format(energia_restante))
    decolagem_autorizada = False
else:
    print("Energia: OK")

# Verificacao 5 - MODULOS ONLINE
if not modulos_online:
    print("Erro: Módulos offline!")
    erros_seguranca.append("Erro: Módulos offline!")
    decolagem_autorizada = False
else:
    print("Módulos: OK")


# =====================================================================
# ETAPA 4 - ANALISE ASSISTIDA POR IA (item 1.5)
# =====================================================================
# AS VERIFICACOES ACIMA OLHAM CADA PARAMETRO SOZINHO. ESTA ETAPA CRUZA OS
# DADOS ENTRE SI, PROCURANDO DISCREPANCIAS QUE NENHUMA VERIFICACAO ISOLADA
# CONSEGUE ENXERGAR. E UM SISTEMA ESPECIALISTA: A "INTELIGENCIA" ESTA NAS
# REGRAS DE CORRELACAO ENTRE OS SENSORES.
criticos = []   # LISTA DE DADOS IMPOSSIVEIS (TELEMETRIA NAO CONFIAVEL)
alertas = []    # LISTA DE COMBINACOES DE RISCO (DADOS VALIDOS, MAS PERIGOSOS)

# --- GRUPO 1: OS DADOS INFORMADOS SAO FISICAMENTE POSSIVEIS? ---
if energia > 100 or energia < 0:
    criticos.append("Energia de {:.1f}% está fora do domínio físico (0 a 100%). Sensor descalibrado ou erro de digitação.".format(energia))

if CAPACIDADE_TOTAL <= 0:
    criticos.append("Capacidade da bateria informada como {:.1f} kWh. Valor impossível.".format(CAPACIDADE_TOTAL))

if pressao_tanques < 0:
    criticos.append("Pressão negativa ({:.1f} psi) é fisicamente impossível em tanque pressurizado.".format(pressao_tanques))

# --- GRUPO 2: OS DADOS SAO COERENTES ENTRE SI? ---
diferenca_termica = abs(temp_interna - temp_externa)   # ABS = VALOR ABSOLUTO (SEM SINAL)

if temp_externa < TEMP_EXTERNA_FRIA and energia < ENERGIA_CONFORTAVEL:
    alertas.append("Energia em {:.0f}% com temperatura externa de {:.0f}C. Baterias de lítio perdem capacidade UTILIZÁVEL no frio: a autonomia real tende a ficar abaixo da calculada.".format(energia, temp_externa))

if pressao_tanques > PRESSAO_ALTA and temp_interna > TEMP_INTERNA_QUENTE:
    alertas.append("Pressão de {:.0f} psi já alta com temperatura interna de {:.0f}C. Pela lei dos gases a pressão sobe com o aquecimento, podendo ultrapassar {:.0f} psi durante a subida.".format(pressao_tanques, temp_interna, PRESSAO_MAX))

if diferenca_termica > DIFERENCIAL_TERMICO_MAX:
    alertas.append("Diferencial térmico de {:.0f}C entre interna e externa. Sugere falha de isolamento térmico ou sensor travado.".format(diferenca_termica))

# --- GRUPO 3: ALGUM PARAMETRO OPERA SEM MARGEM DE SEGURANCA? ---
if ENERGIA_MINIMA <= energia <= ENERGIA_MINIMA + FRONTEIRA_ENERGIA:
    alertas.append("Energia a {:.1f}%, no limiar dos {:.0f}% exigidos. Não sobra margem para a incerteza do próprio sensor (tipicamente +/- {:.0f}%).".format(
        energia, ENERGIA_MINIMA, FRONTEIRA_ENERGIA))

if PRESSAO_MIN <= pressao_tanques <= PRESSAO_MIN + FRONTEIRA_PRESSAO or PRESSAO_MAX - FRONTEIRA_PRESSAO <= pressao_tanques <= PRESSAO_MAX:
    alertas.append("Pressão de {:.0f} psi opera na fronteira da faixa segura ({:.0f} a {:.0f} psi).".format(pressao_tanques, PRESSAO_MIN, PRESSAO_MAX))

if temp_interna >= TEMP_INTERNA_ALERTA:
    alertas.append("Temperatura interna de {:.0f}C próxima do teto de {:.0f}C, e o calor dos motores ainda vai somar durante a decolagem.".format(temp_interna, TEMP_INTERNA_MAX))

# PROTECAO: COM AS CONSTANTES ATUAIS ESTE ALERTA SO APARECE EM CENARIOS JA ABORTADOS
# (SOBRA ABAIXO DE 20% EXIGE CARGA ABAIXO DE 54%, E 80% E O MINIMO). ELE PASSA A
# VALER EM CENARIOS AUTORIZADOS SE CONSUMO_DECOLAGEM SUBIR.
if 0 < autonomia_restante < AUTONOMIA_BAIXA:
    alertas.append("Reserva pós-decolagem de apenas {:.1f}% da bateria. Pouca folga para manobra e pouso.".format(autonomia_restante))

# --- GRUPO 4: A TELEMETRIA PARECE REAL? ---
if temp_interna == NOMINAL_TEMP_INTERNA and temp_externa == NOMINAL_TEMP_EXTERNA and pressao_tanques == NOMINAL_PRESSAO and energia == NOMINAL_ENERGIA:
    alertas.append("Todos os canais retornaram exatamente o valor nominal. Em hardware real isso é estatisticamente improvável: conferir se os sensores não estão devolvendo valor padrão de fábrica.")


# =====================================================================
# ETAPA 5 - PARECER DA IA E VEREDITO FINAL
# =====================================================================
print("")
print("=" * 62)
print("ANÁLISE ASSISTIDA POR IA - DIAGNÓSTICO DE DISCREPÂNCIAS")
print("=" * 62)

if criticos:   # UMA LISTA VAZIA E AVALIADA COMO FALSA PELO PYTHON
    print("")
    print("DISCREPÂNCIAS CRÍTICAS (telemetria não confiável):")
    for item in criticos:   # O FOR PERCORRE CADA ITEM GUARDADO NA LISTA
        print("  [X] " + item)

if alertas:
    print("")
    print("ALERTAS (dados válidos, mas em combinação de risco):")
    for item in alertas:
        print("  [!] " + item)

print("")
if criticos:
    print(">> PARECER: DADOS INCONSISTENTES.")
    print("   A decolagem não pode ser avaliada com telemetria corrompida.")
    decolagem_autorizada = False   # A IA TAMBEM PODE DESLIGAR A CHAVE
elif not decolagem_autorizada:
    print(">> PARECER: DECOLAGEM JÁ BLOQUEADA pelas verificações de segurança.")
    print("   Corrigir a causa raiz antes de nova tentativa.")
elif alertas:
    print(">> PARECER: DECOLAGEM VIÁVEL, COM RESSALVAS.")
    print("   {} ponto(s) de atenção acima. Recomenda-se revisão humana.".format(len(alertas)))
else:
    print(">> PARECER: SUCESSO ABSOLUTO.")
    print("   Nenhuma discrepância encontrada no cruzamento dos dados.")

print("=" * 62)
print("")

# CLASSIFICACAO DO CENARIO (OTIMO / MEDIO / HORRIVEL)
# A ORDEM DOS TESTES IMPORTA: UM CENARIO HORRIVEL TAMBEM PODE TER ALERTAS NA LISTA,
# ENTAO A CHAVE DESLIGADA E VERIFICADA ANTES DOS ALERTAS.
if not decolagem_autorizada:
    classificacao = "HORRIVEL"
elif alertas:
    classificacao = "MEDIO"
else:
    classificacao = "OTIMO"

# Verificacao Final - DECOLAGEM
# NO CENARIO MEDIO A CHAVE AINDA ESTA LIGADA, MAS A PALAVRA FINAL E DO CAPITAO.
if classificacao == "OTIMO":
    print("Decolagem Autorizada!")
elif classificacao == "HORRIVEL":
    print("Decolagem Não Autorizada!")
else:
    print("Decolagem em espera: existem alertas aguardando a decisão do capitão.")

# DECISÃO DO CAPITÃO (só existe no cenário MEDIO)
# O CAPITAO E MAIS UMA VERIFICACAO: ELE SO PODE DESLIGAR A CHAVE, NUNCA LIGAR.
# QUALQUER RESPOSTA DIFERENTE DE "s" (ENTER VAZIO, "n", "talvez") VETA A DECOLAGEM.
if classificacao == "MEDIO":
    resposta = input("Deseja seguir com a decolagem? (s/n): ").strip().lower()
    if resposta == "s":
        print("Decolagem mantida pelo capitão {}.".format(nome_capitao))
    else:
        decolagem_autorizada = False   # O CAPITÃO TAMBÉM PODE DESLIGAR A CHAVE
        print("Decolagem vetada pelo capitão {}.".format(nome_capitao))

# VEREDITO FINAL (vale para os três cenários, sem depender de "resposta")
if decolagem_autorizada:
    print("VEREDITO FINAL: PRONTO PARA DECOLAR")
    print("Missão em andamento.")
else:
    print("VEREDITO FINAL: DECOLAGEM ABORTADA")
    print("Missão abortada.")



# =====================================================================
# ETAPA 6 - REGISTRO DO CENARIO (coleta de dados para o relatorio)
# =====================================================================
# CADA EXECUCAO GRAVA DOIS ARQUIVOS NA PASTA "cenarios":
#   1. registro_execucoes.csv -> UMA LINHA POR EXECUCAO (TABELA COMPARATIVA)
#   2. cenario_XX_CLASSE.txt  -> O RELATORIO COMPLETO DAQUELA EXECUCAO
os.makedirs(PASTA_CENARIOS, exist_ok=True)   # CRIA A PASTA SE ELA AINDA NAO EXISTIR
arquivo_csv = os.path.join(PASTA_CENARIOS, "registro_execucoes.csv")

# DESCOBRE O NUMERO DESTA EXECUCAO CONTANDO AS LINHAS JA GRAVADAS.
# O CABECALHO OCUPA A LINHA 1, ENTAO O TOTAL DE LINHAS JA E O PROXIMO NUMERO.
numero_execucao = 1
if os.path.exists(arquivo_csv):
    arquivo = open(arquivo_csv, "r", encoding="utf-8-sig")
    numero_execucao = len(arquivo.readlines())
    arquivo.close()

# CONVERTE O VEREDITO PARA TEXTO LEGIVEL NA PLANILHA (modulos_texto JA EXISTE, DA ETAPA 1)
if decolagem_autorizada:
    decolagem_texto = "AUTORIZADA"
else:
    decolagem_texto = "ABORTADA"

# --- ARQUIVO 1: A PLANILHA ACUMULATIVA ---
cabecalho = ["execucao", "data_hora", "classificacao", "temp_interna", "temp_externa",
             "integridade", "pressao_psi", "energia_pct", "modulos_online",
             "capacidade_kwh", "disponivel_kwh", "perdida_kwh", "util_kwh", "consumo_kwh",
             "restante_kwh", "autonomia_pct", "qtd_criticos", "qtd_alertas", "decolagem"]

linha = [numero_execucao,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         classificacao,
         temp_interna, temp_externa, integridade, pressao_tanques, energia,
         modulos_texto, CAPACIDADE_TOTAL,
         round(energia_disponivel, 1), round(energia_perdida, 1), round(energia_util, 1),
         CONSUMO_DECOLAGEM, round(energia_restante, 1), round(autonomia_restante, 1),
         len(criticos), len(alertas), decolagem_texto]

csv_ja_existe = os.path.exists(arquivo_csv)
# newline="" EVITA LINHAS EM BRANCO NO WINDOWS; utf-8-sig FAZ O EXCEL LER OS ACENTOS
arquivo = open(arquivo_csv, "a", newline="", encoding="utf-8-sig")
escritor = csv.writer(arquivo, delimiter=";")   # ";" E O SEPARADOR DO EXCEL EM PORTUGUES
if not csv_ja_existe:
    escritor.writerow(cabecalho)
escritor.writerow(linha)
arquivo.close()

# --- ARQUIVO 2: O RELATORIO DETALHADO DESTA EXECUCAO ---
nome_txt = "cenario_{:02d}_{}.txt".format(numero_execucao, classificacao)
arquivo_txt = os.path.join(PASTA_CENARIOS, nome_txt)

relatorio_cenario = []
relatorio_cenario.append("=" * 62)
relatorio_cenario.append("PROJETO AURORA - REGISTRO DE EXECUCAO Nº {:02d}".format(numero_execucao))
relatorio_cenario.append("Data/hora    : " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
relatorio_cenario.append("Capitao      : " + nome_capitao)
relatorio_cenario.append("Classificacao: " + classificacao)
relatorio_cenario.append("=" * 62)
relatorio_cenario.append("")
relatorio_cenario.append("TELEMETRIA E DIAGNOSTICO AUTOMATICO")
relatorio_cenario.append("  Temperatura interna : {:.1f} C".format(temp_interna))
relatorio_cenario.append("  Temperatura externa : {:.1f} C".format(temp_externa))
relatorio_cenario.append("  Integridade calculada: {}".format(integridade_texto))
relatorio_cenario.append("  Diagnostico         : {}".format(diagnostico_integridade))
relatorio_cenario.append("  Pressao dos tanques : {:.1f} psi".format(pressao_tanques))
relatorio_cenario.append("  Energia             : {:.1f} %".format(energia))
relatorio_cenario.append("  Modulos online      : " + modulos_texto)
relatorio_cenario.append("  Capacidade bateria  : {:.1f} kWh".format(CAPACIDADE_TOTAL))
relatorio_cenario.append("")
relatorio_cenario.append("ANALISE ENERGETICA")
relatorio_cenario.append("  Energia disponivel       : {:.1f} kWh".format(energia_disponivel))
relatorio_cenario.append("  Energia perdida ({:.0f}%)     : {:.1f} kWh".format(PERDAS * 100, energia_perdida))
relatorio_cenario.append("  Energia util             : {:.1f} kWh".format(energia_util))
relatorio_cenario.append("  Consumo na decolagem     : {:.1f} kWh".format(CONSUMO_DECOLAGEM))
relatorio_cenario.append("  Energia apos a decolagem : {:.1f} kWh ({:.1f}%)".format(energia_restante, autonomia_restante))
relatorio_cenario.append("")
relatorio_cenario.append("VERIFICACOES DE SEGURANCA")
if erros_seguranca:
    for item in erros_seguranca:
        relatorio_cenario.append("  [X] " + item)
else:
    relatorio_cenario.append("  Todas as verificacoes aprovadas.")
relatorio_cenario.append("")
relatorio_cenario.append("ANALISE ASSISTIDA POR IA")

if criticos:
    relatorio_cenario.append("  Discrepancias criticas:")
    for item in criticos:
        relatorio_cenario.append("    [X] " + item)

if alertas:
    relatorio_cenario.append("  Alertas:")
    for item in alertas:
        relatorio_cenario.append("    [!] " + item)

if not criticos and not alertas:
    relatorio_cenario.append("  Nenhuma discrepancia encontrada.")

if classificacao == "MEDIO":
    relatorio_cenario.append("")
    relatorio_cenario.append("DECISAO DO CAPITAO")
    if decolagem_autorizada:
        relatorio_cenario.append("  Decolagem autorizada pelo capitao (resposta s).")
    else:
        relatorio_cenario.append("  Decolagem vetada pelo capitao (resposta diferente de s).")

relatorio_cenario.append("")
if decolagem_autorizada:
    relatorio_cenario.append("VEREDITO FINAL: PRONTO PARA DECOLAR")
else:
    relatorio_cenario.append("VEREDITO FINAL: DECOLAGEM ABORTADA")
relatorio_cenario.append("=" * 62)

arquivo = open(arquivo_txt, "w", encoding="utf-8")
arquivo.write("\n".join(relatorio_cenario))   # JUNTA A LISTA EM UM TEXTO, UMA LINHA POR ITEM
arquivo.close()

print("")
print("Cenario registrado como {} (classificacao: {})".format(nome_txt, classificacao))
print("Planilha acumulada em: cenarios/registro_execucoes.csv")


# =====================================================================
# ETAPA 7 - SIMULACAO DA MISSAO TERRA -> MARTE
# =====================================================================
# SO ACONTECE SE A DECOLAGEM FOI AUTORIZADA. A IA DEIXA DE SER UM VALIDADOR
# DE UM UNICO INPUT E PASSA A SER UM MONITOR DE MISSAO: A CADA "HORA" ELA
# CALCULA O SALDO DE ENERGIA, DECIDE O ESTADO DA NAVE (VERDE / AMARELO /
# VERMELHO), LIGA OU DESLIGA SISTEMAS POR PRIORIDADE E VIGIA A MARGEM DE
# RETORNO A TERRA.
#
# TUDO O QUE ACONTECE VAI PARA A LISTA "relatorio" (A "CAIXA PRETA" QUE
# VIRA O TXT). NA TELA APARECE O MESMO TEXTO, EXCETO AS LINHAS DE
# TELEMETRIA QUE A IA DECIDE ESCONDER PARA REDUZIR A FREQUENCIA.
if not decolagem_autorizada:
    print("")
    print("MISSAO CANCELADA: a verificacao de decolagem nao autorizou o lancamento.")

else:
    # --- 7.1 A IA ESCOLHE A ROTA PELA BATERIA ---
    # A carga informada antes da decolagem continua sendo usada no planejamento da rota.
    # A simulacao, porem, comeca EXATAMENTE com a energia que restou no item 1.4.
    energia_inicial = energia
    energia_apos_decolagem = max(autonomia_restante, 0.0)
    energia = energia_apos_decolagem
    if energia_inicial >= LIMIAR_ROTA_RAPIDA:
        rota = "RAPIDA"
        texto = "[IA] Carga pre-decolagem em {:.1f}% (>= {:.0f}%): escolhendo a {}.".format(energia_inicial, LIMIAR_ROTA_RAPIDA, ROTAS[rota]["nome"])
    else:
        rota = "ECONOMICA"
        texto = "[IA] Carga pre-decolagem em {:.1f}% (< {:.0f}%): escolhendo a {}.".format(energia_inicial, LIMIAR_ROTA_RAPIDA, ROTAS[rota]["nome"])

    # A ROTA USA A CARGA PRE-DECOLAGEM COMO CRITERIO DE PLANEJAMENTO.
    # A ENERGIA DA SIMULACAO, POR SUA VEZ, VEM DIRETAMENTE DO SALDO DO ITEM 1.4.
    if MOSTRAR_VOO_NA_TELA:
        print("")
        print("=" * 78)
        print("PROJETO AURORA - SIMULACAO DE MISSAO")
        print("=" * 78)
        print(texto)
        print("[ENERGIA] Carga pre-decolagem: {:.1f}%.".format(energia_inicial))
        print("[ENERGIA] Inicio da missao: {:.1f}% apos 8% de perdas e 300 kWh da decolagem.".format(energia_apos_decolagem))
        print("")

    # --- 7.2 O ROTEIRO: A LISTA DE FASES ("CHECKPOINTS") DA MISSAO ---
    horas_cruzeiro = ROTAS[rota]["horas_cruzeiro"]
    quantidade_manobras = ROTAS[rota]["manobras"]

    # ESPALHA AS MANOBRAS POR IGUAL AO LONGO DO CRUZEIRO.
    # ex: 100 h e 2 manobras -> intervalo 33 -> manobras nas horas 33 e 66.
    intervalo = horas_cruzeiro // (quantidade_manobras + 1)
    horas_de_manobra = []
    for numero in range(1, quantidade_manobras + 1):
        horas_de_manobra.append(intervalo * numero)

    roteiro = [
        {"local": "Atmosfera",       "nome": "Saida da atmosfera e orbita terrestre",
         "horas": HORAS_ATMOSFERA,    "paineis": "fechado",   "manobras": []},
        {"local": "Espaco Profundo", "nome": "Cruzeiro interplanetario",
         "horas": horas_cruzeiro,     "paineis": "total",     "manobras": horas_de_manobra},
        {"local": "Orbita de Marte", "nome": "Aproximacao e captura orbital",
         "horas": HORAS_ORBITA_MARTE, "paineis": "alternado", "manobras": []},
        {"local": "Superficie",      "nome": "Pouso e exploracao",
         "horas": HORAS_SUPERFICIE,   "paineis": "total",     "manobras": []},
    ]
    horas_retorno = horas_cruzeiro   # VOLTAR = UM CRUZEIRO INTEIRO NO SENTIDO CONTRARIO

    # --- 7.3 O ESTADO DA NAVE, QUE MUDA A CADA HORA ---
    relatorio = []
    hora_missao = 0
    estado = "VERDE"
    clima = "normal"
    alerta_margem = False        # A IA JA PERCEBEU QUE A VOLTA ESTA AMEACADA?
    em_risco = False             # A MISSAO ESTA EM RISCO NESTE MOMENTO?
    avisos_risco = 0             # QUANTAS VEZES A IA DECLAROU "MISSAO EM RISCO"
    horas_por_estado = {"VERDE": 0, "AMARELO": 0, "VERMELHO": 0}
    bateria_minima = energia
    hora_da_minima = 0
    energia_ao_abrir_paineis = None   # None = OS PAINEIS AINDA NAO ABRIRAM
    horas_com_paineis = 0
    manobras_pendentes = 0       # MANOBRAS QUE CHEGARAM NA HORA MAS A IA ADIOU POR TEMPESTADE
    falhou = False

    # --- 7.4 CABECALHO DO RELATORIO (A CAIXA PRETA) ---
    # NA TELA, ESTES DADOS APARECEM NO RESUMO FINAL, TUDO JUNTO. AQUI ELES
    # ABREM O ARQUIVO TXT, E SO SAO MOSTRADOS AGORA NO MODO DETALHADO.
    texto = "=" * 78
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    texto = "PROJETO AURORA - SIMULACAO DE MISSAO TERRA -> MARTE"
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    texto = "=" * 78
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    texto = "Capitao                  : {}".format(nome_capitao)
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    texto = "Verificacao de decolagem : {} (pre {:.1f}% -> pos {:.1f}%)".format(classificacao, energia_inicial, energia_apos_decolagem)
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    texto = "Rota escolhida pela IA   : {} ({} h de cruzeiro, {} manobra(s))".format(
        ROTAS[rota]["nome"], horas_cruzeiro, quantidade_manobras)
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    texto = "Reserva critica de volta : {:.0f}% da bateria".format(RESERVA_CRITICA)
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    relatorio.append("")
    if MOSTRAR_VOO_NA_TELA: print("")
    texto = "SISTEMAS DA NAVE (consumo em % por hora)"
    relatorio.append(texto)
    if MOSTRAR_VOO_NA_TELA: print(texto)
    for sistema in SISTEMAS:
        texto = "  P{}  {:<22} {:.1f}%/h".format(sistema["prioridade"], sistema["nome"], sistema["consumo"])
        relatorio.append(texto)
        if MOSTRAR_VOO_NA_TELA: print(texto)

    cabecalho_tabela = "{:>4} | {:<15} | {:<8} | {:<8} | {:>5} | {:>5} | {:>5} | {:>7} | {:>6}".format(
        "HORA", "FASE", "PAINEIS", "ESTADO", "CONS", "RECAR", "SALDO", "BATERIA", "MARGEM")

    # --- 7.5 UMA FASE DE CADA VEZ ---
    for fase in roteiro:
        local = fase["local"]
        relatorio.append("")
        if MOSTRAR_VOO_NA_TELA: print("")
        texto = "-" * 78
        relatorio.append(texto)
        if MOSTRAR_VOO_NA_TELA: print(texto)
        texto = "FASE: {} ({} h)".format(fase["nome"], fase["horas"])
        relatorio.append(texto)
        if MOSTRAR_VOO_NA_TELA: print(texto)
        texto = "-" * 78
        relatorio.append(texto)
        if MOSTRAR_VOO_NA_TELA: print(texto)

        # ---- CHECKPOINT: O QUE A IA FAZ AO ENTRAR NA FASE ----
        if local == "Atmosfera":
            texto = "[IA] Decolagem. Monitorando a estabilidade da subida. Paineis fechados (atrito da atmosfera)."
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            # O CONSUMO DA DECOLAGEM JA FOI CONTABILIZADO NO ITEM 1.4.
            # AQUI NAO EXISTE UM SEGUNDO DESCONTO: A MISSAO HERDA O SALDO CALCULADO.
            texto = "[EVENTO] Decolagem ja contabilizada no item 1.4: bateria operacional em {:.1f}%.".format(energia)
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)

        elif local == "Espaco Profundo":
            texto = "[IA] Saindo da atmosfera. Autorizando abertura dos paineis solares. Recarga ativa."
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            texto = "[IA] Plano de voo: {} manobra(s) de correcao nas horas {} do cruzeiro.".format(
                len(fase["manobras"]), fase["manobras"])
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            energia_ao_abrir_paineis = energia
            horas_com_paineis = 0

        elif local == "Orbita de Marte":
            texto = "[IA] Iniciando manobra de frenagem para captura orbital."
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            if energia - CUSTO_FRENAGEM < RESERVA_CRITICA:
                texto = "[IA] AVISO: apos a frenagem a bateria fica abaixo da reserva de retorno ({:.0f}%). MISSAO EM RISCO.".format(RESERVA_CRITICA)
                relatorio.append(texto)
                if MOSTRAR_VOO_NA_TELA: print(texto)
                avisos_risco = avisos_risco + 1
            energia = max(energia - CUSTO_FRENAGEM, 0.0)
            texto = "[EVENTO] {}: -{:.1f}%  -> bateria em {:.1f}%".format("Frenagem orbital", CUSTO_FRENAGEM, energia)
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            texto = "[IA] Em orbita. A nave passa por tras de Marte hora sim, hora nao: eclipse corta a recarga."
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)

        elif local == "Superficie":
            texto = "[IA] Iniciando descida com retropropulsao."
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            if energia - CUSTO_POUSO < RESERVA_CRITICA:
                texto = "[IA] AVISO: apos o pouso a bateria fica abaixo da reserva de retorno ({:.0f}%). MISSAO EM RISCO.".format(RESERVA_CRITICA)
                relatorio.append(texto)
                if MOSTRAR_VOO_NA_TELA: print(texto)
                avisos_risco = avisos_risco + 1
            energia = max(energia - CUSTO_POUSO, 0.0)
            texto = "[EVENTO] {}: -{:.1f}%  -> bateria em {:.1f}%".format("Pouso / retropropulsao", CUSTO_POUSO, energia)
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            texto = "[IA] Pouso concluido. Monitorando acumulo de poeira nos paineis."
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)

        relatorio.append(cabecalho_tabela)
        if MOSTRAR_VOO_NA_TELA: print(cabecalho_tabela)

        # ---- O LOOP DE HORAS DESTA FASE ----
        for hora_na_fase in range(1, fase["horas"] + 1):
            hora_missao = hora_missao + 1
            houve_evento = False   # SE ALGO ACONTECEU, A LINHA DESTA HORA APARECE NA TELA

            # 1) CLIMA: COMECOU OU TERMINOU UMA TEMPESTADE?
            #    OS RISCOS SAO PROGRAMADOS (NAO ALEATORIOS) PARA A MESMA ENTRADA DAR SEMPRE O MESMO RESULTADO.
            clima_novo = "normal"
            if local == "Espaco Profundo":
                inicio = TEMPESTADE_SOLAR["inicio"]
                fim = inicio + TEMPESTADE_SOLAR["duracao"]
                if inicio <= hora_na_fase < fim:
                    clima_novo = "tempestade_solar"
            if local == "Superficie":
                inicio = TEMPESTADE_POEIRA["inicio"]
                fim = inicio + TEMPESTADE_POEIRA["duracao"]
                if inicio <= hora_na_fase < fim:
                    clima_novo = "tempestade_poeira"

            if clima_novo != clima:
                if clima_novo == "tempestade_solar":
                    texto = "[IA] Tempestade solar detectada! Recolhendo os paineis e entrando em MODO DE PROTECAO."
                elif clima_novo == "tempestade_poeira":
                    texto = "[IA] Tempestade de poeira! Recarga solar caindo. Desligando tudo que nao e essencial para sobreviver."
                else:
                    texto = "[IA] Condicoes normalizadas. Retomando a operacao."
                relatorio.append(texto)
                if MOSTRAR_VOO_NA_TELA: print(texto)
                clima = clima_novo
                houve_evento = True

            # 2) MANOBRA PROGRAMADA NESTA HORA?
            #    A MANOBRA ENTRA NA FILA DE PENDENTES. SE O CLIMA ESTA NORMAL, E EXECUTADA
            #    NA MESMA HORA. SE HA TEMPESTADE (PAINEIS RECOLHIDOS, MODO DE PROTECAO), A IA
            #    ADIA: A MANOBRA FICA NA FILA E SAI NA PRIMEIRA HORA COM CLIMA NORMAL, UMA
            #    POR HORA, PARA NAO SOMAR DOIS GASTOS PONTUAIS NA MESMA LINHA DE TELEMETRIA.
            if hora_na_fase in fase["manobras"]:
                manobras_pendentes = manobras_pendentes + 1
                if clima != "normal":
                    texto = "[IA] Manobra programada para a hora {} ADIADA: tempestade em curso. Sera executada quando o clima normalizar.".format(hora_na_fase)
                    relatorio.append(texto)
                    if MOSTRAR_VOO_NA_TELA: print(texto)
                    houve_evento = True

            if manobras_pendentes > 0 and clima == "normal":
                manobras_pendentes = manobras_pendentes - 1
                if hora_na_fase in fase["manobras"]:
                    nome_manobra = "Manobra de correcao de rota"
                else:
                    nome_manobra = "Manobra de correcao de rota (adiada)"
                energia = max(energia - CUSTO_MANOBRA, 0.0)
                texto = "[EVENTO] {}: -{:.1f}%  -> bateria em {:.1f}%".format(nome_manobra, CUSTO_MANOBRA, energia)
                relatorio.append(texto)
                if MOSTRAR_VOO_NA_TELA: print(texto)
                houve_evento = True

            # 3) MARGEM DE RETORNO
            #    Margem = Energia Atual - (Consumo Medio x Tempo de Retorno)
            #    CONSUMO MEDIO = QUANTO A BATERIA CAIU POR HORA DESDE QUE OS PAINEIS ABRIRAM
            #    (JA DESCONTANDO A RECARGA). TEMPO DE RETORNO = UM CRUZEIRO INTEIRO DE VOLTA.
            if energia_ao_abrir_paineis is None:
                gasto_liquido = 0.0
            else:
                gasto_liquido = energia_ao_abrir_paineis - energia

            if horas_com_paineis == 0:
                consumo_medio = 0.0
            else:
                consumo_medio = max(gasto_liquido, 0.0) / horas_com_paineis
            custo_retorno = consumo_medio * horas_retorno
            margem = energia - custo_retorno

            if energia_ao_abrir_paineis is not None:
                if not alerta_margem and margem < RESERVA_CRITICA:
                    alerta_margem = True
                    houve_evento = True
                    texto = "[IA] Margem de retorno ameacada: no ritmo atual a volta custaria {:.1f}%, sobrariam {:.1f}% (minimo {:.0f}%). Iniciando desligamento escalonado.".format(
                        custo_retorno, margem, RESERVA_CRITICA)
                    relatorio.append(texto)
                    if MOSTRAR_VOO_NA_TELA: print(texto)
                elif alerta_margem and margem >= RESERVA_CRITICA + FOLGA_MARGEM:
                    alerta_margem = False
                    houve_evento = True
                    texto = "[IA] Margem de retorno recuperada ({:.1f}%). Liberando sistemas.".format(margem)
                    relatorio.append(texto)
                    if MOSTRAR_VOO_NA_TELA: print(texto)

            # 4) ESTADO DA NAVE
            if clima != "normal":
                estado_novo = "VERMELHO"   # MODO DE PROTECAO (tempestade solar) OU SOBREVIVENCIA (poeira)
            else:
                if energia >= LIMIAR_VERDE:
                    estado_novo = "VERDE"
                elif energia >= LIMIAR_AMARELO:
                    estado_novo = "AMARELO"
                else:
                    estado_novo = "VERMELHO"

                # SE A MARGEM DE RETORNO ESTA AMEACADA, DESCE UM DEGRAU
                # (VERDE -> AMARELO -> VERMELHO; VERMELHO FICA VERMELHO).
                if alerta_margem:
                    if estado_novo == "VERDE":
                        estado_novo = "AMARELO"
                    else:
                        estado_novo = "VERMELHO"

            if estado_novo != estado:
                texto = "[IA] Estado {} -> {}: {}.".format(estado, estado_novo, DESCRICAO_ESTADO[estado_novo])
                relatorio.append(texto)
                if MOSTRAR_VOO_NA_TELA: print(texto)
                estado = estado_novo
                houve_evento = True

            if estado == "VERMELHO" and alerta_margem and not em_risco:
                em_risco = True
                avisos_risco = avisos_risco + 1
                houve_evento = True
                texto = "[IA] *** MISSAO EM RISCO: mesmo so com o essencial, a reserva de retorno nao esta garantida. ***"
                relatorio.append(texto)
                if MOSTRAR_VOO_NA_TELA: print(texto)
            if em_risco and (estado != "VERMELHO" or not alerta_margem):
                em_risco = False

            # 5) QUAIS SISTEMAS FICAM LIGADOS NESTE ESTADO, E QUANTO CONSOMEM
            #      VERDE    -> tudo ligado
            #      AMARELO  -> prioridade 3 desligada, comunicacao em modo economico
            #      VERMELHO -> so prioridade 1 (o essencial)
            consumo = 0.0
            ligados = []
            for sistema in SISTEMAS:
                prioridade = sistema["prioridade"]
                if estado == "VERDE":
                    ligado = True
                elif estado == "AMARELO":
                    ligado = prioridade <= 2
                else:
                    ligado = prioridade == 1

                if not ligado:
                    continue   # PULA PARA O PROXIMO SISTEMA DA LISTA

                consumo_sistema = sistema["consumo"]
                if estado == "AMARELO" and "economico" in sistema:
                    consumo_sistema = sistema["economico"]
                consumo = consumo + consumo_sistema
                ligados.append(sistema["nome"])

            # 6) QUANTO SOL CHEGA NOS PAINEIS NESTA HORA
            if fase["paineis"] == "fechado":
                exposicao = "fechado"
            elif clima == "tempestade_solar":
                exposicao = "fechado"      # A IA RECOLHEU OS PAINEIS PARA PROTEGER OS CIRCUITOS
            elif clima == "tempestade_poeira":
                exposicao = "parcial"      # POEIRA COBRINDO OS PAINEIS
            elif fase["paineis"] == "alternado":
                if hora_na_fase % 2 == 0:
                    exposicao = "eclipse"  # HORAS PARES: A NAVE PASSA POR TRAS DE MARTE
                else:
                    exposicao = "total"
            else:
                exposicao = fase["paineis"]

            # 7) O BALANCO DA HORA: Saldo = Recarga - Soma dos Sistemas Ativos
            recarga = RECARGA[exposicao]
            saldo = recarga - consumo
            energia = energia + saldo
            energia = min(max(energia, 0.0), 100.0)   # A BATERIA FICA ENTRE 0 E 100

            # 8) ESTATISTICAS PARA O RESUMO
            horas_por_estado[estado] = horas_por_estado[estado] + 1
            if energia_ao_abrir_paineis is not None:
                horas_com_paineis = horas_com_paineis + 1
            if energia < bateria_minima:
                bateria_minima = energia
                hora_da_minima = hora_missao

            # 9) A LINHA DE TELEMETRIA DESTA HORA. VAI SEMPRE PARA O RELATORIO; NA TELA
            #    SO APARECE SE HOUVE EVENTO OU SE E A HORA DE MOSTRAR (FREQUENCIA DO ESTADO).
            linha_telemetria = "{:>4} | {:<15} | {:<8} | {:<8} | {:>5.2f} | {:>5.2f} | {:>+5.2f} | {:>6.1f}% | {:>6.1f}".format(
                hora_missao, local, exposicao, estado, consumo, recarga, saldo, energia, margem)
            relatorio.append(linha_telemetria)
            if houve_evento or hora_na_fase % FREQUENCIA_TELEMETRIA[estado] == 0:
                if MOSTRAR_VOO_NA_TELA: print(linha_telemetria)

            if energia <= 0:
                texto = "[FALHA] Bateria esgotada na hora {}. A nave perdeu o suporte a vida.".format(hora_missao)
                relatorio.append(texto)
                if MOSTRAR_VOO_NA_TELA: print(texto)
                falhou = True
                break   # SAI DO LOOP DE HORAS

        if falhou:
            break       # SAI DO LOOP DE FASES

    # --- 7.6 STATUS FINAL E RESUMO ---
    if falhou:
        status = "FALHA"
    elif avisos_risco > 0 or energia < RESERVA_CRITICA:
        status = "CONCLUIDA COM RISCO"
    else:
        status = "SUCESSO"

    relatorio.append(""); print("")
    texto = "=" * 78
    relatorio.append(texto); print(texto)
    texto = "RESUMO DA MISSAO TERRA -> MARTE"
    relatorio.append(texto); print(texto)
    texto = "=" * 78
    relatorio.append(texto); print(texto)
    texto = "Capitao                  : {}".format(nome_capitao)
    relatorio.append(texto); print(texto)
    texto = "Verificacao de decolagem : {} (pre {:.1f}% -> pos {:.1f}%)".format(classificacao, energia_inicial, energia_apos_decolagem)
    relatorio.append(texto); print(texto)
    texto = "Rota escolhida pela IA   : {} ({} h de cruzeiro, {} manobra(s))".format(
        ROTAS[rota]["nome"], horas_cruzeiro, quantidade_manobras)
    relatorio.append(texto); print(texto)
    texto = "Reserva critica de volta : {:.0f}% da bateria".format(RESERVA_CRITICA)
    relatorio.append(texto); print(texto)
    texto = "Horas simuladas          : {}".format(hora_missao)
    relatorio.append(texto); print(texto)
    texto = "Bateria                  : inicial {:.1f}% | apos decolagem {:.1f}% | final {:.1f}%".format(
        energia_inicial, energia_apos_decolagem, energia)
    relatorio.append(texto); print(texto)
    texto = "Bateria minima           : {:.1f}% (hora {})".format(bateria_minima, hora_da_minima)
    relatorio.append(texto); print(texto)
    texto = "Horas por estado         : VERDE {} | AMARELO {} | VERMELHO {}".format(
        horas_por_estado["VERDE"], horas_por_estado["AMARELO"], horas_por_estado["VERMELHO"])
    relatorio.append(texto); print(texto)
    texto = "Avisos de risco          : {}".format(avisos_risco)
    relatorio.append(texto); print(texto)
    texto = "STATUS                   : {}".format(status)
    relatorio.append(texto); print(texto)
    texto = "=" * 78
    relatorio.append(texto); print(texto)

    # =================================================================
    # ETAPA 8 - REGISTRO DA MISSAO (MESMO PADRAO DA ETAPA 6)
    # =================================================================
    os.makedirs(PASTA_MISSOES, exist_ok=True)
    arquivo_csv = os.path.join(PASTA_MISSOES, "registro_missoes.csv")

    numero_missao = 1
    if os.path.exists(arquivo_csv):
        arquivo = open(arquivo_csv, "r", encoding="utf-8-sig")
        numero_missao = len(arquivo.readlines())
        arquivo.close()

    cabecalho = ["missao", "data_hora", "status", "energia_inicial_pct", "energia_pos_decolagem_pct", "rota", "horas",
                 "bateria_final_pct", "bateria_minima_pct",
                 "horas_verde", "horas_amarelo", "horas_vermelho", "avisos_risco"]
    linha = [numero_missao,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             status, energia_inicial, round(energia_apos_decolagem, 1), ROTAS[rota]["nome"], hora_missao,
             round(energia, 1), round(bateria_minima, 1),
             horas_por_estado["VERDE"], horas_por_estado["AMARELO"], horas_por_estado["VERMELHO"],
             avisos_risco]

    csv_ja_existe = os.path.exists(arquivo_csv)
    arquivo = open(arquivo_csv, "a", newline="", encoding="utf-8-sig")
    escritor = csv.writer(arquivo, delimiter=";")
    if not csv_ja_existe:
        escritor.writerow(cabecalho)
    escritor.writerow(linha)
    arquivo.close()

    # NO NOME DO ARQUIVO O STATUS VIRA UMA PALAVRA SO: SUCESSO, RISCO OU FALHA.
    if status == "CONCLUIDA COM RISCO":
        rotulo = "RISCO"
    else:
        rotulo = status
    nome_txt = "missao_{:02d}_{}.txt".format(numero_missao, rotulo)
    arquivo_txt = os.path.join(PASTA_MISSOES, nome_txt)

    conteudo = ["Missao Nº {:02d}  |  {}".format(numero_missao, datetime.now().strftime("%d/%m/%Y %H:%M:%S")), ""]
    arquivo = open(arquivo_txt, "w", encoding="utf-8")
    arquivo.write("\n".join(conteudo + relatorio))
    arquivo.close()

    print("")
    print("Missao registrada como {} (status: {})".format(nome_txt, status))
    print("Planilha acumulada em: missoes/registro_missoes.csv")
