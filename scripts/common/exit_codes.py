"""Códigos de saída para orquestração no run_all.py.

Estados possíveis:
  SUCESSO (0): Execução concluída e novos dados extraídos -> aciona o process.
  ERRO (1): Falha na execução -> interrompe a esteira e reporta erro.
  SEM_NOVIDADE (2): Execução concluída sem dados novos (idempotência) -> pula o process sem relatar erro.
"""
SUCESSO = 0
ERRO = 1
SEM_NOVIDADE = 2