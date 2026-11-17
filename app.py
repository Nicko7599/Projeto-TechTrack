"""Interface web do TechTrack (Flask).

Este arquivo só recebe as requisições e chama as funções do data.py.
Nenhum SQL fica aqui.
"""
from flask import Flask, flash, redirect, render_template, request, url_for

import data

app = Flask(__name__)
app.secret_key = "techtrack-dev"  # necessário para as mensagens (flash)

data.init_db()


def _executar(acao, mensagem_ok, *args):
    """Roda uma função do data.py e mostra sucesso ou erro na tela."""
    try:
        acao(*args)
        flash(mensagem_ok, "ok")
    except ValueError as erro:
        flash(str(erro), "erro")


@app.route("/")
def home():
    busca = request.args.get("busca", "")
    equipamentos = data.listar(busca)
    for equip in equipamentos:
        equip["historico"] = data.historico(equip["id"])
    return render_template(
        "index.html",
        equipamentos=equipamentos,
        busca=busca,
        tipos=data.TIPOS_MOVIMENTACAO,
        setor_ti=data.SETOR_TI,
    )


@app.route("/criar", methods=["POST"])
def criar():
    f = request.form
    _executar(
        data.criar, "Equipamento cadastrado.",
        f.get("serial_number"), f.get("hostname"), f.get("colaborador"), f.get("setor"),
    )
    return redirect(url_for("home"))


@app.route("/atualizar/<int:equip_id>", methods=["POST"])
def atualizar(equip_id):
    f = request.form
    _executar(
        data.atualizar, "Equipamento atualizado.",
        equip_id, f.get("serial_number"), f.get("hostname"), f.get("colaborador"), f.get("setor"),
    )
    return redirect(url_for("home"))


@app.route("/excluir/<int:equip_id>", methods=["POST"])
def excluir(equip_id):
    _executar(data.excluir, "Equipamento excluído.", equip_id)
    return redirect(url_for("home"))


@app.route("/movimentar/<int:equip_id>", methods=["POST"])
def movimentar(equip_id):
    f = request.form
    _executar(
        data.movimentar, "Movimentação registrada.",
        equip_id, f.get("tipo"), f.get("colaborador"), f.get("setor_destino"),
        f.get("motivo"), f.get("responsavel_operacao"),
    )
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
