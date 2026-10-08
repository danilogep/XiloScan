# Frontend

> Parte da documentação do [XiloScan](../README.md).

## Etapa 3 — Frontend

```bash
cd frontend && npm install && npm run dev
```

- `types/xiloscan.ts` — `WoodSpecies`, `AnatomicalFeatures`, `ComparisonResult` e os
  códigos anatômicos como **union types literais**: valor inválido quebra no `tsc`,
  não em runtime na frente do usuário.
- `CaptureUploader` — guia SVG que desenha o corte de 85% do backend, régua de escala
  (~2 cm), `capture="environment"`, drag-and-drop, revogação de object URLs e
  checagem de qualidade antes de identificar.
- `ImageCompareSlider` — cortina com pointer events (mouse/toque/caneta), `role="slider"`
  com setas, Shift+setas e Home/End. Acessível de teclado, não só arrastável.
- `ConfidenceCard` — medidor SVG + **decomposição visual × atributos**. O número
  sozinho engana: 87% pode vir de match visual forte contra atributos divergentes.
- `FeatureDiffList` — **três** estados, nunca dois: coincidente, divergente e
  não informado. Ausência de dado não pode ser lida como discordância.
- `AttributeFilterPanel` — gerado a partir de `/taxonomy`; nada hard-coded.
  Categorias dependentes (parênquima apotraqueal/paratraqueal) só aparecem quando
  a categoria-pai as habilita.

---
