# Publicação de demonstração — Painel Inteligente de Cadastro de Empresas

**Apenas para testes com dados fictícios.** Esta versão NÃO é segura para dados reais de clientes e NÃO consulta nem emite certidões automaticamente. Não possui login individual, MFA, banco persistente, backup, proteção contra abuso ou armazenamento durável no plano gratuito. O token é compartilhado e deve ser tratado como segredo. Os dados e PDFs podem ser apagados a qualquer momento por reinício ou redeploy.

## Caminho sugerido: Render (sujeito a disponibilidade do plano gratuito)

1. Crie uma conta no GitHub e um repositório **privado** para este projeto.
2. Extraia este ZIP e envie o conteúdo da pasta para a raiz do repositório. **Nunca** envie `.env`, `data/`, tokens ou PDFs reais.
3. Crie uma conta no Render e conecte o GitHub. Use **New > Blueprint** e selecione o repositório que contém `render.yaml`.
4. Revise os recursos e custos mostrados antes de confirmar. Se o plano `free` não estiver disponível, não confirme um plano pago sem desejar isso.
5. Após a publicação, abra a URL `https://<nome-atribuido>.onrender.com` exibida pelo próprio Render. O nome final depende da disponibilidade e não pode ser garantido antecipadamente.
6. No painel do serviço no Render, em **Environment**, localize `PAINEL_API_TOKEN`. Use o valor apenas na tela de acesso do aplicativo e não o compartilhe. Se não for possível visualizar um valor gerado, configure manualmente um segredo longo e aleatório e faça redeploy.
7. Teste exclusivamente com empresas e certidões fictícias. A plataforma pode suspender serviços gratuitos ociosos e a inicialização pode demorar.

## Arquitetura desta demonstração

Navegador HTTPS -> hospedagem Render -> FastAPI/Uvicorn -> SQLite temporário + PDFs Fernet em disco efêmero.

## Arquitetura exigida para produção

HTTPS + autenticação individual/MFA + controle de acesso por escritório + PostgreSQL gerenciado + armazenamento privado de PDFs com criptografia e backups testados + logs de auditoria + gestão de segredos + política LGPD + conectores oficiais homologados. Esta arquitetura NÃO está implementada no pacote de demonstração.

## Certidões

A aplicação apenas abre portais oficiais e registra manualmente resultados. Não executa consultas reais, não automatiza CAPTCHA e não emite PDFs oficiais. Integrações devem ser desenvolvidas e autorizadas por órgão.

## Alternativa

Se a hospedagem gratuita não estiver disponível, não publique este MVP em um servidor exposto sem controles de segurança. Continue os testes locais até preparar uma versão de produção.
