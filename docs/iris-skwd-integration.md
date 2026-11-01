# Integração iRiS e Skwd-wall: teste local e recuperação

A integração está implementada nos forks locais. A validação disponível usa QML
em modo offscreen, configuração descartável e o daemon real, com renderizadores,
controlador Paper e interface gráfica simulados. Os binários gráficos foram
compilados, mas nenhuma sessão Wayland foi iniciada durante o desenvolvimento. Reprodução real, efeitos,
Wallpaper Engine, suspend/resume e posicionamento nos monitores ainda precisam
de teste no desktop.

## Responsabilidades e controles

Em Configurações da iRiS → Papel de parede → Skwd-wall:

- **Gerenciador de papéis de parede:** nativo da iNiR (padrão) ou Skwd-wall.
- **Abrir Skwd-wall:** ativa a integração automaticamente e abre a interface
  original após a transferência do controle de renderização.
- **Seletor de papel de parede:** interface do Skwd ou galeria da iRiS.
- **Monitor para as cores globais:** DP-1 (padrão) ou DP-2.

Selecionar **Skwd-wall** como gerenciador ou clicar em **Abrir Skwd-wall**
configura automaticamente o motor `skwd-paper`, a autoridade de temas `iNiR` e
desativa o modo somente seleção. Não é necessário ajustar esses pré-requisitos
na interface do Skwd. A configuração ocorre com a renderização do Skwd bloqueada,
antes de parar o renderer nativo. As outras preferências são preservadas; uma
cópia original é salva em `~/.config/skwd-wall-v2/config.before-inir-integration.json`
(ou no diretório XDG correspondente), sem sobrescrever uma cópia já existente.
Ao voltar ao modo nativo, o Skwd permanece impedido de renderizar e de gerar
temas; suas preferências não são restauradas automaticamente por cima de edições
posteriores. Steam/steamcmd e modelos do Lens continuam opcionais.

A ilha, o cartão de wallpaper, a ação de troca e o menu do desktop usam o
seletor escolhido. A galeria nativa encaminha aplicações ao Skwd enquanto ele
possui o renderer; a prévia nativa fica suspensa nesse modo. Os recursos
avançados continuam no aplicativo original do Skwd.

Eventos confirmados atualizam a fila de cores da iNiR sem reaplicar o wallpaper.
Uma aplicação global em `*` publica uma confirmação para cada monitor conectado.
A verificação de saúde reconhece tanto atribuições prontas do controlador Paper
quanto os renderizadores estáveis supervisionados diretamente pelo daemon;
processos de transição e preferências salvas, sozinhos, não confirmam saúde.
Listas recebidas pelos sinais QML são normalizadas para evitar falsas falhas.
A consulta periódica também não adia uma geração de cores já agendada.
O próprio Skwd recebe a paleta Material pronta da iNiR em
`$XDG_STATE_HOME/quickshell/user/generated/colors.json` (por padrão,
`~/.local/state/quickshell/user/generated/colors.json`). O daemon aproveita o
contrato de importação Material existente, atualiza somente seu cache de cores
e notifica a interface pelo evento `theme_done`, que aplica sua transição visual.
A paleta já existente é carregada também na inicialização e na ativação da
autoridade iNiR. Esse caminho não gera temas, não altera a paleta da shell e não
aplica novamente o wallpaper. Arquivos incompletos mantêm a última paleta válida.
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

Se ainda houver uma sessão de teste anterior, encerre-a primeiro e feche a
janela do Skwd. É necessário reiniciar também o daemon antigo para carregar as
correções; recompilar o arquivo não atualiza um processo já em execução.

Pare a shell supervisionada, confirme a liberação do Skwd e só então encerre o
daemon anterior (o último comando não inicia nenhum renderer):

```bash
systemctl --user stop inir.service
cd ~/Projetos/inir
python scripts/skwd-restore-native.py --shell-stopped && \
  { pkill -u raell -x skwd-walld || test "$?" -eq 1; }
```

Se a recuperação falhar, siga a seção de recuperação abaixo antes de continuar.
Com a recuperação concluída, execute o checkout em primeiro plano:

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

Nas configurações da iRiS, selecione **Skwd-wall** como gerenciador ou use
**Abrir Skwd-wall**. A preparação é automática. Teste imagens diferentes em
DP-1/DP-2, troca do monitor de referência, seletores, vídeo, playlist, reinício da shell e retorno ao modo nativo. Verifique
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

O teste `test-skwd-daemon-qml.py` parte de motor AWWW, autoridade Skwd e modo
somente seleção. Ele aciona o botão de abertura, verifica a preparação automática
e seu backup, usa a imagem nativa para inicializar DP-1/DP-2, aplica outra imagem
em todos os monitores com transição, verifica eventos de cores e várias consultas
de saúde, e retorna ao modo nativo. A renderização e a janela reais permanecem
para o teste visual.

Para verificar o retorno das cores ao Skwd sem sessão gráfica:

```bash
cd ~/Projetos/skwd-deck
python tests/integration-inir-palette-isolated.py
```

Depois dessa correção, basta carregar o daemon recompilado. Na sessão de teste,
selecione primeiro **Nativo da iNiR** e aguarde a liberação, feche o Skwd, encerre
o daemon antigo com `pkill -u raell -x skwd-walld` e selecione **Skwd-wall**
novamente. A própria shell iniciará o executável preparado no diretório de teste.
Não é necessário sincronizar ou substituir a instalação ativa para testar isso.

## Instalação permanente aprovada

Após a aprovação visual do fluxo de wallpaper e das cores da shell e do Skwd,
os executáveis testados foram copiados para uma versão independente dos diretórios
de compilação em `~/.local/lib/inir-skwd/releases/20261101-005224/bin`.
`~/.local/lib/inir-skwd/current` aponta para essa versão, com launchers em
`~/.local/bin`. O manifesto da versão registra os commits e SHA-256 dos binários.
A biblioteca Steam compartilhada acompanha o helper no mesmo diretório.

A iNiR é sincronizada por `./setup update --local`, mantendo `repo-copy` e a
branch `feature/iris-skwd-integration`. Não existe um serviço Skwd independente
habilitado: a shell inicia o daemon quando necessário, preservando a transferência
de controle. A interface também fica disponível no menu de aplicativos.

O backup imediatamente anterior à instalação está em
`~/inir-backup/skwd-install-20261101-005224`, com arquivo completo, SHA-256 e
manifesto dos arquivos. A recuperação pode ser conferida sem alterar a sessão:

```bash
inir-skwd-rollback --verify
```

Para restaurar o runtime anterior e voltar ao modo nativo:

```bash
inir-skwd-rollback
```

A ferramenta para a shell, exige confirmação de liberação do Skwd, preserva as
preferências atuais selecionando apenas o modo nativo e restaura runtime,
launcher e metadados anteriores. O runtime integrado é movido para um diretório
vizinho de recuperação; não são executados comandos Git. Os binários Skwd
permanecem instalados e bloqueados para renderização no modo nativo.
