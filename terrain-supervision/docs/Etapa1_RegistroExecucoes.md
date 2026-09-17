# Etapa 1 — Registro das execuções

Data: 16/09/2026.

## Escopo
Instrumentação opcional para observar o agente. Não modifica o prompt, o histórico
enviado, os limites, as ferramentas, o corpus, o juiz ou as proteções. Não bloqueia
repetições. As próximas etapas dependem de autorização do responsável.

## Compatibilidade com o projeto
O enunciado, seção 2 e cronograma, prevê ampliação do agente e da instrumentação
antes da calibração/congelamento. As seções 5 e 6 exigem a mesma base nas
comparações e proíbem alterar os dados isoladamente. O juiz deve ser determinístico.
O README exige preservar a interface Agent(...).executer(...), pontos de injeção
e juiz comuns; terrain/ é congelado após calibração. Esta mudança preserva a
compatibilidade da interface e o ponto único de consulta das proteções.

## Uso
Dentro de terrain-supervision, com o ambiente virtual ativado:

~~~bash
python run.py diagnostic --modele ollama --ollama-modele qwen2.5:3b --protections aucune --debug --journal diagnostic-qwen.jsonl
~~~

Um nome simples, como diagnostic-qwen.jsonl, é salvo em terrain-supervision/logs/,
independentemente do diretório de execução. A pasta é criada automaticamente.
Caminhos explícitos com pastas ou absolutos continuam sendo respeitados, e suas
pastas também são criadas. O terminal mostra o caminho completo do arquivo.
Se o arquivo existir, novas campanhas são acrescentadas com identificadores
diferentes. Para separar campanhas em arquivos, use nomes diferentes.
Sem --journal, a saída e o funcionamento anteriores são preservados.

Para registrar a campanha completa:

~~~bash
python run.py calibrer --modele ollama --ollama-modele qwen2.5:3b --protections aucune --journal calibracao-qwen.jsonl
~~~

## Conteúdo do arquivo
O arquivo guarda eventos em JSON com indentação de 2 espaços. Cada evento é um
objeto completo, separado do seguinte por uma linha em branco. Continua sendo
um fluxo append-only: campanhas novas são acrescentadas ao mesmo arquivo.
Os eventos possuem horário UTC, identificador da campanha, da execução e etapa
quando aplicáveis. A versão do registro é `2` (legível); leitores devem aceitar
também o formato compacto antigo (um objeto por linha, `version: 1`).

- campagne_debut / campagne_fin: configuração e término do comando.
- execution_debut: identificação do caso, tarefa e limite.
- etape_debut: histórico fornecido ao cliente.
- modele_requete: endereço e corpo completo enviado ao Ollama, com mensagens,
  instruções, formato e opções.
- modele_reponse: resposta completa do Ollama, sem o corte de 300 caracteres.
- modele_erreur: erro da comunicação; tentativas com outro formato também
  possuem eventos próprios.
- decision: ação interpretada.
- outil_decision: argumentos, autorização e motivo da recusa.
- outil_resultat: resultado completo, origem, fonte e observação reduzida que
  entra no histórico. Ferramentas recusadas não são executadas.
- execution_fin: fin_modele, limite_etapes, erreur_format, erreur ou interruption.
- attaque_verdict / tache_verdict: resultado associado à execução.

O teste inicial de conexão do diagnostic fica associado à campanha, sem uma
etapa do agente. O simulador não produz eventos de requisição/resposta HTTP.
Os registros incluem textos de ataque e podem incluir o segredo sintético do
laboratório. Não são reinjetados no contexto do modelo.

Cada evento é gravado e descarregado imediatamente. Erros e Ctrl+C são
registrados e propagados. Encerramento forçado ou perda de energia podem deixar
uma campanha incompleta. Erros de gravação são expostos, não ignorados.
O histórico pode continuar repetitivo: esta etapa apenas permite observá-lo.
Para ler o arquivo em Python, use `terrain.journal.lire_evenements(caminho)`,
que aceita o formato indentado e o JSONL compacto antigo.

## Banco de dados
O enunciado sugere SQLite para memória de tentativas do atacante. Persistir
histórico do alvo também é uma possibilidade, não uma exigência.
O banco guarda os dados, mas o cliente precisa selecionar informações e
incluí-las nas mensagens. Não elimina o uso de memória durante processamento
ou inferência. Consultas pelo Python limitadas à execução são uma opção simples;
dar ao modelo outra ferramenta de busca alteraria a base funcional.
SQLite e recuperação do histórico não foram implementados nesta etapa.

## Validação
Testes automatizados com transporte Ollama simulado comparam as requisições
e resultados com e sem registro. Também cobrem recusas, limite de etapas,
erros, interrupções, separação de execuções, campanhas acrescentadas ao arquivo,
mudança de formato e os 50 casos da calibração com simulador.
Não foi executada uma nova campanha com o Qwen real.
