# Manual de Arquitetura Técnica: Sistema Fan Aggressor

## 1. Introdução e Filosofia de Design do Sistema

No ecossistema de hardware de alto desempenho, o gerenciamento térmico é frequentemente uma "caixa-preta" regida por firmwares proprietários conservadores. O Fan Aggressor foi arquitetado como um **middleware lógico de precisão**, posicionado entre a leitura dos sensores e a escrita final nos registradores de controle. Sua filosofia de design não reside na substituição da lógica do fabricante, mas na introdução de um **"viés configurável"** sobre o duty cycle nativo. Esta abordagem preserva as salvaguardas críticas de hardware — como o thermal shutdown e as proteções de sobrecorrente — enquanto permite um refinamento cirúrgico da modulação por largura de pulso (PWM), garantindo que a segurança térmica e a personalização de performance coexistam em harmonia sistêmica.

## 2. Lógica de Cálculo e Modulação de Offset

A arquitetura adota uma abordagem **aditiva** em vez de absoluta. Ao contrário de ferramentas que forçam rotações estáticas, o Fan Aggressor intercepta a saída do firmware e aplica uma transformação matemática que respeita a dinâmica térmica original. O núcleo do sistema opera sob a equação fundamental:

```
Fan Final = Curva Nativa + Offset
```

Um diferencial arquitetural crítico é que os eixos térmicos da CPU e GPU possuem **offsets independentes**, permitindo um ajuste granular para cargas de trabalho assimétricas. Contudo, o sistema oferece suporte à função de **link**, sincronizando os offsets para simplificar o controle em cenários de estresse térmico global.

A modulação resulta em três estados operacionais:

- **Offset Positivo (+)**: Amplia a agressividade do resfriamento, elevando o teto térmico para overclocking ou regimes de alta carga, com o ônus do incremento na pressão sonora.
- **Offset Negativo (-)**: Prioriza a acústica e o silêncio operacional, ideal para ambientes controlados, aceitando um trade-off de temperaturas base mais elevadas.
- **Offset Zero (0%)**: Garante a transparência total do sistema, onde o Fan Aggressor atua em modo de observação passiva, devolvendo o controle integral ao firmware original.

> **Restrição de Registro**: Para mitigar falhas de endereçamento ou valores fora de escala, o sistema impõe um clamping rigoroso de **0% a 100%** antes da escrita no controlador, prevenindo estados de erro no controlador embarcado.

## 3. Modos de Operação e Mecanismos de Histerese

A instabilidade térmica, que gera o fenômeno de *fan hunting* (oscilação constante da rotação), é resolvida através de uma segmentação inteligente de estados operacionais e um ciclo de polling de 1 segundo para recálculo constante via feedback do firmware.

### Modo Híbrido (Padrão)

O Modo Híbrido utiliza uma lógica de **Latch (Retenção de Estado)** baseada na direção da mudança de temperatura:

- **Abaixo de 65°C** (Estado de Desengajamento): Operação 100% automática. O sistema ignora o offset para privilegiar a longevidade mecânica dos fans em baixas temperaturas.
- **Acima de 70°C** (Estado de Engajamento): Intervenção ativa. O offset é aplicado sobre o duty cycle lido em tempo real.
- **Zona de Histerese (65°C–70°C)**: Atua como uma janela de persistência. Se o sistema está em aquecimento e cruza os 65°C, ele permanece desengajado até atingir 70°C. Se está em resfriamento e desce para 66°C, ele permanece engajado. Esta *direção de transição* é o que elimina o comportamento errático dos fans em limiares críticos.

### Modo Curva Fixa

Neste modo, a lógica de histerese é suprimida. O offset é aplicado de forma persistente sobre a curva nativa, independentemente dos sensores de temperatura, permitindo um perfil de resfriamento constante.

## 4. Arquitetura de Backends e Abstração de Hardware

Dada a complexidade do ecossistema Linux, o Fan Aggressor implementa uma hierarquia de backends para garantir a persistência do controle. O sistema prioriza métodos de acesso direto ao hardware para minimizar a latência de escrita.

1. **EC (Embedded Controller)**: O backend de maior autoridade. Realiza a escrita direta nos registradores do controlador embarcado via mapeamento de memória ou portas I/O específicas através da interface `/sys/kernel/debug/ec`. A integração com o `nekroctl` permite um ajuste de duty cycle com precisão de nível de firmware.
2. **Nekro**: Camada de abstração intermediária que utiliza o utilitário `nekroctl` para gerenciar a comunicação com os drivers de kernel específicos do fabricante.
3. **PredatorSense (Interface sysfs)**: Método de contingência. Devido às limitações de hardware desta interface, o offset percentual é mapeado para modos discretos (Quiet, Auto, Normal, Performance, Turbo), convertendo valores contínuos em estados de operação pré-definidos.

## 5. Integração de Perfis de Energia (CPU Power Management)

A eficiência térmica é indissociável da gestão de consumo energético. O Fan Aggressor sincroniza o comportamento dos fans com a demanda de processamento através de cinco perfis estratégicos. Um daemon de **EPP Override** monitora o Botão Físico Predator para corrigir os mapeamentos de energia que o `power-profiles-daemon` padrão frequentemente interpreta de forma errônea neste hardware.

| Perfil | Governor | Turbo | EPP | Platform Profile |
|--------|----------|-------|-----|-----------------|
| **Deep Sleep** | powersave | OFF | power | low-power |
| **Stealth Mode** | powersave | OFF | power | quiet |
| **Cruise Control** | powersave | ON | balance_power | balanced |
| **Boost Drive** | powersave | ON | balance_performance | balanced-performance |
| **Nitro Overdrive** | performance | ON | performance | performance |

A correção automática de EPP e Governor garante que o hardware entregue a performance esperada no instante em que o botão físico é acionado, harmonizando instantaneamente o fornecimento de energia com a capacidade de dissipação configurada.

## 6. Conclusão Técnica e Considerações de Implementação

O Fan Aggressor transcende a funcionalidade de um simples controlador de ventilação; ele é uma ferramenta de precisão cirúrgica desenhada para administradores que demandam controle total sobre o silício. A robustez da arquitetura reside na inteligência da sua histerese e na segurança das travas lógicas de 0-100%.

Ao implementar este sistema, o administrador de hardware elimina a opacidade dos firmwares de fábrica sem comprometer a estabilidade operacional. O Fan Aggressor reafirma que a melhor defesa térmica não é a substituição da lógica original, mas o seu refinamento inteligente através de offsets calculados e integração profunda com a gestão de energia da CPU.
