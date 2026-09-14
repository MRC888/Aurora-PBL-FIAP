from pathlib import Path

path = Path('README.md')
text = path.read_text(encoding='utf-8')

start = text.index('## Prints da execução')
end = text.index('\n---\n\n## Cenários coletados', start)

replacement = '''## Prints da execução

Abaixo estão duas execuções reais do `scripts/main.py`, cobrindo dois resultados distintos do sistema: um cenário **MÉDIO**, em que existem alertas e a decisão final passa pelo capitão, e um cenário **ÓTIMO**, em que nenhuma discrepância é encontrada.

### Cenário 02 — MÉDIO | decolagem autorizada com ressalvas

Entrada principal: temperatura interna `25 °C`, externa `30 °C`, integridade `1`, pressão `550 psi`, energia `80%` e módulos online. O sistema identifica dois alertas de margem, classifica o cenário como **MÉDIO** e transfere a decisão ao capitão, que autoriza a decolagem.

![Execução real do cenário 02 - MÉDIO](docs/terminal_cenario_02_MEDIO.webp)

### Cenário 09 — ÓTIMO | decolagem autorizada

Entrada principal: temperatura interna `20 °C`, externa `5 °C`, integridade `1`, pressão `470 psi`, energia `98%` e módulos online. Todas as verificações são aprovadas, a análise assistida não encontra discrepâncias e o cenário é classificado como **ÓTIMO**.

![Execução real do cenário 09 - ÓTIMO](docs/terminal_cenario_09_OTIMO.webp)
'''

path.write_text(text[:start] + replacement + text[end:], encoding='utf-8')
