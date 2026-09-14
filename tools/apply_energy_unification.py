#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "scripts" / "main.py"
README = ROOT / "README.md"
NOTEBOOK = ROOT / "notebook" / "aurora_pbl.ipynb"
MISSIONS = ROOT / "missoes"


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 trecho, encontrado {count}")
    return text.replace(old, new, 1)


def replace_count(text, old, new, expected, label):
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: esperado {expected}, encontrado {count}")
    return text.replace(old, new)


def patch_main():
    text = MAIN.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '# --- MISSAO: CUSTOS PONTUAIS EM % DA BATERIA (upgrade.md 4.1) ---\nCUSTO_DECOLAGEM = 20.0   # sair da gravidade da Terra\nCUSTO_MANOBRA = 5.0      # cada ajuste de rota durante o cruzeiro',
        '# --- MISSAO: CUSTOS PONTUAIS APOS A DECOLAGEM, EM % DA BATERIA ---\n# A decolagem NAO e descontada novamente aqui: o item 1.4 ja aplicou as perdas\n# e subtraiu CONSUMO_DECOLAGEM em kWh. A missao parte de autonomia_restante.\nCUSTO_MANOBRA = 5.0      # cada ajuste de rota durante o cruzeiro',
        'remover segundo custo de decolagem',
    )

    text = replace_once(
        text,
        '    energia_inicial = energia\n    if energia_inicial >= LIMIAR_ROTA_RAPIDA:',
        '    # A carga informada antes da decolagem continua sendo usada no planejamento da rota.\n    # A simulacao, porem, comeca EXATAMENTE com a energia que restou no item 1.4.\n    energia_inicial = energia\n    energia_apos_decolagem = max(autonomia_restante, 0.0)\n    energia = energia_apos_decolagem\n    if energia_inicial >= LIMIAR_ROTA_RAPIDA:',
        'iniciar missao com autonomia_restante',
    )

    text = replace_count(
        text,
        'texto = "[IA] Bateria em {:.1f}% (>= {:.0f}%): escolhendo a {}.".format(energia_inicial, LIMIAR_ROTA_RAPIDA, ROTAS[rota]["nome"])',
        'texto = "[IA] Carga pre-decolagem em {:.1f}% (>= {:.0f}%): escolhendo a {}.".format(energia_inicial, LIMIAR_ROTA_RAPIDA, ROTAS[rota]["nome"])',
        1,
        'mensagem rota rapida',
    )
    text = replace_count(
        text,
        'texto = "[IA] Bateria em {:.1f}% (< {:.0f}%): escolhendo a {}.".format(energia_inicial, LIMIAR_ROTA_RAPIDA, ROTAS[rota]["nome"])',
        'texto = "[IA] Carga pre-decolagem em {:.1f}% (< {:.0f}%): escolhendo a {}.".format(energia_inicial, LIMIAR_ROTA_RAPIDA, ROTAS[rota]["nome"])',
        1,
        'mensagem rota economica',
    )

    old_note = '''    # A DECISAO DA ROTA E A NOTA SOBRE OS DOIS MODELOS DE DECOLAGEM SO APARECEM
    # NO MODO DETALHADO; O RESUMO FINAL JA DIZ QUAL ROTA FOI ESCOLHIDA.
    if MOSTRAR_VOO_NA_TELA:
        print("")
        print("=" * 78)
        print("PROJETO AURORA - SIMULACAO DE MISSAO")
        print("=" * 78)
        print(texto)
        print("[IA] Nota: no modelo de missao a decolagem custa {:.0f}% da bateria (upgrade.md 4.1).".format(CUSTO_DECOLAGEM))
        print("     A verificacao acima usa 300 kWh depois de 8% de perdas (~32.6%). Sao dois modelos; ver upgrade.md, secao 6.")
        print("")
'''
    new_note = '''    # A ROTA USA A CARGA PRE-DECOLAGEM COMO CRITERIO DE PLANEJAMENTO.
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
'''
    text = replace_once(text, old_note, new_note, 'substituir nota dos dois modelos')

    text = replace_once(
        text,
        '    relatorio = []\n    energia_apos_decolagem = energia_inicial\n    hora_missao = 0',
        '    relatorio = []\n    hora_missao = 0',
        'remover reset incorreto da energia',
    )

    text = replace_count(
        text,
        'texto = "Verificacao de decolagem : {} (bateria em {:.1f}%)".format(classificacao, energia_inicial)',
        'texto = "Verificacao de decolagem : {} (pre {:.1f}% -> pos {:.1f}%)".format(classificacao, energia_inicial, energia_apos_decolagem)',
        2,
        'cabecalhos da missao',
    )

    old_atmosfera = '''            # GASTO PONTUAL (upgrade.md 4.1). A BATERIA NUNCA FICA NEGATIVA.
            energia = max(energia - CUSTO_DECOLAGEM, 0.0)
            texto = "[EVENTO] {}: -{:.1f}%  -> bateria em {:.1f}%".format("Decolagem / ignicao", CUSTO_DECOLAGEM, energia)
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
            energia_apos_decolagem = energia
'''
    new_atmosfera = '''            # O CONSUMO DA DECOLAGEM JA FOI CONTABILIZADO NO ITEM 1.4.
            # AQUI NAO EXISTE UM SEGUNDO DESCONTO: A MISSAO HERDA O SALDO CALCULADO.
            texto = "[EVENTO] Decolagem ja contabilizada no item 1.4: bateria operacional em {:.1f}%.".format(energia)
            relatorio.append(texto)
            if MOSTRAR_VOO_NA_TELA: print(texto)
'''
    text = replace_once(text, old_atmosfera, new_atmosfera, 'remover desconto duplicado')

    text = replace_once(
        text,
        '    cabecalho = ["missao", "data_hora", "status", "energia_inicial_pct", "rota", "horas",\n                 "bateria_final_pct", "bateria_minima_pct",',
        '    cabecalho = ["missao", "data_hora", "status", "energia_inicial_pct", "energia_pos_decolagem_pct", "rota", "horas",\n                 "bateria_final_pct", "bateria_minima_pct",',
        'adicionar coluna pos-decolagem',
    )
    text = replace_once(
        text,
        '             status, energia_inicial, ROTAS[rota]["nome"], hora_missao,\n             round(energia, 1), round(bateria_minima, 1),',
        '             status, energia_inicial, round(energia_apos_decolagem, 1), ROTAS[rota]["nome"], hora_missao,\n             round(energia, 1), round(bateria_minima, 1),',
        'gravar energia pos-decolagem',
    )

    MAIN.write_text(text, encoding="utf-8")


def patch_readme():
    text = README.read_text(encoding="utf-8")
    old = '''Não há comando separado: a missão é a continuação do `main.py` quando a
decolagem é autorizada. A IA escolhe a rota pela carga da bateria (90 % ou mais
vai pela rota rápida; abaixo disso, pela econômica) e simula a missão hora a
hora, em quatro fases: saída da atmosfera, cruzeiro interplanetário, captura
orbital em Marte e pouso. Na tela aparece só o **resumo da missão** no fim
(capitão, verificação, rota, horas, bateria, horas em cada estado e status).
'''
    new = '''Não há comando separado: a missão é a continuação do `main.py` quando a
decolagem é autorizada. A IA escolhe a rota pela **carga pré-decolagem** (90 % ou
mais vai pela rota rápida; abaixo disso, pela econômica) e simula a missão hora a
hora, em quatro fases: saída da atmosfera, cruzeiro interplanetário, captura
orbital em Marte e pouso. Na tela aparece só o **resumo da missão** no fim
(capitão, verificação, rota, horas, bateria, horas em cada estado e status).

**Modelo energético unificado.** A simulação não reinicia a bateria e não cobra a
decolagem uma segunda vez. Ela começa exatamente em `autonomia_restante`, valor
calculado no item 1.4 depois das perdas de 8 % e do consumo de 300 kWh. Assim,
por exemplo, uma carga de 100 % deixa 62 % da capacidade para o início da missão,
e esse mesmo saldo segue para a simulação Terra → Marte.
'''
    text = replace_once(text, old, new, 'README modelo unificado')

    text = replace_once(
        text,
        '''Os números do modelo (custos pontuais de 20, 5 e 10 %, consumo dos cinco
sistemas, recarga solar de 0,8 %/h, reserva de 30 % para a volta, duração das
fases e tempestades) são as constantes no topo do `main.py`, cada uma comentada
com a origem ou com a marca `ASSUMIDO` quando a especificação não dava o número.
''',
        '''Os números adicionais da extensão (custos pós-decolagem de manobra,
frenagem e pouso, consumo dos cinco sistemas, recarga solar, reserva de retorno,
duração das fases e tempestades) ficam nas constantes do `main.py`, identificados
como `ASSUMIDO` quando são escolhas didáticas do grupo. O único custo de
decolagem é o do item 1.4: 300 kWh após a aplicação das perdas energéticas.
''',
        'README remover 20%',
    )

    text = replace_once(
        text,
        '''As 7 decolagens autorizadas geraram as 7 missões da pasta `missoes/`, todas
concluídas com risco: o pouso em Marte custa 10 % e deixa a bateria abaixo da
reserva de retorno em todos os casos, porque a recarga solar máxima (0,8 %/h)
apenas empata com o consumo do essencial. É uma consequência dos números do
modelo, registrada como decisão de projeto, e não um defeito do código.
''',
        '''As 7 decolagens autorizadas geraram as 7 missões da pasta `missoes/`.
Os registros foram recalculados com o **mesmo saldo energético do item 1.4**:
a missão começa na energia pós-decolagem já descontadas as perdas e os 300 kWh,
sem aplicar um segundo custo de lançamento. Os resultados atualizados ficam em
`missoes/registro_missoes.csv` e nas respectivas caixas-pretas em TXT.
''',
        'README atualizar missoes',
    )
    README.write_text(text, encoding="utf-8")


def patch_notebook():
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    marker = '## As missões Terra → Marte'
    found = False
    for cell in nb.get('cells', []):
        if cell.get('cell_type') != 'markdown':
            continue
        text = ''.join(cell.get('source', []))
        if marker in text:
            found = True
            if 'Modelo energético unificado' not in text:
                insertion = marker + '\n\n> **Modelo energético unificado:** a missão parte da energia pós-decolagem já calculada no item 1.4 (`autonomia_restante`). As perdas de 8% e o consumo de 300 kWh são descontados uma única vez; não existe um segundo custo de decolagem na simulação.\n'
                text = text.replace(marker, insertion, 1)
                cell['source'] = text.splitlines(keepends=True)
            break
    if not found:
        raise RuntimeError('Notebook: seção de missões não encontrada')
    NOTEBOOK.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def regenerate_missions():
    cases = [
        ('Marcelo', 25, 30, 1, 550, 80, 'S', 's'),
        ('Aline', 25, 30, 1, 480, 100, 'S', None),
        ('Douglas', 23, 20, 1, 495, 92, 'S', None),
        ('Marcelo', 21, -9, 1, 500, 85, 'S', 's'),
        ('Aline', 29, -8, 1, 535, 93, 'S', 's'),
        ('Aline', 20, 5, 1, 470, 98, 'S', None),
        ('Marcelo', 25, 30, 1, 450, 90, 'S', 's'),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'scripts').mkdir(parents=True)
        shutil.copy2(MAIN, root / 'scripts' / 'main.py')
        for name, ti, te, integ, pressure, charge, modules, decision in cases:
            values = [name, ti, te, integ, pressure, charge, modules]
            if decision is not None:
                values.append(decision)
            proc = subprocess.run(
                [sys.executable, str(root / 'scripts' / 'main.py')],
                cwd=root,
                input='\n'.join(map(str, values)) + '\n',
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stdout)
        source = root / 'missoes'
        if MISSIONS.exists():
            shutil.rmtree(MISSIONS)
        shutil.copytree(source, MISSIONS)


def validate():
    subprocess.run([sys.executable, '-m', 'py_compile', str(MAIN)], check=True)
    with (MISSIONS / 'registro_missoes.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f, delimiter=';'))
    assert len(rows) == 7
    assert 'energia_pos_decolagem_pct' in rows[0]
    full = next(r for r in rows if float(r['energia_inicial_pct']) == 100.0)
    assert abs(float(full['energia_pos_decolagem_pct']) - 62.0) <= 0.11
    print('OK: 100% pre-decolagem -> 62.0% no inicio da missao')
    for r in rows:
        print(r['missao'], r['energia_inicial_pct'], r['energia_pos_decolagem_pct'], r['rota'], r['bateria_final_pct'], r['status'])


if __name__ == '__main__':
    patch_main()
    patch_readme()
    patch_notebook()
    regenerate_missions()
    validate()
