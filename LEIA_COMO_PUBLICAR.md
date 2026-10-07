# Como Colocar o Master Server da VoidCore Online 24/7 (Render Gratuito)

Este guia ensina o passo a passo exato para deixar o seu painel de controle administrativo e gerador de licenças ligado 24 horas por dia na nuvem gratuitamente, sem depender do seu computador ficar ligado.

---

## 🚀 Passo a Passo no Render.com (Leva 2 a 3 minutos)

### 1. Criar Repositório no GitHub
1. Acesse [https://github.com](https://github.com) e faça login.
2. Clique em **New repository** (Novo Repositório):
   * Nome: `voidcore-master` (pode colocar como **Private** para segurança).
3. Suba os arquivos desta pasta (`master_server_cloud/`):
   * `master_server.py`
   * `requirements.txt`
   * `Procfile`
   * `Dockerfile`
   * `render.yaml`

---

### 2. Criar a Aplicação Gratuita no Render
1. Acesse [https://render.com](https://render.com) e entre com sua conta do GitHub.
2. Clique no botão azul no topo **"New +"** e selecione **"Web Service"**.
3. Escolha a opção **"Build and deploy from a Git repository"** e selecione o repositório `voidcore-master`.
4. Configure as opções básicas:
   * **Name:** `voidcore-master` (ou o que preferir)
   * **Region:** Ohio (US East) ou Frankfurt
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt` (ou deixe vazio)
   * **Start Command:** `python master_server.py`
   * **Instance Type:** Selecione **Free** ($0/mês)
5. *(Opcional)* Em **Environment Variables**, adicione uma senha personalizada se quiser mudar a padrão:
   * Key: `VOIDCORE_ADMIN_PASS`
   * Value: `sua_senha_secreta_aqui`
6. Clique no botão azul **"Deploy Web Service"**.

---

### 3. Pegar sua URL Pública
Em menos de 1 minuto, o status mudará para **"Live"** (Verde).
O Render criará sua URL com HTTPS seguro no topo da tela, por exemplo:
`https://voidcore-master.onrender.com`

---

### 4. Acessar seu Painel de Administrador
* No seu navegador do computador ou no seu **celular**:
  `https://voidcore-master.onrender.com/admin`
* Digite a senha cadastrada (padrão: `voidcore_admin_2026`).
* Pronto! Você pode aprovar amigos e gerar licenças de qualquer lugar do mundo.

---

### 5. Configurar o VoidCore dos Seus Amigos para se Conectar à Nuvem
1. Abra o arquivo `license_config.json` no projeto local do VoidCore:
   ```json
   {
     "server_url": "https://voidcore-master.onrender.com",
     "app_version": "2.0.0"
   }
   ```
2. Recompile o instalador executando:
   `python build_installer.py`
3. O novo executável `dist/VoidCore_Setup.exe` já sairá configurado para se conectar diretamente ao seu servidor na nuvem!
