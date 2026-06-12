-- ============================================================================
-- HUB DE CADERNOS CIENTÍFICOS — LTDP
-- Laboratório Tecnológico de Desenvolvimento e Pesquisa
-- Lubango, Província da Huíla, Angola | Fuso horário: WAT (UTC+1)
-- ============================================================================
-- Compatível com SQLite (modo offline/local) e PostgreSQL (produção cloud).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Tabela de utilizadores (autenticação JWT leve)
-- ----------------------------------------------------------------------------
CREATE TABLE utilizadores (
    id_utilizador     TEXT PRIMARY KEY,                 -- UUID v4
    nome_completo     TEXT NOT NULL,
    email             TEXT NOT NULL UNIQUE,
    perfil            TEXT NOT NULL DEFAULT 'INVESTIGADOR'
                      CHECK (perfil IN ('DIRETOR', 'INVESTIGADOR', 'TESTEMUNHA')),
    senha_hash        TEXT NOT NULL,                    -- PBKDF2-SHA256
    activo            INTEGER NOT NULL DEFAULT 1,
    criado_em         TEXT NOT NULL                     -- ISO 8601 com offset +01:00
);

-- ----------------------------------------------------------------------------
-- Tabela "Cadernos" — um caderno por invenção/investigação
-- ----------------------------------------------------------------------------
CREATE TABLE cadernos (
    id_caderno              TEXT PRIMARY KEY,           -- UUID v4 (gerável offline)
    codigo_ltdp             TEXT NOT NULL UNIQUE,       -- ex.: LTDP/CAD/2026/0001
    titulo_invencao         TEXT NOT NULL,
    investigador_principal  TEXT NOT NULL,
    area_tecnologica        TEXT NOT NULL,              -- ex.: Energias Renováveis, AgroTech
    data_inicio             TEXT NOT NULL,              -- YYYY-MM-DD
    status_trl              INTEGER NOT NULL DEFAULT 1
                            CHECK (status_trl BETWEEN 1 AND 9),
    codigo_patente_previsto TEXT,                       -- ex.: IAPI-AO/2026/XXXX
    estado                  TEXT NOT NULL DEFAULT 'ACTIVO'
                            CHECK (estado IN ('ACTIVO', 'SUSPENSO', 'CONCLUIDO', 'ARQUIVADO')),
    localizacao             TEXT NOT NULL DEFAULT 'LTDP - Lubango, Huíla, Angola',
    fuso_horario            TEXT NOT NULL DEFAULT 'WAT (UTC+1)',
    criado_em               TEXT NOT NULL,
    actualizado_em          TEXT NOT NULL
);

CREATE INDEX idx_cadernos_area   ON cadernos (area_tecnologica);
CREATE INDEX idx_cadernos_trl    ON cadernos (status_trl);
CREATE INDEX idx_cadernos_estado ON cadernos (estado);

-- ----------------------------------------------------------------------------
-- Tabela "Entradas_Cientificas" — registo diário de progresso (imutável)
-- ----------------------------------------------------------------------------
-- Regra de auditoria: as entradas são APPEND-ONLY. Correcções são feitas com
-- nova entrada referenciando a anterior (campo entrada_corrigida), preservando
-- a cadeia de prova para efeitos de propriedade intelectual e patentes.
-- ----------------------------------------------------------------------------
CREATE TABLE entradas_cientificas (
    id_entrada                       TEXT PRIMARY KEY,  -- UUID v4 (gerável offline → sync idempotente)
    id_caderno                       TEXT NOT NULL REFERENCES cadernos (id_caderno),
    data_registo                     TEXT NOT NULL,     -- ISO 8601 com offset +01:00 (WAT)
    metodologia                      TEXT NOT NULL,
    resultados_brutos                TEXT NOT NULL,
    link_repositorio_codigo          TEXT,
    hash_seguranca                   TEXT NOT NULL,     -- SHA-256 do conteúdo canónico
    hash_anterior                    TEXT,              -- encadeamento tipo blockchain (hash da entrada anterior)
    assinatura_digital_investigador  TEXT NOT NULL,     -- HMAC/assinatura do investigador
    assinatura_testemunha            TEXT,              -- assinada posteriormente pela testemunha
    origem_registo                   TEXT NOT NULL DEFAULT 'API'
                                     CHECK (origem_registo IN ('API', 'EXCEL_SYNC')),
    localizacao                      TEXT NOT NULL DEFAULT 'LTDP - Lubango, Huíla, Angola',
    fuso_horario                     TEXT NOT NULL DEFAULT 'WAT (UTC+1)',
    entrada_corrigida                TEXT REFERENCES entradas_cientificas (id_entrada),
    criado_em                        TEXT NOT NULL
);

CREATE INDEX idx_entradas_caderno ON entradas_cientificas (id_caderno, data_registo);
CREATE UNIQUE INDEX idx_entradas_hash ON entradas_cientificas (hash_seguranca);

-- ----------------------------------------------------------------------------
-- Registo de sincronizações (auditoria do motor Excel <-> API)
-- ----------------------------------------------------------------------------
CREATE TABLE log_sincronizacao (
    id_sync          TEXT PRIMARY KEY,
    id_utilizador    TEXT REFERENCES utilizadores (id_utilizador),
    data_sync        TEXT NOT NULL,
    entradas_novas   INTEGER NOT NULL DEFAULT 0,
    duplicados       INTEGER NOT NULL DEFAULT 0,
    alertas_hash     INTEGER NOT NULL DEFAULT 0,        -- quebras de integridade detectadas
    ficheiro_origem  TEXT,
    detalhes         TEXT                                -- JSON com o relatório completo
);

-- ============================================================================
-- EQUIVALENTE NoSQL (JSON) — para MongoDB/CosmosDB, se preferido:
--
-- Colecção "cadernos":
-- {
--   "_id": "uuid", "codigo_ltdp": "LTDP/CAD/2026/0001",
--   "titulo_invencao": "...", "investigador_principal": "...",
--   "area_tecnologica": "...", "data_inicio": "2026-06-12",
--   "status_trl": 3, "codigo_patente_previsto": "IAPI-AO/2026/0042",
--   "metadados": { "localizacao": "LTDP - Lubango, Huíla, Angola",
--                  "fuso_horario": "WAT (UTC+1)" }
-- }
--
-- Colecção "entradas_cientificas": espelha a tabela acima; o campo
-- "hash_seguranca" mantém-se obrigatório e indexado como único.
-- ============================================================================
