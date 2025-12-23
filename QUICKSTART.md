# Fan Aggressor - Guia de Início Rápido

## Instalação em 3 Passos

### 1. Instalar a aplicação

```bash
cd /home/fred/fan-control
sudo ./install.sh
```

### 2. Configurar o offset desejado

Exemplo para aumentar 10% em ambos os ventiladores:

```bash
fan_aggressor set both +10
fan_aggressor enable
```

### 3. Iniciar o serviço

```bash
sudo systemctl start fan-aggressor
sudo systemctl enable fan-aggressor
```

## Comandos Úteis

### Ver status e velocidades atuais

```bash
fan_aggressor status
```

### Configurar offsets diferentes para CPU e GPU

```bash
fan_aggressor set cpu +15
fan_aggressor set gpu +20
```

### Ver logs do serviço

```bash
sudo journalctl -u fan-aggressor -f
```

### Parar o serviço

```bash
sudo systemctl stop fan-aggressor
```

## Cenários Comuns

### Notebook esquentando durante trabalho pesado

```bash
fan_aggressor set both +20
fan_aggressor enable
sudo systemctl restart fan-aggressor
```

### Gaming (GPU mais agressiva)

```bash
fan_aggressor set cpu +10
fan_aggressor set gpu +25
fan_aggressor enable
sudo systemctl restart fan-aggressor
```

### Trabalho silencioso (atenção às temperaturas!)

```bash
fan_aggressor set both -5
fan_aggressor enable
sudo systemctl restart fan-aggressor
```

Sempre monitore as temperaturas com `fan_aggressor status`!

### Desabilitar temporariamente

```bash
fan_aggressor disable
```

Para reabilitar:

```bash
fan_aggressor enable
```

## Verificação

Após iniciar o serviço, verifique se está funcionando:

```bash
fan_aggressor status
sudo journalctl -u fan-aggressor -n 20
```

## Troubleshooting

### Erro "EC não disponível"

Execute:

```bash
sudo modprobe ec_sys write_support=1
sudo systemctl restart fan-aggressor
```

### Serviço não inicia

Verifique os logs:

```bash
sudo journalctl -u fan-aggressor -n 50 --no-pager
```

### Fans não respondem

1. Verifique se o offset está configurado:
   ```bash
   fan_aggressor status
   ```

2. Verifique se o serviço está rodando:
   ```bash
   sudo systemctl status fan-aggressor
   ```

3. Reinicie o serviço:
   ```bash
   sudo systemctl restart fan-aggressor
   ```

## Monitoramento

Para monitorar continuamente velocidades e temperaturas:

```bash
watch -n 2 fan_aggressor status
```

## Valores Recomendados

- **Conservador**: +5% a +10%
- **Moderado**: +10% a +20%
- **Agressivo**: +20% a +30%
- **Silencioso**: -5% a -10% (monitore temperaturas!)

Valores acima de +30% ou abaixo de -15% não são recomendados.
