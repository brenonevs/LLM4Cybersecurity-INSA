Com base na integração de toda a fundamentação teórica (Denning, Goguen, NDN) e nas arquiteturas práticas analisadas (FIDES e CaMeL), temos um guia inicial. As duas arquiteturas modernas se complementam: enquanto o FIDES foca na mecânica de ocultação seletiva de variáveis e na desclassificação segura por decodificação restrita, o CaMeL foca na geração de código interpretado, na manutenção de um Grafo de Fluxo de Dados e na mitigação de canais laterais através do modo STRICT.

O guia foi criado apenas a partir da bibliografia do projeto, e nao teve acesso aos aarquivos de código. Entao esse guia está sujeito a mudanças.

Abaixo está um guia inicial para as próximas etapas práticas do seu projeto:

### Fase 1: Construção da Arquitetura de Defesa (O Sistema)

* **Implementação do Padrão Dual-LLM (CaMeL & FIDES):** Dividir as operações em um LLM Privilegiado (P-LLM), que atua como planejador e gera código expressando a intenção do usuário sem acessar dados não confiáveis, e um LLM em Quarentena (Q-LLM), sem acesso a ferramentas e dedicado a parsear dados não estruturados.


* **Ocultação Seletiva e Expansão Tardia (FIDES):** O sistema deve armazenar os resultados das ferramentas em variáveis (ex: `#ticket_14#`) para não contaminar o P-LLM, inserindo o texto bruto de volta na chamada apenas através da função `EXPAND` no milissegundo em que a ferramenta for executada.


* **Grafo de Fluxo de Dados e Capabilities (CaMeL & NDN):** O interpretador deve manter uma Árvore Sintática Abstrata (AST) do código gerado pelo P-LLM e rastrear as dependências de cada variável através de *capabilities* — metadados que guardam a proveniência (origem) do dado e seus leitores permitidos. A propagação dessa contaminação segue a lógica matemática de limites superiores de Denning.


* **Inspeção Segura por Decodificação Restrita (FIDES):** Implementar a ferramenta `query_llm` forçando o Q-LLM a emitir apenas respostas de baixa capacidade de informação (como um `bool`). Isso atua como um mecanismo seguro de desclassificação, permitindo que o P-LLM tome decisões lógicas baseadas em dados externos sem absorver injeções.


* **Mitigação de Canais Laterais via Modo ESTREITO (STRICT Mode - CaMeL):** Para impedir vazamentos implícitos (Goguen), o interpretador deve forçar que todas as variáveis ou ações executadas dentro de estruturas condicionais (`if`, `for`), bem como todas as instruções que ocorrem após uma chamada ao Q-LLM, herdem obrigatoriamente as dependências da condição testada ou dos argumentos do Q-LLM.


* **Políticas de Segurança Determinísticas:** A execução de qualquer ferramenta deve ser bloqueada se as *capabilities* das variáveis fornecidas nos argumentos violarem as regras de fluxo estabelecidas no momento da execução.



---

### Fase 2: Construção do Atacante Agêntico (A Exploração)

* **Exploração de Desclassificação (Lavagem de Proveniência):** O foco principal do ataque será criar injeções em dados não estruturados (ex: tickets, e-mails) que manipulem semanticamente o Q-LLM durante a inspeção. O objetivo é forçar a emissão de respostas estruturadas falsas (como um `True` malicioso) para apagar a etiqueta original do dado e induzir o P-LLM a acionar ferramentas indevidas.


* **Ataques Texto-para-Texto (Text-to-Text):** Uma vez que as defesas focam na proteção do fluxo de controle, o atacante deve explorar vulnerabilidades inerentes (não-objetivos do CaMeL) injetando instruções que induzam o Q-LLM a falsificar relatórios ou resumos que serão entregues diretamente ao usuário, sem tentar acionar ferramentas restritas.


* **Canais Laterais por Inferência Indireta (Bypass do Modo STRICT):** O atacante tentará injetar laços de repetição (como `for`) usando variáveis privadas como limite, acoplados a requisições externas aparentemente inofensivas. O objetivo será descobrir formas de burlar o rastreamento do Modo STRICT para contar as requisições em um servidor externo e deduzir o valor da variável secreta.


* **Vazamento de 1 Bit por Exceção:** O atacante testará a injeção de comandos no Q-LLM que gerem falhas de código propositais apenas quando uma variável privada atender a uma condição específica, usando o travamento da execução para inferir segredos bit a bit.


* **Sequestro pelo Tratamento de Erros:** O invasor induzirá falhas no interpretador para testar o sistema de correção. Se o CaMeL ou FIDES enviar avisos de erro que contenham dados brutos não higienizados de volta ao P-LLM, o invasor utilizará esse canal para realizar uma injeção de prompt direta no planejador.