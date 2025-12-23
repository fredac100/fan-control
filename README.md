# Fan Aggressor

Aplicação para controlar a agressividade dos ventiladores de notebooks Acer no Linux.

## Funcionalidades

- Controle de offset de velocidade para CPU e GPU fans
- Mantém a variação dinâmica do controle automático
- Adiciona ou remove porcentagem de potência
- Interface CLI simples
- Serviço systemd para execução automática
- Suporte a controle via Embedded Controller (EC)

## Como Funciona

A aplicação monitora continuamente a velocidade dos ventiladores e aplica um offset configurável. Por exemplo:

- Se o sistema define o fan em 50% e você configurou +10%:
  - O fan rodará a 60%
- Se o sistema reduz para 30% e você tem +10%:
  - O fan rodará a 40%

Isso mantém a curva de ventilação dinâmica do fabricante, mas com mais (ou menos) agressividade.

## Requisitos

- Linux com kernel 3.17+
- lm-sensors instalado
- Módulo kernel ec_sys
- Permissões root para controle de hardware

## Instalação

```bash
cd /home/fred/fan-control
chmod +x install.sh
sudo ./install.sh
```

## Uso Básico

### Ver status atual

```bash
fan_aggressor status
```

### Configurar offset

```bash
fan_aggressor set cpu +10
fan_aggressor set gpu +15
fan_aggressor set both +10
```

Valores válidos: -100 a +100 (porcentagem)

### Habilitar/Desabilitar

```bash
fan_aggressor enable
fan_aggressor disable
```

### Iniciar serviço

```bash
sudo systemctl start fan-aggressor
sudo systemctl enable fan-aggressor
```

### Ver logs

```bash
journalctl -u fan-aggressor -f
```

## Exemplos de Uso

### Notebook esquentando muito

```bash
fan_aggressor set both +20
fan_aggressor enable
sudo systemctl start fan-aggressor
```

### Reduzir ruído (cuidado!)

```bash
fan_aggressor set both -10
fan_aggressor enable
sudo systemctl start fan-aggressor
```

Monitore as temperaturas!

### Gaming (mais agressivo)

```bash
fan_aggressor set cpu +15
fan_aggressor set gpu +25
fan_aggressor enable
sudo systemctl start fan-aggressor
```

## Arquitetura Técnica

A aplicação utiliza três métodos de controle:

1. **Leitura via hwmon**: Lê velocidades atuais dos fans através do driver acer-wmi
2. **Controle via EC**: Escreve diretamente no Embedded Controller via `/sys/kernel/debug/ec`
3. **Cálculo de duty cycle**: Converte RPM em porcentagem e aplica offset

### Offsets do EC (Acer)

- `0x03`: Fan mode control
- `0x71`: CPU fan duty cycle
- `0x75`: GPU fan duty cycle

## Avisos Importantes

- O controle inadequado de ventiladores pode causar superaquecimento
- Monitore as temperaturas ao usar offsets negativos
- Em caso de dúvida, use offsets conservadores (+5% a +10%)
- O sistema pode sobrepor o controle manual em situações críticas

## Desinstalação

```bash
sudo systemctl stop fan-aggressor
sudo systemctl disable fan-aggressor
sudo rm /etc/systemd/system/fan-aggressor.service
sudo rm /usr/local/bin/fan_aggressor
sudo systemctl daemon-reload
```

## Fontes e Referências

- [Fan speed control - ArchWiki](https://wiki.archlinux.org/title/Fan_speed_control)
- [Controlling Fan Speed in Linux | Baeldung](https://www.baeldung.com/linux/control-fan-speed)
- [GitHub - PXDiv/Div-Acer-Manager-Fan-Controls](https://github.com/PXDiv/Div-Acer-Manager-Fan-Controls)
- [GitHub - F0rth/acer_ec](https://github.com/F0rth/acer_ec)
- [platform/x86: acer-wmi: Add fan control support [LWN.net]](https://lwn.net/Articles/1010222/)

## Licença

MIT
