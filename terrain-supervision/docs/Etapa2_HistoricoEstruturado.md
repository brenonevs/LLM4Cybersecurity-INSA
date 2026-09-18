# Etapa 2 — Histórico estruturado
Data: 16/09/2026. Implementação autorizada separadamente da etapa 3.

Cada tarefa cria um histórico novo. Ele guarda a ação normalizada, seus
argumentos, o resultado completo e a autorização/recusa. O cliente Ollama envia
cada ação como mensagem assistant e o resultado como mensagem user identificada
como resultado de ferramenta. Não foi introduzido o protocolo nativo de tool
calling: o projeto continua usando decisões em JSON.

Todas as ações da tarefa são preservadas no contexto, em vez de apenas seis
observações. Com o limite padrão de oito decisões, são no máximo sete pares
anteriores apresentados à última decisão. O registro inclui tentativas recusadas,
que são identificadas como recusadas, sem tratá-las como ações executadas.

Para limitar textos longos, cada resultado enviado pode usar até 1.200
caracteres. O conjunto de resultados no histórico usa no máximo 4.800
caracteres: esse orçamento é dividido entre os resultados já existentes. Os
argumentos corps/contenu também são reduzidos a 1.200 caracteres com um marcador,
apenas na representação enviada ao modelo. Destinatário, equipamento e busca são
preservados. Cada resultado informa `resultat_tronque` e
`limite_resultat_modele`, para distinguir uma carga vista de uma carga cortada.
O registro completo permanece disponível no log; o histórico estruturado também
guarda os textos completos.

O simulador mantém a mesma visão de observações textuais para preservar seus
testes determinísticos. Chamadores antigos que passam uma lista de strings ao
cliente continuam compatíveis. O uso normal por Agent utiliza a nova estrutura.
O log identifica a configuração como actions-resultats-v2.

Não foram alterados SYSTEME, o juiz, o corpus, as ferramentas ou as proteções.
Não há bloqueio de repetição nem SQLite. A representação diferente pode mudar
o comportamento do modelo e dos ataques, portanto exige nova medição sem defesa.

## Testar com o modelo real
Dentro de terrain-supervision:

    python run.py diagnostic --modele ollama --ollama-modele qwen2.5:3b --protections aucune --debug --journal diagnostic-qwen-etapa2.jsonl

O arquivo vai para logs/. Compare decisões, repetições, endereços, resultado das
tarefas e motivos de encerramento. Menos chamadas não garante tarefa correta.
Os testes automatizados verificam mensagens, isolamento, retenção de ações
antigas, recusas e cortes explícitos. Não comprovam redução de repetição no Qwen.

## Correção da geração prolongada — 16/09/2026
Os logs locais do Ollama mostraram geração contínua de mais de 5.400 tokens
antes do timeout de 300 segundos. O servidor estava gerando, não esperando a
ferramenta de busca. Não foi comprovada uma falha exclusiva do JSON Schema:
testes limitados a 256 tokens com schema e json retornaram ambos por limite.

O cliente agora define num_predict=768 por resposta. Uma resposta com
done_reason=length é rejeitada antes do parsing, mesmo se contiver um JSON
aparentemente válido. Há uma única recuperação por limite na decisão inicial:
o programa pede uma ação em JSON completo e breve, com campos textuais de até
500 caracteres. Esse pedido é uma orientação, não uma validação de comprimento.
Se a segunda resposta também exceder o limite, uma exceção é propagada e
registrada; a execução não é classificada como ataque bloqueado.
A tentativa adicional de reparo de JSON já existente também fica sujeita ao
limite e não inicia novas recuperações por comprimento.

A instrução de recuperação muda o pedido nessa condição e faz parte da
configuração experimental, embora SYSTEME permaneça inalterado. A mesma
configuração deve ser usada nos ensaios com e sem proteção.
O timeout de rede continua em 300 segundos: limitar geração não garante que
um servidor indisponível responda. Não foram adicionados bloqueios de ferramentas
repetidas nem correção automática de destinatário.
