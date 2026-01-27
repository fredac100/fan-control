# Fan Aggressor

Controle dinâmico de ventiladores para notebooks Acer no Linux, com offset configurável sobre a curva de temperatura.

## Compatibilidade

Este projeto funciona **exclusivamente** com notebooks Acer que possuem interface WMI para controle de fans:

- **Acer Predator** (Helios, Triton, etc.)
- **Acer Nitro** (Nitro 5, Nitro 7, etc.)

Requer o módulo kernel [nekro-sense](https://github.com/fredac100/nekro-sense) instalado e funcionando.

## Funcionalidades

- **Curva dinâmica de temperatura** - Velocidade dos fans varia conforme a temperatura
- **Offset configurável** - Adiciona ou remove porcentagem sobre a curva base
- **Modo Híbrido** - Ativa boost apenas quando temperatura atinge threshold
- **GUI GTK4** - Interface gráfica moderna com libadwaita
- **CLI completa** - Controle via linha de comando
- **Integração com nekro-sense** - Funciona em conjunto com o módulo kernel

## Como Funciona

### Modo Híbrido (Recomendado)

1. Sistema fica no **modo AUTO** enquanto temperatura está baixa
2. Quando temperatura atinge o **threshold de engage** (ex: 60°C), ativa o boost
3. Aplica **curva dinâmica + offset** configurado
4. Quando temperatura cai abaixo do **threshold de disengage** (ex: 55°C), volta ao AUTO

### Curva de Temperatura Base

| Temperatura | Velocidade Base |
|-------------|-----------------|
| < 50°C      | 0%              |
| 50-60°C     | 0-20%           |
| 60-70°C     | 20-45%          |
| 70-80°C     | 45-75%          |
| 80-90°C     | 75-100%         |
| > 90°C      | 100%            |

### Exemplo com Offset +15%

| Temperatura | Base | + Offset | Final |
|-------------|------|----------|-------|
| 55°C        | 10%  | +15%     | 25%   |
| 65°C        | 32%  | +15%     | 47%   |
| 75°C        | 60%  | +15%     | 75%   |

## Requisitos

- Linux com kernel 5.x+
- [nekro-sense](https://github.com/fredac100/nekro-sense) instalado e funcionando
- Python 3.8+
- GTK4 e libadwaita (para GUI)

## Instalação

```bash
git clone https://github.com/fredac100/fan-control.git
cd fan-control
chmod +x install.sh
sudo ./install.sh
```

### Instalar GUI

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

### Linha de Comando

#### Ver status

```bash
fan_aggressor status
```

#### Configurar offset

```bash
# Aumentar agressividade
fan_aggressor set both +15

# CPU e GPU separados
fan_aggressor set cpu +20
fan_aggressor set gpu +10

# Reduzir ruído (cuidado com temperaturas!)
fan_aggressor set both -10
```

#### Habilitar/Desabilitar

```bash
fan_aggressor enable
fan_aggressor disable
```

### Serviço Systemd

```bash
# Iniciar
sudo systemctl start fan-aggressor

# Habilitar no boot
sudo systemctl enable fan-aggressor

# Ver logs
journalctl -u fan-aggressor -f
```

## Configuração

Arquivo: `/etc/fan-aggressor/config.json`

```json
{
  "cpu_fan_offset": 15,
  "gpu_fan_offset": 15,
  "enabled": true,
  "poll_interval": 1.0,
  "hybrid_mode": true,
  "temp_threshold_engage": 60,
  "temp_threshold_disengage": 55
}
```

| Parâmetro | Descrição |
|-----------|-----------|
| `cpu_fan_offset` | Offset para CPU (-100 a +100) |
| `gpu_fan_offset` | Offset para GPU (-100 a +100) |
| `enabled` | Ativa/desativa o controle |
| `poll_interval` | Intervalo de atualização em segundos |
| `hybrid_mode` | Se true, usa thresholds; se false, controla sempre |
| `temp_threshold_engage` | Temperatura para ativar boost |
| `temp_threshold_disengage` | Temperatura para voltar ao auto |

## Integração com Nekro-Sense

O Fan Aggressor funciona em conjunto com o nekro-sense:

- Usa `nekroctl` para controlar os fans via módulo kernel
- O GUI do nekro-sense detecta quando o aggressor está ativo
- Quando ativo, mostra o status do boost e desabilita controles manuais

## Arquitetura

```
fan_aggressor_gui.py  ──┐
                        ├──► fan_aggressor.py (daemon)
fan_aggressor (CLI)   ──┘           │
                                    ▼
                            nekroctl.py
                                    │
                                    ▼
                          nekro-sense (kernel module)
                                    │
                                    ▼
                              Hardware (WMI)
```

## Exemplos de Uso

### Gaming (mais resfriamento)

```bash
fan_aggressor set both +20
fan_aggressor enable
sudo systemctl restart fan-aggressor
```

### Trabalho silencioso

```bash
fan_aggressor set both -5
fan_aggressor enable
sudo systemctl restart fan-aggressor
```

### Desativar temporariamente

```bash
fan_aggressor disable
```

Os fans voltam ao modo automático do sistema.

## Avisos

- Monitore as temperaturas ao usar offsets negativos
- O sistema pode atingir throttling se os fans forem muito lentos
- Em caso de superaquecimento, desabilite o aggressor

## Desinstalação

```bash
sudo systemctl stop fan-aggressor
sudo systemctl disable fan-aggressor
sudo rm /etc/systemd/system/fan-aggressor.service
sudo rm /usr/local/bin/fan_aggressor
sudo rm -rf /etc/fan-aggressor
sudo systemctl daemon-reload
```

## Licença

MIT
