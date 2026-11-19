"""TechTrack – abre o sistema no navegador, sem Flask, sem Jinja e sem instalar nada.

Este arquivo usa apenas a biblioteca padrão do Python. Ele serve a página
index.html e responde às chamadas dela, que por sua vez usam as funções do
data.py (nenhum SQL fica aqui).

Como rodar:  python main.py
(o navegador abre sozinho; para encerrar, feche esta janela ou use Ctrl+C)
"""
import json
import re
import traceback
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import data

PASTA = Path(__file__).parent
ENDERECO = "0.0.0.0"
PORTA = int(os.environ.get("PORT", 8080)) #só esse computador consegue acessar


class Handler(BaseHTTPRequestHandler):
       server_version = "TechTrack"

       def log_message(self, *args):  # deixa o terminal limpo
           pass

       # ----- respostas -----

       def _responder(self, corpo, tipo, status=200):
           self.send_response(status)
           self.send_header("Content-Type", tipo)
           self.send_header("Content-Length", str(len(corpo)))
           self.send_header("Cache-Control", "no-store")
           self.end_headers()
           self.wfile.write(corpo)

       def _json(self, dados, status=200):
           corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
           self._responder(corpo, "application/json; charset=utf-8", status)

       def _ler_json(self):
           tamanho = int(self.headers.get("Content-Length") or 0)
           bruto = self.rfile.read(tamanho) if tamanho else b"{}"
           return json.loads(bruto or b"{}")

       def _executar(self, acao, *args):
           """Roda uma função do data.py e devolve {ok: true} ou {ok: false, erro: ...}."""
           try:
               acao(*args)
           except ValueError as erro:
               return self._json({"ok": False, "erro": str(erro)})
           self._json({"ok": True})

       # ----- rotas -----

       def _tratar(self, metodo):
           try:
               url = urlparse(self.path)
               caminho = url.path

               if metodo == "GET" and caminho in ("/", "/index.html"):
                   pagina = (PASTA / "index.html").read_bytes()
                   return self._responder(pagina, "text/html; charset=utf-8")

               if metodo == "GET" and caminho == "/api/config":
                   return self._json({
                       "ok": True,
                       "tipos": data.TIPOS_MOVIMENTACAO,
                       "setor_ti": data.SETOR_TI,
                   })

               if caminho == "/api/equipamentos":
                   if metodo == "GET":
                       params = parse_qs(url.query)
                       busca = params.get("busca", [""])[0]
                       filtro = params.get("filtro", ["todos"])[0]
                       return self._json({"ok": True, "equipamentos": data.listar(busca, filtro)})
                   if metodo == "POST":
                       f = self._ler_json()
                       return self._executar(
                           data.criar,
                           f.get("serial_number"), f.get("hostname"),
                           f.get("colaborador"), f.get("setor"),
                           f.get("modelo"), f.get("fabricante"), f.get("tipo_equipamento"),
                       )

               m = re.fullmatch(r"/api/equipamentos/(\d+)", caminho)
               if m:
                   equip_id = int(m.group(1))
                   if metodo == "PUT":
                       f = self._ler_json()
                       return self._executar(
                           data.atualizar, equip_id,
                           f.get("serial_number"), f.get("hostname"),
                           f.get("colaborador"), f.get("setor"),
                           f.get("modelo"), f.get("fabricante"), f.get("tipo_equipamento"),
                       )
                   if metodo == "DELETE":
                       return self._executar(data.excluir, equip_id)

               m = re.fullmatch(r"/api/equipamentos/(\d+)/movimentar", caminho)
               if m and metodo == "POST":
                   f = self._ler_json()
                   return self._executar(
                       data.movimentar, int(m.group(1)),
                       f.get("tipo"), f.get("colaborador"), f.get("setor_destino"),
                       f.get("motivo"), f.get("responsavel_operacao"),
                   )

               m = re.fullmatch(r"/api/equipamentos/(\d+)/historico", caminho)
               if m and metodo == "GET":
                   return self._json({"ok": True, "historico": data.historico(int(m.group(1)))})

               if metodo == "GET" and caminho == "/api/dashboard":
                   return self._json({"ok": True, "movimentacoes_mes": data.resumo_dashboard()})

               if caminho == "/api/estoque":
                   if metodo == "GET":
                       return self._json({"ok": True, "itens": data.listar_estoque()})

               if caminho == "/api/estoque/itens" and metodo == "POST":
                   f = self._ler_json()
                   return self._executar(data.cadastrar_item_estoque, f.get("item"))

               if caminho == "/api/estoque/entrada" and metodo == "POST":
                   f = self._ler_json()
                   return self._executar(data.registrar_entrada_estoque, f.get("item"), f.get("quantidade"), f.get("origem"))

               if caminho == "/api/estoque/retirar" and metodo == "POST":
                   f = self._ler_json()
                   return self._executar(data.retirar_estoque, f.get("item"), f.get("quantidade"), f.get("setor"))

               if caminho == "/api/estoque/historico" and metodo == "GET":
                   return self._json({"ok": True, **data.historico_estoque()})

               self._json({"ok": False, "erro": "Página não encontrada."}, 404)
           except Exception:
               traceback.print_exc()
               self._json({"ok": False, "erro": "Erro inesperado no TechTrack. Veja a janela do programa."}, 500)

       def do_GET(self):
           self._tratar("GET")

       def do_POST(self):
           self._tratar("POST")

       def do_PUT(self):
           self._tratar("PUT")

       def do_DELETE(self):
           self._tratar("DELETE")



def main():
       if not (PASTA / "index.html").exists():
           raise SystemExit("Não encontrei o index.html na mesma pasta do main.py.")

       data.init_db()

       servidor = ThreadingHTTPServer(
           (ENDERECO, PORTA),
           Handler
       )

       print(f"TechTrack rodando na porta {PORTA}")

       try:
           servidor.serve_forever()
       except KeyboardInterrupt:
           print("\nTechTrack encerrado.")
       finally:
           servidor.server_close()


if __name__ == "__main__":
       main()


