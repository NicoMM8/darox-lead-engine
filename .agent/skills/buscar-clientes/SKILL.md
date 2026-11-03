---
name: buscar-clientes
description: Saca todos los negocios de un sector en una ciudad desde Google Maps (a través de treg), entra en la web de cada uno a por su correo y lo deja en un CSV para Excel o Google Sheets, con nombre, tipo, dirección, teléfono, web, correo, nota y reseñas. Úsala cuando digan "búscame todas las clínicas dentales de Valencia", "sácame los gimnasios de mi ciudad", "quiero una lista de negocios", "leads de...", "clientes potenciales en..." o algo parecido.
---

# Buscar clientes

Quien te usa quiere una lista de negocios a los que ofrecer lo suyo. Casi nunca ha usado
Claude Code. Háblale claro, con frases cortas y sin tecnicismos. **Nunca le pidas que
escriba un comando: los ejecutas tú.**

- **Carpeta de la skill**: la de este SKILL.md (el sistema te la da al cargarla como
  "Base directory"). El script es `<skill>/scripts/buscar-clientes.mjs`. Ejecútalo con
  `node`.
- **Resultados**: una carpeta por búsqueda, `clientes/<negocio>-<ciudad>` dentro de la
  carpeta en la que está abierto Claude Code. Pásala siempre con `--carpeta`.
- **Cómo funciona**: busca la ciudad en el mapa, la divide en zonas de 1,7 km, busca el
  sector en Google Maps zona a zona (cada búsqueda trae 20 negocios y pasa de página donde
  hay más), quita duplicados y lo que cae fuera de la ciudad, entra en cada web a por el
  correo y lo exporta. Cada búsqueda en Maps cuesta 0,00015 $ del saldo de treg; las que
  fallan no se cobran y los correos no cuestan nada.

## 1. Preparar el ordenador (solo la primera vez)

Ejecuta `node <skill>/scripts/buscar-clientes.mjs comprobar`. Dice `OK` o `FALTA` para cada cosa.

**Falta node** (o no responde): dile que vas a instalarlo y hazlo.
- Windows: `winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements`.
  Si esta sesión aún no lo ve, búscalo en `C:\Program Files\nodejs\node.exe`.
- Mac con Homebrew (`brew --version` responde): `brew install node`.
- Mac sin Homebrew: que descargue el instalador "LTS" de https://nodejs.org, le dé doble
  clic y siga los pasos. Después sigue tú.

**Falta treg** (no hay llave o la cuenta no tiene equipo): lee https://treg.to/llms.txt y
sigue sus instrucciones para un agente local: instalar treg, entrar con su correo (le llega
un código de 6 cifras que te tiene que dictar) y, si no tiene equipo, crearlo. Al crear el
equipo treg regala 1 $ una vez: da para miles de búsquedas. La llave queda guardada en
`~/.treg/config.json` y el script la lee de ahí. Nunca le pidas que te pegue la llave en el
chat ni la escribas en ningún fichero.

Vuelve a ejecutar `comprobar` hasta que todo diga `OK`.

## 2. Entender qué busca

Necesitas dos cosas: **qué negocios** (en singular y como los buscaría en Google Maps:
"clínica dental", "gimnasio", "inmobiliaria") y **en qué ciudad**. Si falta una, pregúntala.
Si la ciudad puede estar en varios países, pregunta cuál.

Una búsqueda es una ciudad. Para una provincia o una comarca, hazlas ciudad por ciudad.

## 3. Estimar y pedir permiso (no se gasta nada)

```
node <skill>/scripts/buscar-clientes.mjs estimar --negocio "<negocio>" --ciudad "<ciudad>" --carpeta "clientes/<negocio>-<ciudad>"
```

Añade `--pais <código>` (es, mx, co, ar…) si hace falta. El script enseña los municipios que
encuentra con ese nombre y elige el primero; si no es el bueno, repite con `--candidato N`.

Cuéntale en un mensaje corto: el lugar que vas a recorrer, cuántas zonas, **lo que costará
como mucho** y su saldo. Normalmente cuesta bastante menos que ese máximo. **No sigas sin
su sí.** Si el coste máximo supera su saldo, díselo antes.

## 4. Buscar

```
node <skill>/scripts/buscar-clientes.mjs buscar --carpeta "clientes/<negocio>-<ciudad>"
```

Tarda de uno a varios minutos según el tamaño de la ciudad: avísale y deja que corra. Va
diciendo cuántas búsquedas lleva, cuántos negocios y cuánto ha gastado. Nunca gasta más del
máximo que aprobó.

- `SIN SALDO`: lo encontrado está guardado. Puede recargar en treg.to (Team → Billing) y
  se repite la búsqueda.
- `PARADA: treg rechaza la llave`: vuelve al paso 1.

## 5. Quedarse con su sector

Google Maps mezcla negocios parecidos (al buscar fisioterapeutas salen también osteópatas o
centros médicos). Ejecuta:

```
node <skill>/scripts/buscar-clientes.mjs tipos --carpeta "clientes/<negocio>-<ciudad>"
```

Enseña los tipos que aparecen y cuántos hay de cada uno, y marca `ENTRA` o `fuera` según la
palabra buscada. Decide tú lo evidente. Pregúntale solo lo dudoso, en una frase ("¿cuento
también los osteópatas?"). Luego:

```
node <skill>/scripts/buscar-clientes.mjs filtrar --carpeta "clientes/<negocio>-<ciudad>" [--tipos "fisioterap|osteop"]
```

Sin `--tipos` se queda con lo marcado `ENTRA` y con los negocios que llevan la palabra en
el nombre. Con `--tipos`, con los tipos que casen con esa expresión (sin tildes). `--todos` se queda con todo y `--con-alrededores` añade los
negocios de los pueblos de al lado. Se puede repetir las veces que haga falta: no gasta nada.

## 6. Sacar los correos (gratis)

```
node <skill>/scripts/buscar-clientes.mjs correos --carpeta "clientes/<negocio>-<ciudad>"
```

Entra en la web de cada negocio (portada y páginas de contacto o aviso legal) y se queda
con su correo. Desecha los de ejemplo de las plantillas. No todas las webs lo publican: es
normal que salga correo para la mitad, más o menos.

## 7. Entregar

```
node <skill>/scripts/buscar-clientes.mjs csv --carpeta "clientes/<negocio>-<ciudad>"
```

Ábrele la carpeta y cuéntale, en tres líneas:
- dónde está el CSV (se abre con Excel o Google Sheets; va ordenado por número de reseñas);
- cuántos negocios hay y cuántos con teléfono, web y correo;
- cuánto ha costado y cuánto ha tardado.

Las columnas: nombre, tipo, dirección, teléfono, web, correo, otros correos, nota, reseñas,
enlace a Google Maps y coordenadas.

## Reglas

- **Solo hace la lista.** No escribe ni envía nada a nadie. Si te pide mandar un correo a
  todos de golpe, no lo hagas: recomiéndale escribir a cada negocio con un mensaje pensado
  para él, empezando por los que más encajan, y respetar a quien pida que no le escriba.
  Antes de mandar correos comerciales que nadie ha pedido tiene que mirar lo que exige la
  ley de su país (en España, la LSSI pide permiso previo para el correo comercial): llamar
  o presentarse suele ser mejor primer paso.
- No repitas una búsqueda que ya está hecha sin preguntarle: cuesta saldo. Para cambiar el
  filtro o volver a sacar el CSV no hace falta buscar otra vez.
- No inventes cifras: todo lo que le cuentes sale de lo que imprime el script.
- La llave de treg no se enseña ni se copia a ningún sitio.

## Si algo falla

- `NO ENCONTRADA`: prueba con el nombre oficial del municipio o añade la provincia
  ("Elche, Alicante").
- Una zona enorme (aviso al estimar): mejor una ciudad concreta, o `--paso 2.5` para menos
  zonas (sale más barato y algo menos completo).
- Pocos resultados con una palabra muy rara: prueba con cómo lo llama Google Maps
  ("dentista" en vez de "odontólogo").
