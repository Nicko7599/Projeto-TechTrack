"""Camada de dados do TechTrack.

Aqui ficam TODAS as operações com o banco (SQLite). A interface (main.py)
nunca escreve SQL: ela só chama as funções deste arquivo.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("techtrack.db")

TIPOS_MOVIMENTACAO = ["Transferência", "Devolução", "Troca"]
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
                setor TEXT
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


# ---------- CRUD de equipamentos ----------

def listar(busca=""):
    """Lista equipamentos; a busca procura por Serial Number ou HostName."""
    termo = f"%{(busca or '').strip()}%"
    with _conn() as c:
        rows = c.execute(
            """SELECT * FROM equipamentos
               WHERE serial_number LIKE ? OR hostname LIKE ?
               ORDER BY id DESC""",
            (termo, termo),
        ).fetchall()
    return [_para_dict(r) for r in rows]


def criar(serial_number, hostname, colaborador, setor):
    serial = _limpar(serial_number)
    if not serial:
        raise ValueError("O Serial Number é obrigatório.")
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO equipamentos (serial_number, hostname, colaborador, setor) "
                "VALUES (?, ?, ?, ?)",
                (serial, _limpar(hostname), _limpar(colaborador), _limpar(setor)),
            )
    except sqlite3.IntegrityError:
        raise ValueError("Já existe um equipamento com esse Serial Number ou HostName.")


def atualizar(equip_id, serial_number, hostname, colaborador, setor):
    serial = _limpar(serial_number)
    if not serial:
        raise ValueError("O Serial Number é obrigatório.")
    try:
        with _conn() as c:
            c.execute(
                "UPDATE equipamentos SET serial_number=?, hostname=?, colaborador=?, setor=? "
                "WHERE id=?",
                (serial, _limpar(hostname), _limpar(colaborador), _limpar(setor), equip_id),
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
