"""Camada de dados do TechTrack.

Aqui ficam TODAS as operações com o banco (SQLite). A interface (main.py)
nunca escreve SQL: ela só chama as funções deste arquivo.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("techtrack.db")

TIPOS_MOVIMENTACAO = ["Devolução", "Entrega", "Transferência", "Troca"]
SETOR_TI = "TI"  # destino usado em devoluções


def _conn():
       conn = sqlite3.connect(DB_PATH)
       conn.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
       return conn


def _limpar(valor):
       """Transforma texto vazio em None (e remove espaços nas pontas)."""
       valor = (valor or "").strip()
       return valor or None


def _para_dict(row):
       """Converte uma linha do banco em dict, trocando None por texto vazio."""
       return {k: ("" if row[k] is None else row[k]) for k in row.keys()}


def init_db():
       """Cria as tabelas se ainda não existirem."""
       with _conn() as c:
           c.execute(
               """CREATE TABLE IF NOT EXISTS equipamentos (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   serial_number TEXT NOT NULL UNIQUE,
                   hostname TEXT UNIQUE,
                   colaborador TEXT,
                   setor TEXT,
                   modelo TEXT,
                   fabricante TEXT,
                   tipo_equipamento TEXT DEFAULT 'CPU'
               )"""
           )
           c.execute(
               """CREATE TABLE IF NOT EXISTS movimentacoes (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   equipamento_id INTEGER NOT NULL,
                   tipo TEXT NOT NULL,
                   responsavel_operacao TEXT NOT NULL,
                   data TEXT NOT NULL,
                   colaborador_anterior TEXT,
                   setor_anterior TEXT,
                   colaborador_novo TEXT,
                   setor_novo TEXT,
                   motivo TEXT,
                   FOREIGN KEY (equipamento_id) REFERENCES equipamentos(id)
               )"""
           )
           # Migração segura: acrescenta colunas sem apagar equipamentos existentes.
           colunas = {r[1] for r in c.execute("PRAGMA table_info(equipamentos)").fetchall()}
           if "modelo" not in colunas:
               c.execute("ALTER TABLE equipamentos ADD COLUMN modelo TEXT")
           if "fabricante" not in colunas:
               c.execute("ALTER TABLE equipamentos ADD COLUMN fabricante TEXT")
           if "tipo_equipamento" not in colunas:
               c.execute("ALTER TABLE equipamentos ADD COLUMN tipo_equipamento TEXT DEFAULT 'CPU'")
           # Compatibilidade com cadastros antigos: a categoria genérica vira CPU;
           # notebooks permanecem identificados como Notebook.
           c.execute("UPDATE equipamentos SET tipo_equipamento='CPU' WHERE tipo_equipamento IS NULL OR TRIM(tipo_equipamento)='' OR tipo_equipamento='Máquina'")
           c.execute(
               """CREATE TABLE IF NOT EXISTS estoque (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   item TEXT NOT NULL UNIQUE,
                   quantidade INTEGER NOT NULL DEFAULT 0
               )"""
           )
           # Mantém a tabela antiga para migrar históricos de versões anteriores.
           c.execute("""CREATE TABLE IF NOT EXISTS retiradas_estoque (
               id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL,
               quantidade INTEGER NOT NULL, setor TEXT NOT NULL,
               responsavel TEXT NOT NULL, data TEXT NOT NULL)""")
           # Histórico único de entradas e retiradas do estoque.
           c.execute(
               """CREATE TABLE IF NOT EXISTS movimentacoes_estoque (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   tipo TEXT NOT NULL,
                   item TEXT NOT NULL,
                   quantidade INTEGER NOT NULL,
                   origem TEXT,
                   setor TEXT,
                   data TEXT NOT NULL
               )"""
           )
           c.execute("CREATE TABLE IF NOT EXISTS migracoes (chave TEXT PRIMARY KEY)")
           migrada = c.execute("SELECT 1 FROM migracoes WHERE chave='historico_estoque_v1'").fetchone()
           if not migrada:
               antigas = c.execute("SELECT item, quantidade, setor, data FROM retiradas_estoque ORDER BY id").fetchall()
               for x in antigas:
                   c.execute("INSERT INTO movimentacoes_estoque(tipo,item,quantidade,origem,setor,data) VALUES('Retirada',?,?,?,?,?)",
                             (x['item'], x['quantidade'], '', x['setor'], x['data']))
               c.execute("INSERT INTO migracoes(chave) VALUES('historico_estoque_v1')")
           perifericos = ["Fonte Lenovo", "Fonte HP", "Fonte Dell", "Cabo VGA", "Cabo de força", "Monitor", "Memória RAM", "Mouse", "Teclado", "Cabo de rede"]
           c.executemany("INSERT OR IGNORE INTO estoque(item, quantidade) VALUES(?, 0)", [(x,) for x in perifericos])
           # Padroniza nomes antigos sem perder quantidades já cadastradas.
           for antigo, novo_nome in [("Memória", "Memória RAM"), ("VGA", "Cabo VGA")]:
               row = c.execute("SELECT quantidade FROM estoque WHERE item=?", (antigo,)).fetchone()
               if row:
                   c.execute("UPDATE estoque SET quantidade=quantidade+? WHERE item=?", (row['quantidade'], novo_nome))
                   c.execute("UPDATE movimentacoes_estoque SET item=? WHERE item=?", (novo_nome, antigo))
                   c.execute("DELETE FROM estoque WHERE item=?", (antigo,))
           # Remove apenas os itens antigos sem saldo; qualquer quantidade existente é preservada.
           c.execute("DELETE FROM estoque WHERE item IN ('Headset','Adaptador','Outros') AND quantidade=0")


# ---------- CRUD de equipamentos ----------

def listar(busca="", filtro="todos"):
       """Lista equipamentos; busca por serial, hostname, modelo ou fabricante."""
       termo = f"%{(busca or '').strip()}%"
       with _conn() as c:
           rows = c.execute(
               """SELECT * FROM equipamentos
                  WHERE (serial_number LIKE ? OR hostname LIKE ? OR modelo LIKE ? OR fabricante LIKE ? OR colaborador LIKE ? OR setor LIKE ? OR tipo_equipamento LIKE ?)
                    AND (? = 'todos' OR (? = 'disponiveis' AND (colaborador IS NULL OR colaborador = ''))
                         OR (? = 'uso' AND colaborador IS NOT NULL AND colaborador != '')
                         OR (? = 'notebooks' AND tipo_equipamento = 'Notebook' AND (colaborador IS NULL OR colaborador = ''))
                         OR (? = 'notebooks_uso' AND tipo_equipamento = 'Notebook' AND colaborador IS NOT NULL AND colaborador != '')
                         OR (? = 'maquinas' AND tipo_equipamento = 'Máquina' AND (colaborador IS NULL OR colaborador = ''))
                         OR (? = 'maquinas_uso' AND tipo_equipamento = 'Máquina' AND colaborador IS NOT NULL AND colaborador != ''))
                  ORDER BY id DESC""",
               (termo, termo, termo, termo, termo, termo, termo, filtro, filtro, filtro, filtro, filtro, filtro, filtro),
           ).fetchall()
       return [_para_dict(r) for r in rows]


def criar(serial_number, hostname, colaborador, setor, modelo="", fabricante="", tipo_equipamento="CPU"):
       serial = _limpar(serial_number)
       if not serial:
           raise ValueError("O Serial Number é obrigatório.")
       if not _limpar(modelo) or not _limpar(fabricante):
           raise ValueError("Modelo e fabricante são obrigatórios.")
       try:
           with _conn() as c:
               c.execute(
                   "INSERT INTO equipamentos (serial_number, hostname, colaborador, setor, modelo, fabricante, tipo_equipamento) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (serial, _limpar(hostname), _limpar(colaborador), _limpar(setor), _limpar(modelo), _limpar(fabricante), _limpar(tipo_equipamento) or "CPU"),
               )
       except sqlite3.IntegrityError:
           raise ValueError("Já existe um equipamento com esse Serial Number ou HostName.")


def atualizar(equip_id, serial_number, hostname, colaborador, setor, modelo="", fabricante="", tipo_equipamento="CPU"):
       serial = _limpar(serial_number)
       if not serial:
           raise ValueError("O Serial Number é obrigatório.")
       if not _limpar(modelo) or not _limpar(fabricante):
           raise ValueError("Modelo e fabricante são obrigatórios.")
       try:
           with _conn() as c:
               c.execute(
                   "UPDATE equipamentos SET serial_number=?, hostname=?, colaborador=?, setor=?, modelo=?, fabricante=?, tipo_equipamento=? "
                   "WHERE id=?",
                   (serial, _limpar(hostname), _limpar(colaborador), _limpar(setor), _limpar(modelo), _limpar(fabricante), _limpar(tipo_equipamento) or "CPU", equip_id),
               )
       except sqlite3.IntegrityError:
           raise ValueError("Já existe um equipamento com esse Serial Number ou HostName.")


def excluir(equip_id):
       """Exclui o equipamento e o histórico dele."""
       with _conn() as c:
           c.execute("DELETE FROM movimentacoes WHERE equipamento_id=?", (equip_id,))
           c.execute("DELETE FROM equipamentos WHERE id=?", (equip_id,))


# ---------- Movimentações e histórico ----------

def movimentar(equip_id, tipo, colaborador, setor_destino, motivo, responsavel_operacao):
       """Registra a movimentação e atualiza o equipamento, na mesma transação."""
       if tipo not in TIPOS_MOVIMENTACAO:
           raise ValueError("Selecione o tipo de operação.")
       responsavel = _limpar(responsavel_operacao)
       if not responsavel:
           raise ValueError("Informe o responsável pela operação.")

       if tipo == "Devolução":
           # Devolução = equipamento volta ao controle do setor de TI
           colaborador_novo, setor_novo = None, SETOR_TI
       else:
           colaborador_novo, setor_novo = _limpar(colaborador), _limpar(setor_destino)
           if not colaborador_novo or not setor_novo:
               raise ValueError("Informe o colaborador responsável e o setor de destino.")

       with _conn() as c:
           atual = c.execute("SELECT * FROM equipamentos WHERE id=?", (equip_id,)).fetchone()
           if atual is None:
               raise ValueError("Equipamento não encontrado.")
           c.execute(
               """INSERT INTO movimentacoes
                  (equipamento_id, tipo, responsavel_operacao, data,
                   colaborador_anterior, setor_anterior,
                   colaborador_novo, setor_novo, motivo)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
               (
                   equip_id, tipo, responsavel,
                   datetime.now().strftime("%d/%m/%Y %H:%M"),
                   atual["colaborador"], atual["setor"],
                   colaborador_novo, setor_novo, _limpar(motivo),
               ),
           )
           c.execute(
               "UPDATE equipamentos SET colaborador=?, setor=? WHERE id=?",
               (colaborador_novo, setor_novo, equip_id),
           )


def historico(equip_id):
       """Movimentações de um equipamento, da mais recente para a mais antiga."""
       with _conn() as c:
           rows = c.execute(
               "SELECT * FROM movimentacoes WHERE equipamento_id=? ORDER BY id DESC",
               (equip_id,),
           ).fetchall()
       return [_para_dict(r) for r in rows]





# ---------- Controle de estoque, entradas, retiradas e histórico ----------
def listar_estoque():
       with _conn() as c:
           rows = c.execute("SELECT * FROM estoque ORDER BY item COLLATE NOCASE").fetchall()
       return [_para_dict(r) for r in rows]


def cadastrar_item_estoque(item):
       nome = _limpar(item)
       if not nome:
           raise ValueError("Informe o nome do periférico.")
       with _conn() as c:
           try:
               c.execute("INSERT INTO estoque(item, quantidade) VALUES(?, 0)", (nome,))
           except sqlite3.IntegrityError:
               raise ValueError("Esse periférico já está cadastrado.")


def registrar_entrada_estoque(item, quantidade, origem):
       nome, procedencia = _limpar(item), _limpar(origem)
       try:
           qtd = int(quantidade)
       except (TypeError, ValueError):
           raise ValueError("Informe uma quantidade válida.")
       if not nome or not procedencia or qtd <= 0:
           raise ValueError("Selecione o periférico, informe a quantidade e a origem.")
       with _conn() as c:
           atual = c.execute("SELECT id FROM estoque WHERE item=?", (nome,)).fetchone()
           if atual is None:
               raise ValueError("Periférico não encontrado no estoque.")
           c.execute("UPDATE estoque SET quantidade=quantidade+? WHERE item=?", (qtd, nome))
           c.execute("INSERT INTO movimentacoes_estoque(tipo,item,quantidade,origem,setor,data) VALUES('Entrada',?,?,?,?,?)",
                     (nome, qtd, procedencia, '', datetime.now().strftime("%d/%m/%Y %H:%M")))


def retirar_estoque(item, quantidade, setor):
       nome, destino = _limpar(item), _limpar(setor)
       try:
           qtd = int(quantidade)
       except (TypeError, ValueError):
           raise ValueError("Informe uma quantidade válida.")
       if not nome or not destino or qtd <= 0:
           raise ValueError("Selecione o periférico, informe a quantidade e o setor de destino.")
       with _conn() as c:
           atual = c.execute("SELECT quantidade FROM estoque WHERE item=?", (nome,)).fetchone()
           if atual is None or atual["quantidade"] < qtd:
               raise ValueError("Quantidade insuficiente em estoque.")
           c.execute("UPDATE estoque SET quantidade=quantidade-? WHERE item=?", (qtd, nome))
           c.execute("INSERT INTO movimentacoes_estoque(tipo,item,quantidade,origem,setor,data) VALUES('Retirada',?,?,?,?,?)",
                     (nome, qtd, '', destino, datetime.now().strftime("%d/%m/%Y %H:%M")))


def historico_estoque():
       with _conn() as c:
           rows = c.execute("SELECT * FROM movimentacoes_estoque ORDER BY id DESC").fetchall()
           resumo = c.execute("""SELECT item,
                   SUM(CASE WHEN tipo='Entrada' THEN quantidade ELSE 0 END) AS entradas,
                   SUM(CASE WHEN tipo='Retirada' THEN quantidade ELSE 0 END) AS retiradas
                   FROM movimentacoes_estoque GROUP BY item""").fetchall()
       return {"historico": [_para_dict(r) for r in rows],
               "resumo": [_para_dict(r) for r in resumo]}


# ---------- Indicadores da visão geral ----------
def resumo_dashboard():
       """Conta devoluções, entregas e transferências do mês atual."""
       agora = datetime.now()
       contagem = {"devolucoes": 0, "entregas": 0, "transferencias": 0}
       with _conn() as c:
           rows = c.execute("SELECT tipo, data FROM movimentacoes").fetchall()
       for row in rows:
           try:
               data_mov = datetime.strptime(row["data"], "%d/%m/%Y %H:%M")
           except (TypeError, ValueError):
               continue
           if data_mov.year != agora.year or data_mov.month != agora.month:
               continue
           tipo = (row["tipo"] or "").strip().lower()
           if tipo == "devolução":
               contagem["devolucoes"] += 1
           elif tipo == "transferência":
               contagem["transferencias"] += 1
           elif tipo == "entrega":
               contagem["entregas"] += 1
       return contagem
