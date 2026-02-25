# Identidad Visual UABCS
## Universidad Autónoma de Baja California Sur

> **Lema:** *"Sabiduría como Meta, Patria como Destino"*
> **Sitio oficial:** uabcs.mx

---

## Colores Institucionales

Los colores del escudo de la UABCS derivan de su tradición institucional y del paisaje bajacaliforniano: el azul del Mar de Cortés, el amarillo del desierto y el sol, y el rojo que evoca la tierra.

### Paleta principal

| Nombre             | Hex       | RGB                | Uso principal                                      |
|--------------------|-----------|--------------------|----------------------------------------------------|
| **Azul UABCS**     | `#009FD4` | rgb(0, 159, 212)   | Fondo de slides, encabezados, elementos primarios  |
| **Amarillo UABCS** | `#FFD100` | rgb(255, 209, 0)   | Acentos, highlights, botones de llamada a acción   |
| **Rojo UABCS**     | `#CC1E1E` | rgb(204, 30, 30)   | Énfasis crítico, alertas, texto del logotipo       |

### Paleta extendida (derivados institucionales)

| Nombre                | Hex       | RGB                | Uso                                                |
|-----------------------|-----------|--------------------|----------------------------------------------------|
| **Azul marino**       | `#00497E` | rgb(0, 73, 126)    | Fondos oscuros, slides de portada y cierre         |
| **Azul profundo**     | `#002147` | rgb(0, 33, 71)     | Fondo de código, contraste máximo                  |
| **Azul suave**        | `#E3F4FB` | rgb(227, 244, 251) | Fondos de diapositivas claras, hover de tablas     |
| **Amarillo suave**    | `#FFF8CC` | rgb(255, 248, 204) | Cajas de advertencia / tips                        |
| **Rojo suave**        | `#FDECEC` | rgb(253, 236, 236) | Fondos de cajas de error / cuidado                 |
| **Gris institucional**| `#4A5568` | rgb(74, 85, 104)   | Texto secundario, pies de página                   |
| **Blanco**            | `#FFFFFF` | rgb(255, 255, 255) | Texto sobre azules oscuros, fondos de slides       |

---

## Tipografía Recomendada

### Para documentos y presentaciones (disponible en Office)

| Uso              | Fuente                | Tamaño sugerido | Peso     |
|------------------|-----------------------|-----------------|----------|
| Título principal | **Calibri / Georgia** | 40–56 pt        | Bold     |
| Subtítulo        | Calibri               | 24–32 pt        | Regular  |
| Encabezado H1    | **Arial / Calibri**   | 24–28 pt        | Bold     |
| Encabezado H2    | Arial                 | 20–24 pt        | Bold     |
| Cuerpo           | Arial / Calibri       | 12–14 pt        | Regular  |
| Código           | **Courier New / Consolas** | 11–13 pt   | Regular  |
| Pie de página    | Arial                 | 10–11 pt        | Regular  |

---

## Uso del Logotipo

- El logotipo oficial es el **escudo universitario** con fondo circular azul, franja amarilla, libro abierto y cacto sobre montañas.
- **No modificar** los colores del escudo ni añadir efectos (sombras, biselados, transparencias).
- Usar sobre fondos blancos, azul marino `#002147` o azul UABCS `#009FD4`.
- **Versión negativa** (blanco): solo sobre fondos azul marino o azul UABCS.
- Respetar zona de protección: mínimo igual al ancho de la letra "U" del logotipo.

---

## Aplicación en Presentaciones (PowerPoint / Google Slides)

### Estructura "sándwich" recomendada

```
Diapositiva de portada  → fondo azul marino  (#002147)
Diapositivas de contenido → fondo blanco o azul suave (#E3F4FB)
Diapositiva de cierre   → fondo azul marino  (#002147)
```

### Barra superior de contenido

```
color de fondo: #009FD4  (Azul UABCS)
texto sobre barra: #FFFFFF (Blanco)
```

### Elementos de acento

```
Llamadas a acción / highlights: #FFD100  (Amarillo UABCS)
Alertas / advertencias:         #CC1E1E  (Rojo UABCS)
```

### Código en presentaciones

```
Fondo del bloque de código:  #002147  (Azul profundo)
Texto del código:            #90D4F0  (Azul claro / cian)
Borde del bloque:            #009FD4  (Azul UABCS)
Salida del programa:         #A8D8EA  (Azul muy claro)
```

---

## Variables para scripts de automatización

### JavaScript / PptxGenJS

```javascript
const UABCS = {
  azul:          '009FD4',   // Azul institucional
  amarillo:      'FFD100',   // Amarillo institucional
  rojo:          'CC1E1E',   // Rojo institucional
  azulMarino:    '00497E',   // Fondos oscuros secundarios
  azulProfundo:  '002147',   // Fondos de portada / código
  azulSuave:     'E3F4FB',   // Fondos de diapositivas
  amarilloSuave: 'FFF8CC',   // Cajas de tips
  rojoSuave:     'FDECEC',   // Cajas de advertencia
  gris:          '4A5568',   // Texto secundario
  blanco:        'FFFFFF',
  negro:         '1A1A1A',
};
```

### Python / docx (python-docx / docx-js)

```python
UABCS = {
    "azul":          "009FD4",
    "amarillo":      "FFD100",
    "rojo":          "CC1E1E",
    "azul_marino":   "00497E",
    "azul_profundo": "002147",
    "azul_suave":    "E3F4FB",
    "amarillo_suave":"FFF8CC",
    "rojo_suave":    "FDECEC",
    "gris":          "4A5568",
    "blanco":        "FFFFFF",
    "negro":         "1A1A1A",
}
```

---

## Contexto de uso por tipo de documento

| Documento             | Fondo de encabezado | Acento   | Texto principal |
|-----------------------|---------------------|----------|-----------------|
| Presentación clase    | `#009FD4`           | `#FFD100`| `#002147`       |
| Actividad práctica    | `#002147`           | `#009FD4`| `#1A1A1A`       |
| Examen / evaluación   | `#00497E`           | `#FFD100`| `#1A1A1A`       |
| Reporte de proyecto   | `#009FD4`           | `#CC1E1E`| `#1A1A1A`       |
| Carta / oficio        | `#002147`           | `#009FD4`| `#1A1A1A`       |

---

*UABCS — Área de Conocimiento de Ciencias del Mar y de la Tierra*
*Febrero 2026*
