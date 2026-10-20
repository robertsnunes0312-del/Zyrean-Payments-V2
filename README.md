# Zyrean Payments — Render Ready

Projeto full-stack da Zyrean Payments preparado para deploy no Render.

## Estrutura correta da raiz

- `app.py`
- `render.yaml`
- `start.sh`
- `start.bat`
- `static/`
- `README.md`

## Render

Build command:

```bash
python -m py_compile app.py
```

Start command:

```bash
python app.py
```

Variáveis:

```text
HOST=0.0.0.0
PAYMENT_MODE=sandbox
```

## Recursos

- Cadastro e login
- Dashboard
- Loja pública
- Produtos
- Pedidos
- Checkout sandbox
- Carteira
- Saques
- Taxa Zyrean de 3%

## Importante

Esta versão usa SQLite e é adequada para sandbox/demonstração. Em produção,
use PostgreSQL ou armazenamento persistente, pois o filesystem de serviços
sem disco persistente pode ser recriado em deploys/reinicializações.

Pagamentos reais devem ser integrados no backend via provedor oficial e webhook.
