# Regra Permanente — Integridade de Dados em Toda Configuração e Atualização Futura

Este documento define uma regra fixa e permanente obrigatória para **todo** código escrito no aplicativo Shanti Studio, em qualquer tela, tela nova ou funcionalidade nova. Esta regra vigora por padrão em qualquer tarefa, sem necessidade de ser repetida.

**Motivo:** Evitar que o ato de salvar dados ou configurações em uma tela apague ou sobrescreva dados que a Natália ou outro usuário preencheu em outra tela, ou que textos de placeholder (como "informe usuário", "não informado") sejam gravados no banco de dados.

---

## As 6 Regras Fixas

1. **Nunca sobrescrever o registro inteiro:**
   Toda ação de salvar deve enviar e atualizar **apenas os campos que aquela tela específica edita** — nunca o objeto completo do aluno, da configuração ou de qualquer outro registro.

2. **Atualização parcial, não substituição:**
   No backend, salvar significa "atualizar estes campos específicos", preservando automaticamente todos os outros campos já existentes no banco — nunca montar um registro novo do zero substituindo o existente.

3. **Placeholder é só visual, nunca é dado:**
   Textos como "informe usuário", "não informado", "nenhum", etc., servem exclusivamente para exibição quando um campo está vazio na tela. Eles **nunca** podem ser gravados no banco de dados como se fossem o valor real de um campo.

4. **Antes de salvar, carregar o estado atual:**
   Qualquer tela de edição deve carregar o registro atual do banco antes de permitir a edição, aplicar somente a mudança feita pelo usuário e gravar de volta — nunca assumir que o que não está visível na tela pode ser zerado.

5. **Teste Obrigatório antes de qualquer entrega:**
   Toda funcionalidade nova que inclua salvar dados precisa, antes de ser considerada concluída, passar por este teste:
   - Preencher/alterar um campo em uma tela.
   - Salvar em uma tela ou funcionalidade diferente.
   - Confirmar que o primeiro campo continua exatamente como estava.
   *Se esse teste falhar, a funcionalidade não está pronta.*

6. **Backup obrigatório em alterações de schema:**
   Qualquer alteração de schema ou estrutura de dados continua exigindo backup antes de aplicar.

---

## Protocolo de Execução para o Antigravity
Ao final de qualquer nova tarefa ou funcionalidade entregue:
- Executar e validar o teste de integridade da Regra 5.
- Confirmar explicitamente ao usuário no relatório final que o teste da Regra 5 foi executado com sucesso e que nenhum dado pré-existente foi corrompido ou sobrescrito.
