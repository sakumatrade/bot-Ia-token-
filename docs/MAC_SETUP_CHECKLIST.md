# Checklist: rodando o DominusBot no seu Mac

Tudo que foi construído (backend Python, app SwiftUI, extensão Safari) foi
escrito e testado neste ambiente Linux até onde deu — Swift via GitHub
Actions (CI real), TypeScript localmente, Python localmente. Esta lista é
o que falta rodar de verdade, na ordem que faz sentido.

## 0. Pré-requisitos

- [ ] Xcode instalado (Mac App Store) ou `xcode-select --install`
- [ ] Apple ID configurada em Xcode → Settings → Accounts
- [ ] Python 3.12+ instalado (`brew install python@3.12` se precisar)
- [ ] `git pull origin claude/broker-sakuma-macos-app-d17bns` (ou a branch
      atual do projeto)

## 1. Backend (confirma que a base está sólida antes de mexer no app)

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q          # espera-se: 171 passed
```

- [ ] 171 testes passando
- [ ] Subir a API local e confirmar que responde:
  ```bash
  export BROKER_SAKUMA_LOCAL_API__API_KEY="escolha-uma-chave-longa"
  uvicorn broker_sakuma.api.app:create_app --factory --port 8765
  # em outro terminal:
  curl -H "X-API-Key: escolha-uma-chave-longa" http://127.0.0.1:8765/api/dashboard
  ```

## 2. App macOS (SwiftUI)

```bash
cd macapp
open Package.swift    # abre no Xcode como Swift Package
```

- [ ] Compila e roda com ⌘R (com o backend do passo 1 já rodando)
- [ ] Dashboard mostra dados reais (não "sem conexão") — se mostrar "sem
      conexão", confira se a API está no ar na mesma porta (8765) e se a
      chave bate
- [ ] Menu da barra de menu abre, Pausar/Retomar/Parada de Emergência
      funcionam
- [ ] **Esperado, não é bug**: sem wizard de setup, sem GUI de carteiras,
      sem tela do Telegram, sem manual interno — isso é próxima fase

## 3. Empacotamento (.app → .dmg)

```bash
scripts/build_mac.sh     # gera build/DominusBot.app
scripts/package_dmg.sh   # gera build/BrokerSakuma.dmg
```

- [ ] `build/DominusBot.app` abre (clique direito → Abrir, por não
      estar assinado ainda)
- [ ] `build/BrokerSakuma.dmg` monta e mostra o layout arrastar-para-Applications
- [ ] Se algo quebrar aqui, é a primeira vez que esses scripts rodam de
      verdade — reporte o erro exato, não tente "consertar por cima"

## 4. Notarization (só se for distribuir para outros Macs)

Precisa de conta paga Apple Developer Program. Se você só quer usar no
seu próprio Mac, **pule esta etapa** — o app do passo 3 já funciona
localmente.

```bash
export APPLE_DEVELOPER_ID_APPLICATION="Developer ID Application: Seu Nome (TEAMID)"
export APPLE_ID="seu-apple-id@exemplo.com"
export APPLE_TEAM_ID="TEAMID"
export APPLE_APP_SPECIFIC_PASSWORD="senha-de-app-gerada-em-appleid.apple.com"
scripts/notarize.sh
```

- [ ] Assinatura + notarization completam sem erro
- [ ] DMG abre em outro Mac sem aviso do Gatekeeper

## 5. Extensão Safari (opcional, já testada como TypeScript puro)

```bash
cd extension
npm install && npm run build && npm test   # deve já passar, 6/6
xcrun safari-web-extension-converter .      # gera projeto Xcode wrapper
```

- [ ] Projeto abre no Xcode e roda
- [ ] Safari → Preferências → Extensões → habilitar "DominusBot"
- [ ] Popup mostra dados reais (configure a chave da API nas Configurações
      da extensão primeiro)

## O que NÃO vai funcionar ainda (esperado, documentado em docs/PHASES.md)

- Wizard de configuração inicial
- GUI de gerenciamento de carteiras / Keychain Signer real
- Configuração do Telegram pela interface (o backend já sabe processar
  comandos, mas não há tela para isso, nem o bot está de fato rodando
  contra um token real)
- Pesquisa Pump.fun real (só existe o mock/pipeline — sem fonte pública
  de dados real disponível para integrar)
- Trading ao vivo (**propositalmente desabilitado** em todo o sistema)

## Se algo der errado

Prefira reportar o erro exato (comando + saída) a tentar contornar. Nada
aqui foi testado num Mac de verdade ainda — é esperado que a primeira
rodada encontre alguma coisa, e é isso que essa checklist existe para
capturar.
