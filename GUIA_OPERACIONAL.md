# Guia Operacional — Hub de Cadernos Científicos LTDP
### Como colocar o sistema em produção e operá-lo no dia a dia
### LTDP · Lubango, Província da Huíla, Angola · WAT (UTC+1)

---

## Fase 1 — Publicar o Hub na cloud (Render, ~15 minutos)

O repositório já inclui o `render.yaml` (Blueprint), pelo que o processo é idêntico ao que foi usado no projecto da Quinta São Luís. Primeiro, crie um repositório no GitHub (por exemplo `ltdp-hub`) e envie todo o conteúdo desta pasta com `git init`, `git add .`, `git commit -m "Hub LTDP v1.1"` e `git push`. Depois, no painel do Render, escolha **New + → Blueprint**, aponte para o repositório e confirme — o Render cria automaticamente o serviço web `ltdp-hub` e a base de dados PostgreSQL `ltdp-hub-db`, já ligados entre si.

Antes do primeiro arranque, o Render vai pedir o valor de `LTDP_DIRETOR_SENHA` (está marcado como `sync: false` para nunca ficar gravado no git) — defina aqui a senha real do Diretor. Confirme também o `LTDP_DIRETOR_EMAIL` no painel de variáveis de ambiente. O `LTDP_JWT_SECRET` é gerado automaticamente pelo Render com valor forte. No fim do deploy, o Hub fica acessível num endereço do tipo `https://ltdp-hub.onrender.com`, com a interface web na raiz, a documentação técnica em `/docs` e o estado do sistema em `/health`.

Duas notas importantes sobre o plano gratuito do Render. Primeiro, o serviço web "adormece" após cerca de 15 minutos sem tráfego e o primeiro acesso seguinte demora 30 a 60 segundos a acordar — comportamento normal, basta aguardar; o script de sincronização já usa timeouts de 30 segundos a contar com isso. Segundo, a base PostgreSQL gratuita do Render tem prazo de validade limitado; quando o Hub passar a guardar dados críticos de patentes, recomendo migrar para o plano pago do Postgres (alguns dólares/mês) ou para um Postgres gratuito permanente externo (ex.: Neon), bastando trocar a variável `DATABASE_URL`. Em alternativa total à cloud, o `Dockerfile` incluído permite correr o Hub num servidor local do próprio LTDP.

## Fase 2 — Configuração inicial (Diretor, ~10 minutos)

Aceda ao endereço do Hub no navegador e entre com as credenciais do Diretor. No botão **Utilizadores**, crie as contas da equipa: perfil `INVESTIGADOR` para quem regista progresso e `TESTEMUNHA` para quem co-assina registos (boa prática para reforço da prova de anterioridade junto do IAPI). Entregue a cada investigador a sua senha inicial e peça-lhes para a memorizar — o token de sessão dura 12 horas, pelo que só precisam de entrar uma vez por dia de trabalho.

## Fase 3 — Distribuir o kit do investigador

Cada invenção recebe uma cópia própria do ficheiro `Caderno_Cientifico_LTDP_Modelo.xlsx` (renomeie, por exemplo, para `Caderno_BombaSolar.xlsx`). No computador de cada investigador é preciso ter o Python instalado com `pip install requests openpyxl`, e o script `sincronizar_hub.py` numa pasta junto das planilhas. Defina no computador a variável de ambiente `LTDP_API_URL` com o endereço do Hub (ex.: `setx LTDP_API_URL https://ltdp-hub.onrender.com` no Windows), ou edite directamente a linha `API_URL` no topo do script.

Para criar o "botão" de sincronização no Windows, basta um ficheiro `Sincronizar_Hub_LTDP.bat` na mesma pasta com o conteúdo:

```
@echo off
set LTDP_API_URL=https://ltdp-hub.onrender.com
python sincronizar_hub.py "Caderno_BombaSolar.xlsx"
pause
```

O investigador trabalha offline na planilha durante o dia (folha `Entradas_Cientificas`, colunas C, D e E) e, quando a internet do laboratório estiver disponível, faz duplo clique no `.bat`. O script autentica, envia as linhas novas, escreve de volta o Hash SHA-256 oficial e pinta cada linha de verde. Linhas que falhem por queda de rede ficam a amarelo (`PENDENTE`) e seguem na tentativa seguinte, sem duplicar nada.

## Fase 4 — Rotina de operação e auditoria

No dia a dia, o Diretor acompanha tudo pela interface web: o painel lista todas as invenções com a barra de maturidade TRL, o estado e o número de entradas; clicar num caderno mostra a cadeia completa de registos com os selos SHA-256 encadeados; o botão **Verificar integridade** em cada entrada recalcula o hash em tempo real e confirma (a verde) que nada foi adulterado; e o botão **Exportar Excel** gera o dump formatado para arquivo físico ou anexo a processos de patente.

Três regras de ouro para a equipa. Nunca editar uma linha já sincronizada na planilha — o sistema detecta e marca quebra de integridade; correcções fazem-se sempre com uma nova entrada (princípio do caderno de laboratório rubricado). Sincronizar no fim de cada dia de trabalho sempre que haja rede, para que a data do selo seja o mais próxima possível do facto científico. E guardar as planilhas locais numa pasta com cópia de segurança (OneDrive, disco externo), porque elas são também o arquivo offline do laboratório.

## Resolução de problemas comuns

Se o script disser "Sem ligação ao Hub LTDP", ou não há internet no momento ou o serviço gratuito do Render está a acordar — aguarde um minuto e repita. Se a autenticação falhar, confirme as credenciais com o Diretor (que pode criar nova conta na interface). Se aparecer "⚠ QUEBRA DE INTEGRIDADE" numa linha, alguém alterou conteúdo já selado: a versão oficial continua intacta no Hub; registe a correcção como nova entrada e reponha o texto original na linha marcada. Se o endpoint `/cadernos/export/excel` devolver 403, é porque a conta usada não tem perfil de Diretor.

---
*Guia operacional — Hub LTDP v1.1 · Junho de 2026*
