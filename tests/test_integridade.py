"""Regressões do fluxo interativo; registros ficam em pastas temporárias."""
import contextlib
import csv
import io
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'main.py'


class IntegridadeAutomaticaTest(unittest.TestCase):
    def executar(self, leituras, resposta='s'):
        respostas = iter(['Teste'] + list(map(str, leituras)) + [resposta])
        prompts = []

        def entrada(prompt):
            prompts.append(prompt)
            return next(respostas)

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / 'scripts').mkdir()
            shutil.copy(SCRIPT, raiz / 'scripts' / 'main.py')
            saida = io.StringIO()
            with patch('builtins.input', entrada), contextlib.redirect_stdout(saida):
                estado = runpy.run_path(str(raiz / 'scripts' / 'main.py'))
            with (raiz / 'cenarios' / 'registro_execucoes.csv').open(encoding='utf-8-sig') as arquivo:
                linha = next(csv.DictReader(arquivo, delimiter=';'))
            registro = next((raiz / 'cenarios').glob('cenario_*.txt')).read_text()
        self.assertFalse(any('integridade' in p.lower() for p in prompts))
        self.assertEqual(int(linha['integridade']), estado['integridade'])
        self.assertIn(estado['diagnostico_integridade'], registro)
        for motivo in estado['erros_seguranca']:
            self.assertIn(motivo, registro)
        if estado['classificacao'] == 'MEDIO':
            decisao = 'autorizada' if estado['decolagem_autorizada'] else 'vetada'
            self.assertIn('Decolagem ' + decisao + ' pelo capitao', registro)
        self.assertIn(estado['diagnostico_integridade'], saida.getvalue())
        return estado, prompts, saida.getvalue()

    def test_cenario_07_agora_tem_integridade_calculada(self):
        e, prompts, _ = self.executar([22, 25, 500, 90, 'S'])
        self.assertEqual(len(prompts), 6)  # nome e cinco leituras
        self.assertEqual(e['integridade'], 1)
        self.assertEqual(e['classificacao'], 'OTIMO')
        self.assertTrue(e['decolagem_autorizada'])

    def test_limites_inclusivos(self):
        for dados in ([15, -10, 450, 95, 'S'], [30, 45, 550, 95, 'S']):
            with self.subTest(dados=dados):
                e, _, _ = self.executar(dados)
                self.assertEqual(e['integridade'], 1)

    def test_falhas_individuais_bloqueiam(self):
        for indice, valor in [(0, 14.9), (0, 30.1), (1, -10.1), (1, 45.1),
                              (2, 449.9), (2, 550.1), (4, 'N')]:
            dados = [23, 20, 495, 92, 'S']
            dados[indice] = valor
            with self.subTest(dados=dados):
                e, prompts, _ = self.executar(dados)
                self.assertEqual(e['integridade'], 0)
                self.assertFalse(e['decolagem_autorizada'])
                self.assertEqual(e['classificacao'], 'HORRIVEL')
                self.assertEqual(len(prompts), 6)  # sem autorização humana em falha

    def test_falhas_acumulam_motivos(self):
        e, _, _ = self.executar([10, 50, 350, 90, 'N'])
        self.assertEqual(len(e['motivos_integridade']), 4)

    def test_energia_tem_avaliacao_propria(self):
        for carga in (55, 105):
            with self.subTest(carga=carga):
                e, _, _ = self.executar([22, 25, 500, carga, 'S'])
                self.assertEqual(e['integridade'], 1)
                self.assertFalse(e['decolagem_autorizada'])

    def test_alerta_preserva_veto_do_capitao(self):
        for resposta, esperado in [('s', True), ('n', False), ('', False)]:
            with self.subTest(resposta=resposta):
                e, prompts, _ = self.executar([20, 30, 480, 80, 'S'], resposta)
                self.assertEqual(e['integridade'], 1)
                self.assertEqual(e['classificacao'], 'MEDIO')
                self.assertEqual(e['decolagem_autorizada'], esperado)
                self.assertEqual(len(prompts), 7)

    def test_entradas_invalidas_sao_repetidas(self):
        e, _, saida = self.executar(['abc', 'nan', 'inf', 23, 20, 495, 92, '?', 's'])
        self.assertEqual(e['integridade'], 1)
        self.assertEqual(saida.count('Valor inválido'), 4)


if __name__ == '__main__':
    unittest.main()
