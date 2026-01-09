# Roguelike Prototype (PgZero)

Este repositório contém um protótipo simples de um roguelike feito com PgZero.

Requisitos
- Python 3.8+
- PgZero

Instalação
1. Crie e ative um ambiente virtual (recomendado):

   python3 -m venv .venv
   source .venv/bin/activate

2. Instale as dependências:

   pip install -r requirements.txt

Execução
Use o `pgzrun` para executar o jogo:

   pgzrun main.py

Controles
- Menu: clique em "Start Game", toggle de música, ou "Exit".
- Jogo: use as setas do teclado para mover o herói entre células (movimento suave).

Notas
- O projeto sintetiza sons pequenos em tempo de execução se não existirem.
- Se quiser adicionar sprites reais, coloque imagens em `images/`.
