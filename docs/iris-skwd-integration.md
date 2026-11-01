# Integração iRiS e Skwd-wall: teste local e recuperação

A integração está implementada nos forks locais. A validação disponível usa QML
em modo offscreen, configuração descartável, o daemon real e um controlador
Paper simulado. Os binários gráficos foram compilados, mas nenhuma sessão
Wayland foi iniciada durante o desenvolvimento. Reprodução real, efeitos,
Wallpaper Engine, suspend/resume e posicionamento nos monitores ainda precisam
de teste no desktop.

## Responsabilidades e controles

Em Configurações da iRiS → Papel de parede → Skwd-wall:

- **Gerenciador de papéis de parede:** nativo da iNiR (padrão) ou Skwd-wall.
- **Abrir Skwd-wall:** abre a interface original. Em modo nativo, o daemon
  iniciado pela integração fica impedido de aplicar wallpapers.
- **Seletor de papel de parede:** interface do Skwd ou galeria da iRiS.
- **Monitor para as cores globais:** DP-1 (padrão) ou DP-2.

No Skwd, selecione `skwd-paper` como motor, `iNiR` como autoridade de temas e
**desative pick-only** antes de ativar o modo integrado. A integração verifica
essas condições e recusa uma transferência incompatível. Steam/steamcmd e os
modelos do Lens são dependências opcionais dos recursos correspondentes; não
foram instalados ou configurados automaticamente.

A ilha, o cartão de wallpaper, a ação de troca e o menu do desktop usam o
seletor escolhido. A galeria nativa encaminha aplicações ao Skwd enquanto ele
possui o renderer; a prévia nativa fica suspensa nesse modo. Os recursos
avançados continuam no aplicativo original do Skwd.

Eventos confirmados atualizam a fila de cores da iNiR sem reaplicar o wallpaper.
Quando o monitor escolhido não está conectado, a última referência de cores é
mantida até uma nova confirmação. Wallpapers salvos no Skwd têm prioridade; na
primeira transferência, um monitor sem atribuição recebe o wallpaper nativo
configurado como ponto inicial.

## Teste gráfico sem substituir o runtime instalado

Os executáveis de desenvolvimento já foram compilados. Um conjunto de links,
sem instalação no PATH ou ativação de serviços, está em:

```text
/home/raell/.cache/inir-skwd-staging-ewvppwfw/bin
```

Para gerar outro conjunto depois de recompilar:

```bash
cd ~/Projetos/inir
python scripts/stage-skwd-integration.py
```

O backup anterior continua em
`~/inir-backup/skwd-integration-20261031-174032`; seu SHA-256 foi conferido.
O teste abaixo usa a configuração pessoal e poderá gravar a preferência de
integração e as configurações escolhidas no Skwd. Mantenha um terminal aberto.

Pare a shell supervisionada e execute o checkout em primeiro plano:

```bash
systemctl --user stop inir.service
cd ~/Projetos/inir
INIR_RUNTIME_DIR="$PWD" \
INIR_SKWD_BIN_DIR="$HOME/.cache/inir-skwd-staging-ewvppwfw/bin" \
INIR_DISABLE_HOT_RELOAD=1 \
./scripts/inir run --foreground
```

Esse comando não copia arquivos para `~/.config/quickshell/inir`. Não execute
uma segunda shell enquanto o serviço estiver ativo. O teste temporariamente
substitui a shell visível até seu encerramento.

Abra o Skwd pelas configurações, ajuste os pré-requisitos e selecione o modo
integrado. Teste imagens diferentes em DP-1/DP-2, troca do monitor de referência,
seletores, vídeo, playlist, reinício da shell e retorno ao modo nativo. Verifique
se a referência muda somente após aplicação confirmada e se as configurações de
wallpaper nativo continuam disponíveis ao retornar. Se a transferência falhar,
a iRiS só reinicia o renderer nativo após a confirmação de liberação do Skwd.

## Voltar à instalação atual

Primeiro selecione o modo nativo nas configurações e aguarde a conclusão. Encerre
o processo em primeiro plano com Ctrl+C. Para uma recuperação independente da
interface, com a shell parada:

```bash
cd ~/Projetos/inir
python scripts/skwd-restore-native.py --shell-stopped && \
  systemctl --user start inir.service
```

A ferramenta exige confirmação de liberação pelo daemon, salva uma cópia
`config.json.before-skwd-restore-*` e altera somente `iris.skwd.mode` para
`native`. Não usa comandos Git nem restaura configurações antigas.

Se o daemon não estiver acessível, a ferramenta recusa a troca. Inicie o daemon
protegido no mesmo ambiente de sessão e repita a recuperação após ele ficar
acessível:

```bash
"$HOME/.cache/inir-skwd-staging-ewvppwfw/bin/skwd-walld" --external-wallpaper-owner
```

Use outro terminal para repetir o comando de recuperação; não inicie o renderer
nativo se o Skwd não confirmar a liberação. Uma falha no próprio carregamento da
shell também pode ser contornada com essa ferramenta e o runtime instalado,
que não foi substituído pelo teste.

Após aprovação visual, a cópia do código pode ser feita pelo mecanismo oficial
`./setup update --local`. A instalação permanente dos executáveis Skwd e de seu
ambiente de execução deve ser organizada antes dessa sincronização. Nenhuma
sincronização, alteração de serviço ou publicação foi realizada automaticamente.

## Verificações reproduzíveis

```bash
cd ~/Projetos/inir
python scripts/test-skwd-transport.py
python scripts/test-skwd-handoff.py
python scripts/test-skwd-session-controller.py
python scripts/test-skwd-persistence-gate.py
python scripts/test-skwd-real-config.py
python scripts/test-skwd-daemon-qml.py
python scripts/test-skwd-native-adapter.py
python scripts/test-skwd-restore-native.py
python scripts/test-skwd-real-recovery.py
python scripts/test-skwd-exact-color.py
python scripts/test-iris-defaults.py
```

Os testes que usam o daemon esperam a compilação local em
`../skwd-deck/target/debug/skwd-walld`. Todos criam configurações e sockets
próprios; não conectam ao daemon da sessão pessoal.
