# Hub de Cadernos Científicos — LTDP
### Laboratório Tecnológico de Desenvolvimento e Pesquisa · Lubango, Província da Huíla, Angola
### Fuso horário oficial do sistema: WAT — West Africa Time (UTC+1)

---

## 1. Desenho lógico da arquitectura

A solução é deliberadamente híbrida e tolerante a falhas de conectividade. O coração do sistema é a API Web (FastAPI), que actua como fonte única da verdade e guardiã da integridade intelectual. À sua volta gravitam dois canais de entrada equivalentes: o canal online directo (interface web, Swagger ou futura aplicação) e o canal offline baseado na planilha Excel padronizada, sincronizada por um motor Python quando a internet do laboratório está disponível.

```
                         ┌──────────────────────────────────────────────┐
                         │        HUB LTDP (Cloud ou servidor local)    │
                         │                                              │
   Internet estável      │  ┌────────────┐      ┌────────────────────┐  │
  ┌───────────────┐      │  │  FastAPI   │◄────►│  Base de Dados     │  │
  │ Navegador /   │─────►│  │  (JWT,     │      │  SQLite (piloto)   │  │
  │ Swagger /docs │      │  │  SHA-256,  │      │  PostgreSQL (prod) │  │
  └───────────────┘      │  │  HMAC)     │      └────────────────────┘  │
                         │  └─────┬──────┘                              │
                         │        │ GET /cadernos/export/excel          │
                         │        ▼                                     │
                         │  Dump .xlsx formatado (Diretor do LTDP)      │
                         └────────▲─────────────────────────────────────┘
                                  │ HTTPS (apenas quando há rede)
   Internet instável              │
  ┌───────────────────────────────┴──────────────────────────┐
  │  POSTO DO INVESTIGADOR (Lubango — modo offline-first)    │
  │                                                          │
  │  Caderno_Cientifico_LTDP.xlsx  ──►  sincronizar_hub.py   │
  │  (trabalho diário sem rede)         "Sincronizar com o   │
  │                                      Hub LTDP"           │
  └──────────────────────────────────────────────────────────┘
```

A decisão estrutural mais importante é que **os identificadores (UUID v4) são geráveis offline**. O investigador nunca precisa do servidor para criar um ID de caderno ou de entrada; isso torna a sincronização naturalmente idempotente — a mesma linha enviada duas vezes (por exemplo, após uma queda de rede a meio do envio) é reconhecida pelo Hub e rejeitada com HTTP 409 sem criar duplicados.

A segunda decisão estrutural é a **cadeia de hashes**. Cada entrada científica recebe um SHA-256 calculado sobre uma representação canónica (JSON ordenado) do seu conteúdo, e guarda também o hash da entrada anterior do mesmo caderno (`hash_anterior`), formando uma cadeia de auditoria semelhante a um livro-razão. Para efeitos de patente junto do IAPI, isto permite provar que um resultado existia numa data concreta e que nada foi alterado posteriormente. A fórmula do hash é idêntica no backend e no script de sincronização — qualquer divergência denuncia adulteração.

## 2. Fluxo de sincronização Offline/Online

O ciclo de trabalho do investigador no Lubango decorre assim. Durante o dia, com ou sem internet, regista o progresso na folha `Entradas_Cientificas` da planilha (apenas as colunas Metodologia, Resultados Brutos e Link do Repositório — as restantes são geridas pelo sistema). Quando a rede do laboratório fica disponível, executa o comando `python sincronizar_hub.py Caderno_Cientifico_LTDP.xlsx` (ou o botão/atalho equivalente). O motor então: verifica a ligação ao Hub e autentica-se via JWT (token válido por 12 horas, reduzindo re-autenticações em redes oscilantes); garante que o caderno existe no Hub, criando-o na primeira sincronização; percorre as linhas e envia apenas as que não estão marcadas como `SINCRONIZADO`; recebe de volta o Hash SHA-256 oficial e a assinatura digital, gravando-os na planilha e pintando a linha de verde.

A resolução de conflitos segue três regras. Se o `ID_Entrada` já existe na API, a linha não é duplicada e é simplesmente marcada como sincronizada. Se uma linha já sincronizada foi alterada localmente, o recálculo do hash diverge do hash registado e o motor emite um **alerta de quebra de integridade** (linha a vermelho), instruindo o investigador a criar uma nova entrada de correcção — o caderno é imutável por princípio (`append-only`), tal como um caderno de laboratório físico rubricado. Se a rede cair a meio, as linhas já confirmadas mantêm-se marcadas e as restantes ficam `PENDENTE`, sendo retomadas na sincronização seguinte sem qualquer intervenção manual.

Para integração futura com o Microsoft 365 (OneDrive/SharePoint), o mesmo motor pode ser apontado à Microsoft Graph API em vez do ficheiro local: o endpoint `GET /drives/{id}/items/{id}/workbook/worksheets('Entradas_Cientificas')/usedRange` lê as linhas e o fluxo de envio ao Hub permanece exactamente o mesmo, pelo que a lógica de hash e idempotência não precisa de ser tocada.

## 3. Segurança e contexto local

A autenticação é JWT assinado com HS256 — leve, sem ida e volta de sessões, ideal para ligações intermitentes. Existem três perfis: `DIRETOR` (acesso total, exportação Excel e criação de utilizadores), `INVESTIGADOR` (cria cadernos e entradas) e `TESTEMUNHA` (co-assina entradas). As senhas são guardadas com PBKDF2-SHA256 (120 000 iterações). As assinaturas digitais são HMAC-SHA256 do par email+hash com segredo do servidor, ligando criptograficamente cada registo ao seu autor. Todos os registos transportam nos metadados a localização (`LTDP - Lubango, Huíla, Angola`) e o fuso (`WAT (UTC+1)`), e todas as datas são gravadas em ISO 8601 com offset `+01:00`.

## 4. Como executar

Backend: dentro de `api/`, instalar dependências com `pip install -r requirements.txt` e arrancar com `uvicorn main:app --host 0.0.0.0 --port 8000`. A documentação interactiva fica em `/docs`. No primeiro arranque é criado o utilizador inicial `diretor@ltdp.ao` / `ltdp2026` (alterar via variáveis de ambiente `LTDP_DIRETOR_EMAIL`, `LTDP_DIRETOR_SENHA` e `LTDP_JWT_SECRET`). Para produção, definir `LTDP_DATABASE_URL` com a string PostgreSQL.

Sincronização: distribuir aos investigadores o ficheiro `Caderno_Cientifico_LTDP_Modelo.xlsx` (um por invenção) e o script `sync/sincronizar_hub.py` com o `API_URL` ajustado. O ciclo offline→online descrito acima trata do resto.

---
*Documento técnico — Hub LTDP v1.0 · Junho de 2026 · Lubango, Huíla, Angola*
