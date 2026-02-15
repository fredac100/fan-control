# Fan Aggressor

Controle dinâmico de ventiladores e gerenciamento de energia CPU para o **Acer Predator Helios Neo 16 (PHN16-72)** no Linux.

> **Aviso**: Este projeto foi desenvolvido e testado exclusivamente no **Acer Predator PHN16-72**. Não há garantia de funcionamento em outros modelos.

## Pré-requisito: nekro-sense

Este projeto depende do módulo kernel [nekro-sense](https://github.com/fredac100/nekro-sense) para comunicação com o hardware via WMI. O nekro-sense substitui o driver `acer_wmi` do kernel e expõe controles de ventiladores, RGB e perfis de energia via sysfs.

**Instalação detalhada na seção "Instalação" abaixo.**

## Funcionalidades

### Controle de Ventiladores
- **Curva dinâmica de temperatura** - Velocidade dos fans varia conforme a temperatura
- **Offset configurável** - Adiciona ou remove porcentagem sobre a curva base
- **Modo Híbrido** - Ativa boost apenas quando temperatura atinge threshold
- **Controle separado CPU/GPU** - Offsets independentes para cada ventilador

### Gerenciamento de Energia CPU
- **Power Profiles** - 5 perfis pré-configurados com aplicação instantânea
- **CPU Governor** - Alterna entre `performance` e `powersave`
- **Intel Turbo Boost** - Liga/desliga turbo boost
- **Energy Performance Preference (EPP)** - 5 níveis de performance/economia
- **EPP Override** - Corrige mapeamento automático do botão Predator

### Interface
- **GUI GTK4** - Interface gráfica moderna com libadwaita em duas colunas
- **CLI completa** - Controle via linha de comando
- **Integração com nekro-sense** - Funciona em conjunto com o módulo kernel
- **Status em tempo real** - Monitoramento de fans, temperatura e CPU power

## Como Funciona

![Como funciona o Fan Aggressor](docs/how-it-works.png)

### Modo Híbrido (Recomendado)

1. Sistema fica no **modo AUTO** enquanto temperatura está baixa (< threshold engage)
2. Quando temperatura atinge o **threshold de engage** (padrão: 70°C):
   - Captura um **snapshot** do RPM atual dos fans (curva do fabricante)
   - Converte para duty cycle percentual (0-100%)
   - Ativa o offset
3. Aplica **curva do fabricante (snapshot) + offset** configurado
4. Mantém esse snapshot como base fixa enquanto o offset estiver ativo
5. Quando temperatura cai abaixo do **threshold de disengage** (padrão: 65°C), desativa offset e volta ao AUTO

**Conceito-chave**: O sistema **não substitui** a curva do fabricante. Ele apenas **adiciona** o offset configurado sobre a curva natural que o hardware já aplica.

### Exemplo Prático (Offset +10%)

No momento da ativação (60°C):
- RPM do CPU fan: 2500 RPM → ~33% duty cycle (base da curva do fabricante)
- RPM do GPU fan: 2100 RPM → ~28% duty cycle
- **Offset aplicado**: +10%
- **Fan final setado**: CPU 43%, GPU 38%

O snapshot permanece fixo até a temperatura cair abaixo do disengage ou variar significativamente.

### EPP Override para Botão Predator

O botão físico de energia do Predator possui 4 estágios, mas o `power-profiles-daemon` mapeia incorretamente o modo `balanced` para `balance_performance` ao invés de `balance_power`. O serviço `epp-override` corrige isso automaticamente:

| Estágio | Profile | EPP Padrão (errado) | EPP Corrigido |
|---------|---------|---------------------|---------------|
| 1 (ECO) | `low-power` | `power` | `power` ✓ |
| 2 (BALANCED) | `balanced` | `balance_performance` | **`balance_power`** |
| 3 (PERFORMANCE) | `balanced-performance` | `balance_performance` | `balance_performance` ✓ |
| 4 (TURBO) | `performance` | `performance` | `performance` ✓ |

### Power Profiles (GUI)

A GUI inclui 5 perfis pré-configurados que aplicam governor, turbo e EPP com um clique:

| Perfil | Governor | Turbo | EPP | Platform Profile | Uso |
|--------|----------|-------|-----|-----------------|-----|
| **Deep Sleep** | powersave | OFF | power | low-power | Economia extrema, CPU no mínimo absoluto |
| **Stealth Mode** | powersave | OFF | power | quiet | Silencioso, sem turbo, economia total |
| **Cruise Control** | powersave | ON | balance_power | balanced | Dia a dia, equilíbrio consumo/performance |
| **Boost Drive** | powersave | ON | balance_performance | balanced-performance | Produtividade, alta performance com eficiência |
| **Nitro Overdrive** | performance | ON | performance | performance | Gaming, benchmark, performance máxima |

O perfil ativo é indicado visualmente. Os perfis sincronizam com o botão físico do Predator e com mudanças individuais nos controles de governor/turbo/EPP. O Deep Sleep acessa o platform profile `low-power` que não é acessível pelo botão físico.

## Requisitos

- Linux com kernel 5.x+
- [nekro-sense](https://github.com/fredac100/nekro-sense) instalado e funcionando
- Python 3.8+
- GTK4 e libadwaita (para GUI)
- `intel_pstate` driver (para controles de CPU power)

## Instalação

### 1. Instalar nekro-sense (pré-requisito)

```bash
git clone https://github.com/fredac100/nekro-sense.git
cd nekro-sense
make
sudo make install
sudo modprobe nekro_sense
```

Verifique se o módulo carregou:
```bash
lsmod | grep nekro
```

### 2. Instalar Fan Aggressor

```bash
git clone https://github.com/fredac100/fan-control.git
cd fan-control
chmod +x install.sh
sudo ./install.sh
```

Isso instala:
- `/usr/local/bin/fan_aggressor` - CLI e daemon
- `/usr/local/bin/epp_override` - Correção de EPP do botão Predator
- `/usr/local/lib/fan-aggressor/` - Módulos Python (`fan_monitor.py`, `cpu_power.py`)
- `/etc/systemd/system/fan-aggressor.service` - Serviço do daemon
- `/etc/systemd/system/epp-override.service` - Serviço de correção EPP

### 3. Habilitar e Iniciar Serviços

```bash
# Habilitar controle de fans
sudo fan_aggressor enable

# Iniciar daemon
sudo systemctl enable --now fan-aggressor

# Correção de EPP (opcional, recomendado para botão Predator)
sudo systemctl enable --now epp-override
```

### 4. Verificar Funcionamento

```bash
# Ver status
sudo fan_aggressor status

# Ver logs em tempo real
journalctl -u fan-aggressor -f
```

### 5. Instalar GUI (Opcional)

```bash
./install_gui.sh
```

Isso instala o ícone e adiciona entrada no menu de aplicações.

## Uso

### Interface Gráfica

```bash
./fan_aggressor_gui.py
```

Ou procure "Fan Aggressor" no menu de aplicações.

A GUI possui **duas colunas**:
- **Esquerda**: Status, controle de fans, offsets e thresholds
- **Direita**: CPU Power Management (governor, turbo, EPP) e CPU Status (valores em tempo real)

### Linha de Comando

#### Ver status

```bash
fan_aggressor status
```

Mostra:
- Status do daemon (enabled/disabled)
- Modo (híbrido/curva fixa)
- Offsets configurados (CPU/GPU)
- Thresholds (engage/disengage)
- Duty atual via nekroctl
- Fan speeds (RPM e % estimado)
- Temperaturas (todas + máxima)
- CPU Power (governor, turbo boost, EPP)
- Cálculo híbrido (base do fabricante + offset = final)

#### Configurar offset

```bash
# Aumentar agressividade (+10% a +30% recomendado)
fan_aggressor set both +15

# CPU e GPU separados
fan_aggressor set cpu +20
fan_aggressor set gpu +10

# Reduzir ruído (cuidado com temperaturas!)
fan_aggressor set both -10

# Resetar ao padrão
fan_aggressor set both 0
```

**Nota**: Mudanças de offset são aplicadas imediatamente pelo daemon se estiver rodando.

#### Habilitar/Desabilitar

```bash
# Habilitar controle de fans
fan_aggressor enable

# Desabilitar (volta ao modo AUTO do hardware)
fan_aggressor disable
```

#### Alterar thresholds

Edite `/etc/fan-aggressor/config.json`:

```json
{
  "temp_threshold_engage": 60,
  "temp_threshold_disengage": 55
}
```

O daemon recarrega o config automaticamente a cada ciclo.

### Serviço Systemd

```bash
# Fan Aggressor
sudo systemctl start fan-aggressor
sudo systemctl enable fan-aggressor
journalctl -u fan-aggressor -f

# EPP Override (corrige botão Predator)
sudo systemctl start epp-override
sudo systemctl enable epp-override
journalctl -u epp-override -f
```

## Configuração

Arquivo: `/etc/fan-aggressor/config.json`

```json
{
  "cpu_fan_offset": 0,
  "gpu_fan_offset": 0,
  "enabled": true,
  "poll_interval": 1.0,
  "hybrid_mode": true,
  "temp_threshold_engage": 70,
  "temp_threshold_disengage": 65,
  "cpu_governor": "powersave",
  "cpu_turbo_enabled": true,
  "cpu_epp": "balance_performance",
  "cpu_platform_profile": "",
  "link_offsets": true,
  "nekroctl_path": null,
  "failsafe_mode": "auto"
}
```

**Importante**: O arquivo de config é recarregado automaticamente pelo daemon a cada ciclo (poll_interval). Não é necessário reiniciar o serviço após editar.

### Parâmetros de Fans

| Parâmetro | Descrição | Range |
|-----------|-----------|-------|
| `cpu_fan_offset` | Offset para CPU | -100 a +100 |
| `gpu_fan_offset` | Offset para GPU | -100 a +100 |
| `enabled` | Ativa/desativa o controle | true/false |
| `poll_interval` | Intervalo de atualização | segundos (padrão: 1.0) |
| `hybrid_mode` | Se true, usa thresholds; se false, controla sempre | true/false |
| `temp_threshold_engage` | Temperatura para ativar boost | °C (padrão: 70) |
| `temp_threshold_disengage` | Temperatura para voltar ao auto | °C (padrão: 65) |
| `nekroctl_path` | Caminho customizado para nekroctl | caminho absoluto ou `null` para auto-detect |
| `failsafe_mode` | Comportamento em falha de sensores | `auto` (aguarda) ou `max` (força 100%) |

**Sobre `nekroctl_path`**: Por padrão (`null`), o sistema busca `nekroctl.py` em:
1. Variável de ambiente `NEKROCTL`
2. `/home/fred/nekro-sense/tools/nekroctl.py`
3. `/usr/local/bin/nekroctl.py`, `/usr/local/bin/nekroctl`, `/usr/bin/nekroctl`
4. `/opt/nekro-sense/tools/nekroctl.py`

Defina um caminho absoluto apenas se estiver em local não-padrão.

**Sobre `failsafe_mode`**: Se sensores de temperatura falharem (retorno `None`, <0°C, >120°C):
- `auto` (padrão): aguarda até sensores voltarem, mantém estado anterior
- `max`: força fans a 100% como medida de segurança contra superaquecimento

### Parâmetros de CPU Power

| Parâmetro | Descrição | Valores |
|-----------|-----------|---------|
| `cpu_governor` | Governor do CPU | `powersave`, `performance` |
| `cpu_turbo_enabled` | Intel Turbo Boost | true/false |
| `cpu_epp` | Energy Performance Preference | `default`, `performance`, `balance_performance`, `balance_power`, `power` |

**Nota sobre EPP**: Com governor `performance`, o EPP é controlado automaticamente pelo driver e pode não aceitar mudanças manuais. Use governor `powersave` para controle total do EPP.

## Integração com Nekro-Sense

O Fan Aggressor funciona em conjunto com o nekro-sense:

- Usa `nekroctl.py` para controlar os fans via módulo kernel
- O GUI do nekro-sense detecta quando o aggressor está ativo
- Quando ativo, mostra o status do boost e desabilita controles manuais

## Arquitetura

```
fan_aggressor_gui.py  ──┐
                        ├──► fan_aggressor.py (daemon) ───► cpu_power.py
fan_aggressor (CLI)   ──┘           │                           │
                                    ▼                           ▼
                            nekroctl.py                  sysfs (cpufreq)
                                    │
                                    ▼
                          nekro-sense (kernel module)
                                    │
                                    ▼
                              Hardware (WMI)

epp_override.py ──► platform_profile → EPP sysfs
```

## Componentes

### fan_aggressor.py
Daemon principal que monitora temperaturas e controla ventiladores. Aplica curva dinâmica com offsets configuráveis. Também gerencia configurações de CPU power (governor, turbo, EPP).

### fan_aggressor_gui.py
Interface gráfica GTK4/Libadwaita com duas colunas:
- Controles de fans (offsets, thresholds, modo híbrido)
- CPU Power Management com status em tempo real

### cpu_power.py
Módulo para leitura/escrita de controles CPU via sysfs:
- Governor (`/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`)
- Turbo Boost (`/sys/devices/system/cpu/intel_pstate/no_turbo`)
- EPP (`/sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference`)

### epp_override.py
Daemon que monitora `/sys/firmware/acpi/platform_profile` e corrige o mapeamento EPP quando o botão físico do Predator é pressionado. Sobrescreve o comportamento padrão do `power-profiles-daemon` para garantir que o modo `balanced` use `balance_power` ao invés de `balance_performance`.

### fan_monitor.py
Módulo para leitura de fan speeds e temperaturas via hwmon (`/sys/class/hwmon`).

## Exemplos de Uso

### Gaming (mais resfriamento + performance)

```bash
fan_aggressor set both +20
fan_aggressor enable
# Via GUI: perfil "Nitro Overdrive"
```

### Trabalho silencioso (economia de energia)

```bash
fan_aggressor set both -5
fan_aggressor enable
# Via GUI: perfil "Stealth Mode"
```

### Balanced (padrão recomendado)

```bash
fan_aggressor set both 0
fan_aggressor enable
# Via GUI: perfil "Cruise Control"
```

### Desativar controle de fans temporariamente

```bash
fan_aggressor disable
```

Os fans voltam ao modo automático do sistema.

## Avisos

- Monitore as temperaturas ao usar offsets negativos
- O sistema pode atingir throttling se os fans forem muito lentos
- Em caso de superaquecimento, desabilite o aggressor com `fan_aggressor disable`
- Mudanças de CPU power requerem permissões de root (a GUI usa pkexec quando necessário)
- O `epp-override` só é necessário se você usa o botão físico do Predator e quer o mapeamento correto dos modos

## Logs

```bash
# Fan Aggressor
journalctl -u fan-aggressor -f

# EPP Override
journalctl -u epp-override -f

# Ambos
journalctl -u fan-aggressor -u epp-override -f
```

## Desinstalação

```bash
sudo systemctl stop fan-aggressor epp-override
sudo systemctl disable fan-aggressor epp-override
sudo rm /etc/systemd/system/fan-aggressor.service
sudo rm /etc/systemd/system/epp-override.service
sudo rm /usr/local/bin/fan_aggressor
sudo rm /usr/local/bin/epp_override
sudo rm -rf /usr/local/lib/fan-aggressor
sudo rm -rf /etc/fan-aggressor
sudo systemctl daemon-reload
```

## Troubleshooting

### Fans escalam até 100% no modo híbrido

Se os fans sobem gradualmente até 100% ao invés de manter o offset configurado, verifique:

1. **Versão do código**: Certifique-se de ter a versão mais recente (commit `7045999` ou posterior)
   ```bash
   cd /home/fred/fan-control
   git pull
   sudo ./install.sh
   sudo systemctl restart fan-aggressor
   ```

2. **Logs do daemon**: Verifique se o snapshot é capturado corretamente
   ```bash
   journalctl -u fan-aggressor -f
   ```

   Deve mostrar:
   ```
   [60°C] Offset ATIVADO (base snapshot: CPU 34%, GPU 35%)
   [60°C] Fans: CPU 44% (base 34% + 10%), GPU 45% (base 35% + 10%)
   ```

   **NÃO deve mostrar** "Snapshot atualizado" repetidamente — isso indica versão antiga com bug de feedback loop.

3. **Modo híbrido ativo**: Confirme no config.json:
   ```json
   "hybrid_mode": true
   ```

### EPP não muda
- Verifique se está usando governor `powersave` (com `performance`, o EPP é gerenciado pelo driver)
- Confira se tem permissões de root: `sudo python3 -c "from cpu_power import set_epp; print(set_epp('balance_power'))"`

### Botão Predator não altera EPP corretamente
- Verifique se o serviço `epp-override` está rodando: `systemctl status epp-override`
- Veja os logs: `journalctl -u epp-override -f`
- Pressione o botão e observe se o log mostra a correção

### Fans não respondem
- Verifique se o nekro-sense está carregado: `lsmod | grep nekro`
- Confira se o daemon está rodando: `systemctl status fan-aggressor`
- Verifique se nekroctl foi encontrado: `journalctl -u fan-aggressor | grep nekroctl`
- Teste manualmente: `sudo python3 /home/fred/nekro-sense/tools/nekroctl.py --fan1 50`
- Se nekroctl está em local não-padrão, configure `nekroctl_path` no config.json

### Sensores de temperatura não funcionam
- Verifique: `cat /sys/class/hwmon/hwmon*/name` (deve mostrar "acer" ou "coretemp")
- Se falhar constantemente, configure `failsafe_mode: "max"` para forçar fans a 100%

### Daemon não inicia após atualização
- O serviço systemd agora tem hardening de segurança
- Se houver conflitos de permissão, verifique os logs: `journalctl -u fan-aggressor -n 50`
- Paths permitidos: `/etc/fan-aggressor` (leitura/escrita) e `/var/run` (PID/state)

## Segurança

O serviço systemd inclui hardening:
- `NoNewPrivileges=true` - Previne escalação de privilégios
- `PrivateTmp=true` - Isola `/tmp` do sistema
- `ProtectSystem=full` - Sistema de arquivos read-only exceto paths explícitos
- `ReadWritePaths=/etc/fan-aggressor /var/run` - Apenas paths necessários são graváveis

Escrita de config é atômica (`.tmp` + `rename`) para prevenir corrupção em caso de falha.

## Licença

MIT
