# Project-RS

# Autores do Trabalho:

- David Saraiva Monteiro (125793)

- Murilo Frezzato Francisco (xxxxxx)

- Lucas Morgado dos Reis (xxxxxx)

# Comandos a utilizar:

0. Gerar os ficheiros proto quando é preciso

- python3 -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. game.proto

1. Criar o ambiente venv

- python3 -m venv venv
// Para sair do venv basta escrever deactivate

2. Ativar o ambiente venv

- source venv/bin/activate

3. Instalar os requisitos

- pip install -r requirements.txt

4. Iniciar o Jogo

- python3 main.py <Nome do jogador> <Classe do jogador> <tcp.port> 

// Para jogar em mais de um PC
- python3 main.py <Nome do jogador> <Classe do jogador> <tcp.port> 192.168.0.<Ip pc do host>

// Para jogar em 2 ou mais terminais
- python3 main.py <Nome do jogador> <Classe do jogador> <tcp.port> 127.0.0.1






