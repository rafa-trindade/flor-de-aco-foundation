"""
Códigos de saída padronizados para scripts de extract, usados pelo
run_all.py para decidir se o process deve rodar em seguida.

Um extract pode terminar em 3 estados distintos -- "rodou sem erro" não
é a mesma coisa que "tem dado novo pra processar":

  SUCESSO       (0) -- rodou certo E baixou algo novo -> roda o process
  SEM_NOVIDADE  (2) -- rodou certo, mas nada mudou desde a última vez
                        (todos os arquivos já estavam completos/atualizados)
                        -> NÃO roda o process, não é erro
  ERRO          (1) -- falhou de verdade -> não roda o process, reporta falha
"""
SUCESSO = 0
ERRO = 1
SEM_NOVIDADE = 2