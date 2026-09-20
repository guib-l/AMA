# Format des fichiers `doc.json`

Chaque logiciel supporté possède un paquet `amac/assets/<logiciel>/`, nommé d'après le
logiciel en minuscules (`dftbplus`, `demonnano`), contenant un
`doc.json`. Ce fichier est la **description déclarative** de ce que le logiciel sait faire
et de la manière dont son fichier d'entrée s'écrit. Il est consommé par le composer
(`amac/parameter/composer.py`) pour générer l'input et par le validateur pour vérifier les
paramètres utilisateur. Un logiciel sans `doc.json` ne peut pas être validé : `AMAC`
refuse alors `validate="strict"` et avertit en `"warn"`.

## Structure générale

```jsonc
{
  "SOFTWARE": "DFTBP",          // nom canonique (cf. amac.engine.registry)
  "VERSION": "25.1",            // version de la documentation utilisée
  "SYNTAX": "TREE",             // famille syntaxique de l'input (voir plus bas)
  "EXECUTION": ["FILEIO"],      // FILEIO et/ou INPROCESS
  "INPUT": { ... },             // nom du fichier d'entrée, format géométrique, en-têtes
  "MODULES": { ... },           // COMMENT le calcul est utilisé (run type)
  "METHODS": { ... },           // QUEL calcul est fait (hamiltonien / niveau de théorie)
  "PARAMETERS": { ... },        // options générales (base, SCF, solvant, sorties, ...)
  "OUTPUT": { ... }             // fichiers produits et grandeurs récupérables
}
```

### `SYNTAX` — les cinq familles

| Valeur | Logiciels | Forme de l'input |
|---|---|---|
| `KEYWORD_BLOCK` | ORCA, Gaussian | ligne de mots-clés (`!` / `#p`) + blocs (`%bloc … end`) |
| `TREE` | DFTB+ | arbre hiérarchique HSD (`Bloc = Méthode { … }`) |
| `NAMELIST` | Quantum Espresso | namelists Fortran `&SYSTEM … /` + cartes |
| `FLAT` | Abinit | `variable valeur`, un niveau |
| `API` | pySCF, GPAW | pas de fichier : appels Python |

## Les trois niveaux

### `MODULES` — comment le calcul est utilisé

Un module est un *run type* : point simple, optimisation de géométrie, dynamique,
Hessienne, NEB, scan… Un module est **exclusif** des autres sauf mention contraire
(`CHAINABLE`).

```jsonc
"GEOMETRY_OPTIMISATION": {
  "KEYWORD": "Opt",                    // ce qui est écrit dans l'input
  "ALIASES": ["OPT", "Optimisation"],  // synonymes acceptés côté utilisateur
  "TARGET": "SIMPLE_INPUT",            // où l'écrire : SIMPLE_INPUT, ou chemin ["Driver"]
  "PERIODIC": "BOTH",                  // MOLECULE | PERIODIC | BOTH
  "REQUIRES": [],                      // autres nœuds nécessaires
  "EXCLUDE_IF": [],
  "ARGUMENTS": { ... },                // options propres au module
  "DESCRIPTION": "..."
}
```

### `METHODS` — quel calcul est fait

Arbre à deux niveaux : *famille* (`HF`, `DFT`, `MP2`, `CC`, `MULTIREFERENCE`,
`SEMIEMPIRICAL`, `TIGHT_BINDING`…) puis *variantes* (fonctionnelles, ordres, …).

```jsonc
"DFT": {
  "KEYWORD": null,                     // la famille elle-même n'écrit rien
  "VARIANTS": {
    "B3LYP": { "KEYWORD": "B3LYP", "CLASS": "HYBRID_GGA", "EXX": 0.20 }
  },
  "ARGUMENTS": { ... }                 // options communes à la famille
}
```

### `PARAMETERS` — options générales

Reprend le vocabulaire déjà en place (`TYPE`, `DEFAULT`, `MANDATORY`, `MANDATORY_IF`,
`EXCLUDE_IF`, `RANGE`, `ARGUMENTS`, `FORMAT`, `DESCRIPTION`) en y ajoutant `PATH`,
`VALUES`, `UNIT`, `ALIASES`, ainsi que `VARIANTS`, `COMPANION` et `COMMON_ARGUMENTS`
(voir « Variantes, `SETS`, `COMPANION` et `COMMON_ARGUMENTS` »).

## Vocabulaire commun à tous les nœuds

| Clé | Sens |
|---|---|
| `TYPE` | `FLAG`, `INTEGER`, `REAL`, `STRING`, `CHOICE`, `LIST`, `TABLE`, `INLINE`, `BLOCK`, `TREE` |
| `DEFAULT` | valeur par défaut du logiciel (`null` = non écrit si non demandé) |
| `VALUES` | énumération des valeurs admises (pour `CHOICE`) |
| `RANGE` | `[min, max]` pour `INTEGER` / `REAL` |
| `UNIT` | unité physique attendue (`energy`, `length`, `force`, `time`, `pressure`) |
| `PATH` | localisation dans l'input : `["Hamiltonian","DFTB","SCC"]` ou `["%scf","MaxIter"]` |
| `MANDATORY` | booléen |
| `MANDATORY_IF` | liste de `{ "PATH": [...], "VALUE": ... }` |
| `EXCLUDE_IF` | idem, mais rend le nœud interdit |
| `ARGUMENTS` | sous-nœuds (récursif) |
| `VARIANTS` | variantes d'une méthode, d'un module ou d'une option |
| `SETS` | dans une variante : valeurs imposées à des options quand elle est choisie |
| `COMPANION` | dans une entrée de `PARAMETERS` : paramètres associés |
| `COMMON_ARGUMENTS` | dans un `CHOICE` : arguments valables pour tous les choix |
| `CONDITION` | texte libre documentaire, non interprété |
| `FORMAT` | rendu textuel (voir ci-dessous) |
| `ALIASES` | synonymes acceptés en entrée utilisateur |
| `DESCRIPTION` | texte court issu de la documentation officielle |
| `CANONICAL` | entrée du catalogue canonique (voir « Lien avec le catalogue ») |

### `FORMAT`

Les conventions d'écriture sont déclarées une fois pour toutes dans
`INPUT.FORMAT_DEFAULTS`, et surchargées nœud par nœud si nécessaire :

```jsonc
"FORMAT": {
  "INLINE": true,        // écrit sur la ligne de mots-clés
  "NEWLINE": false,
  "SEPARATOR": " ",
  "ASSIGN": " = ",       // séparateur clé/valeur
  "OPEN": "{",           // ouverture de bloc
  "CLOSE": "}",
  "PADDING": "  ",
  "UPPERCASE": false,
  "LOWERCASE": false,
  "BOOLEAN": ["Yes", "No"],  // texte de vrai, de faux (défaut : true, false)
  "UNITS": {"energy": "eV"}, // grandeur (UNIT) → nom d'unité du logiciel
  "MODIFIER": "[{unit}]"     // gabarit d'écriture de l'unité
}
```

## Sémantique des conditions (`MANDATORY_IF`, `EXCLUDE_IF`, `REQUIRES`)

Règles appliquées par `amac/parameter/validator.py`.

### Emplacement d'une option

Le `PATH` d'une condition désigne un emplacement **dans l'input du logiciel**, pas
une clé des kwargs utilisateur. L'emplacement de chaque option fournie est calculé
ainsi :

- une méthode est placée à son `PATH`, un module à son `TARGET` (s'il s'agit d'un
  chemin), une variante à son `PATH`, ou à défaut à celui de sa famille ;
- la *base* d'un nœud est son emplacement suivi de son `KEYWORD` quand celui-ci est
  non vide : c'est sous la base que se placent ses `ARGUMENTS` ;
- une option est placée à son `PATH` s'il est déclaré, sinon sous la base de son
  parent suivie de sa clé canonique (une entrée de `PARAMETERS` sans `PATH` est donc
  à `[<clé>]`) ;
- un compagnon (`COMPANION`) sans `PATH` est placé à côté de son propriétaire ;
- pour un `CHOICE` fourni sous la forme `{choix: options}`, les options sont placées
  sous `emplacement + [choix]` (suivi du `KEYWORD` de l'entrée du choix s'il existe) ;
- une option à variantes est enregistrée avec le `KEYWORD` (ou la clé) de la variante
  choisie pour valeur.

La méthode et le module sont eux-mêmes enregistrés à leur emplacement avec leur
`KEYWORD` pour valeur.

Exemple DFTB+ : `module="GEOMETRY_OPTIMISATION"` (`TARGET ["Driver"]`, `KEYWORD
"GeometryOptimisation"`) et `module_args={"Isotropic": true}` placent `Isotropic` à
`["Driver", "GeometryOptimisation", "Isotropic"]` ; `method="TIGHT_BINDING"` rend
vraie la condition `{"PATH": ["Hamiltonian"], "VALUE": "DFTB"}`.

### Résolution du `PATH`

1. **Relatif** si le premier élément désigne (clé ou alias, casse ignorée) un voisin
   du nœud qui porte la condition, c'est-à-dire un nœud du même `ARGUMENTS` (ou de
   `PARAMETERS` et de leurs compagnons) : le chemin part de l'emplacement de ce
   voisin. Exemple : `["Timescale"]` dans le thermostat `Berendsen`.
2. **Absolu** sinon, depuis la racine de l'input.

Les éléments suivants sont comparés sans tenir compte de la casse, sans résolution
d'alias. Pour le `REQUIRES` d'un module, les voisins sont les `ARGUMENTS` du module.

### Comparaison de `VALUE`

- `"SET"` : vraie si l'option a été fournie (ou imposée par `SETS`), quelle que soit
  sa valeur.
- Sinon, égalité avec la valeur fournie : chaînes comparées sans tenir compte de la
  casse, booléen égal seulement à un booléen (`true` ≠ `1`). Pour un `CHOICE`, la
  valeur comparée est le choix.
- Une option non fournie ne rend aucune condition vraie : `DEFAULT` n'est pas
  appliqué. Un emplacement que l'utilisateur ne renseigne pas (par exemple
  `["Geometry", "Periodic"]`, dérivé de la géométrie) ne rend donc jamais une
  condition vraie.

### Combinaison

- `MANDATORY_IF` : l'option est obligatoire si **au moins une** condition est vraie
  (OU). `MANDATORY: true` rend l'option obligatoire sans condition.
- `EXCLUDE_IF` : l'option est interdite si **au moins une** condition est vraie (OU).
- `MANDATORY` et `MANDATORY_IF` ne concernent que les options dont le parent est
  présent : les `ARGUMENTS` de la méthode, de la variante et du module choisis, les
  entrées de `PARAMETERS` et leurs compagnons, les `ARGUMENTS` d'une option fournie
  ou d'un choix retenu.
- Une liste vide (`[]`) ne pose aucune condition.
- `REQUIRES` d'un module : **toutes** les exigences doivent être satisfaites (ET).
  Une chaîne désigne une entrée de `PARAMETERS` (clé ou alias) qui doit être
  fournie ; un objet `{ "PATH": [...], "VALUE": ... }` est une condition qui doit
  être vraie.

## Variantes, `SETS`, `COMPANION` et `COMMON_ARGUMENTS`

Règles appliquées à l'identique par le validateur et par `translate()`.

### `VARIANTS` d'une option

Une option (entrée de `PARAMETERS` ou d'`ARGUMENTS`) peut déclarer des `VARIANTS`, de
même forme que celles des méthodes (`KEYWORD`, `PATH`, `ALIASES`, `ARGUMENTS`,
`SETS`).

- **Option non `CHOICE`** (`BLOCK`, `TREE`…) : la valeur est un dict dont la clé
  réservée `variant` (casse ignorée) désigne une variante (clé ou alias, casse
  ignorée), comme `method_args={"variant": ...}` pour une méthode. Les autres clés
  sont confrontées aux `ARGUMENTS` de l'option fusionnés avec ceux de la variante (la
  variante l'emporte). Sans clé `variant`, seuls les `ARGUMENTS` de l'option
  s'appliquent ; s'il n'y a aucun `ARGUMENTS`, le contenu n'est pas décrit et n'est
  pas vérifié.
  Exemple DFTB+ : `"SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Suffix":
  ".skf"}` (`Prefix` n'est pas un argument : AMAC l'écrit depuis `BASIS`, `env` de
  `config-amac.json`).
- **Option `CHOICE`** : le choix peut désigner une variante comme une entrée
  d'`ARGUMENTS` (les `ARGUMENTS` sont cherchés d'abord). Le contenu de
  `{choix: contenu}` est vérifié contre la variante (`TYPE`, `ARGUMENTS`). Sans
  `VALUES`, un choix qui ne désigne ni une entrée d'`ARGUMENTS` ni une variante est
  refusé.
  Exemple DFTB+ : `"KPOINTS": {"SupercellFolding": [[4, 0, 0], [0, 4, 0], [0, 0, 4],
  [0.5, 0.5, 0.5]]}`.
- **Emplacements** (option non `CHOICE`) : l'option est enregistrée avec le `KEYWORD`
  de la variante (ou sa clé) pour valeur ; les `ARGUMENTS` de la variante sont placés
  sous `emplacement de la variante + KEYWORD`, l'emplacement de la variante étant son
  `PATH` ou celui de l'option. Dans l'arbre, le `KEYWORD` de la variante est la valeur
  de l'emplacement de l'option (`SlaterKosterFiles = Type2FileNames { … }`),
  contrairement à une variante de méthode sans `PATH`, qui va dans `keywords`.

### `SETS`

`SETS`, dans une variante de méthode, de module ou d'option, associe des noms
d'options à des valeurs imposées quand la variante est choisie. Les noms désignent des
options du périmètre de la variante (`ARGUMENTS` de la famille ou de l'option, et de
la variante), par clé ou alias, casse ignorée.

- Option absente : elle prend la valeur imposée, vérifiée comme une valeur fournie
  (`TYPE`, `VALUES`, conditions) ; `translate()` l'écrit.
- Option fournie avec la même valeur : rien à signaler.
- Option fournie avec une autre valeur : `Issue` d'erreur (`ValidationError` en
  `strict`, avertissement en `warn`). En `off`, et dans `translate()`, la valeur de
  l'utilisateur est gardée.
- Un nom de `SETS` inconnu, ou des `SETS` dans une variante dont le périmètre n'a
  aucun `ARGUMENTS`, est une erreur du `doc.json`, signalée comme une `Issue`.

Exemple DFTB+ : `method_args={"variant": "DFTB2"}` impose `SCC = true`.

### `COMPANION`

`COMPANION`, dans une entrée de premier niveau de `PARAMETERS`, déclare des paramètres
associés. Ils se fournissent comme les autres entrées de `parameters` (clé canonique ou
alias, casse ignorée), et sont validés et traduits comme elles (`TYPE`, `MANDATORY`,
`MANDATORY_IF`, `EXCLUDE_IF`…). Un compagnon est placé à son `PATH` ; sans `PATH`, à
côté de son propriétaire : emplacement du propriétaire privé de son dernier élément,
suivi de la clé du compagnon.

Exemple DFTB+ : `SpinConstants`, compagnon de `SPIN_POLARISATION`, devient obligatoire
dès que `SpinPolarisation` est fourni.

### `COMMON_ARGUMENTS`

`COMMON_ARGUMENTS`, dans une option `CHOICE`, déclare des arguments valables pour tous
les choix. Le contenu de `{choix: options}` doit alors être un dict ; il est vérifié
contre `COMMON_ARGUMENTS` fusionnés avec les `ARGUMENTS` de l'entrée du choix (l'entrée
l'emporte), et placé sous `emplacement du choix + KEYWORD`.

Exemple DFTB+ : `"FILLING": {"Fermi": {"Temperature": 0.001}}`.

### `CONDITION`

Les champs `CONDITION` en texte libre (ex. `"SCC = Yes"`) sont documentaires : ni le
validateur ni le composer ne les interprètent. Les conditions vérifiées s'écrivent avec
`MANDATORY_IF` et `EXCLUDE_IF`.

## Fichiers produits (`OUTPUT.FILES`)

Chaque clé de `OUTPUT.FILES` est un motif glob relatif au répertoire du calcul
(`detailed.out`, `*.xyz`). `FileIOSoftware.collect` enregistre dans `ctx.files` chaque
fichier correspondant, sous son chemin relatif ; un fichier absent n'est pas une erreur.

## Traduction vers l'input (composer)

Règles appliquées par `translate(spec, schema)` (`amac/parameter/composer.py`). La
fonction produit un arbre intermédiaire indépendant de la syntaxe : chaque famille
`SYNTAX` le rend en texte, et un driver de bibliothèque peut le lire directement.

### Arbre intermédiaire

- `InputTree` : `nodes` (emplacements de premier niveau, par nom), `keywords` (liste
  ordonnée sans doublon), `raw`, `format` (`INPUT.FORMAT_DEFAULTS`).
- `Node` : `value` (valeur Python non rendue, `None` pour un bloc sans valeur),
  `unit` (`UNIT` du nœud du schéma), `format` (format fusionné), `children`
  (sous-emplacements, par nom).

Exemple : `method="DFT"`, `method_args={"variant": "PBE", "Charge": 1}`,
`parameters={"DISPERSION": "D3"}` donnent :

```
nodes:    Hamiltonian = "DFT"
            └─ DFT
                ├─ Charge = 1
                └─ Dispersion = "D3"
keywords: ["PBE"]
```

### Placement

- Chaque valeur fournie est écrite à l'emplacement que lui attribue la section
  « Emplacement d'une option », sous sa clé canonique (alias résolus). Les chemins de
  l'arbre et ceux des conditions désignent donc les mêmes emplacements.
- Méthode, variante, module : si le nœud a un emplacement propre (`PATH` de la
  méthode ou de la variante, `TARGET` du module s'il est un chemin), son `KEYWORD`
  est la valeur de cet emplacement (`KEYWORD` vide ou `null` : emplacement créé sans
  valeur). Sinon, un `KEYWORD` non vide est ajouté à `keywords` (ligne de mots-clés,
  `TARGET` non chemin comme `"SIMPLE_INPUT"`). Une variante de méthode sans `PATH` va
  donc dans `keywords`, même si sa famille a un `PATH`.
- `CHOICE` : le choix est la valeur de l'emplacement, les options de
  `{choix: options}` sont placées sous `emplacement + [choix]`.
- Variantes d'options, `SETS`, `COMPANION` et `COMMON_ARGUMENTS` : voir la section
  précédente. Les valeurs imposées par `SETS` sont écrites pour les options absentes.
- Contenu non décrit (nœud sans `ARGUMENTS`) : recopié tel quel, un dict devenant des
  sous-emplacements.
- Les chemins fusionnent sans tenir compte de la casse : la première écriture fixe
  l'orthographe.
- `DEFAULT` n'est jamais écrit ; `CONDITION` n'est pas interprété.
- Deux valeurs différentes au même emplacement, ou un nom absent du schéma (méthode,
  module, variante, option déclarée) : `ValidationError`, quel que soit le mode de
  validation. `raw` sert à contourner le schéma.

### Rendu

- Format d'un nœud : fusion superficielle (clé par clé, premier niveau) de
  `INPUT.FORMAT_DEFAULTS` et du `FORMAT` du nœud, sans héritage du parent.
- Booléens : `BOOLEAN[0]` pour vrai, `BOOLEAN[1]` pour faux, `true` / `false` si
  `BOOLEAN` n'est pas déclaré.
- Unités : `FORMAT.UNITS` associe une grandeur (`UNIT`) au nom d'unité du logiciel ;
  un `UNIT` absent de `UNITS` est pris comme nom d'unité (ex. `"Hartree"`). Le nom
  est inséré dans `FORMAT.MODIFIER` s'il est déclaré. Les valeurs ne sont pas
  converties : elles sont supposées exprimées dans cette unité.
- `compose` renvoie `{INPUT.FILENAME: texte}` ; le texte vient de `render(tree)`, que
  les sous-classes propres à un logiciel surchargent pour ajouter la géométrie
  (`atoms` est ignoré par les composers de base). L'arbre reçu n'est jamais modifié.
- Clés de `FORMAT` absentes : `TREE` prend `ASSIGN " = "`, `OPEN "{"`, `CLOSE "}"`,
  `PADDING "  "`, `SEPARATOR " "` ; `KEYWORD_BLOCK` prend `INLINE false`,
  `ASSIGN " "`, `OPEN ""`, `CLOSE "end"`, `PADDING "  "`, `SEPARATOR " "`.
- `raw` (`TREE` et `KEYWORD_BLOCK`) : un `str` ou une `list[str]` donne des lignes
  écrites telles quelles (en fin de fichier pour `TREE`, après la ligne de mots-clés
  pour `KEYWORD_BLOCK`) ; un `dict` est fusionné dans une copie de l'arbre comme le
  contenu non décrit (chemins sans casse, dict imbriqué = sous-emplacements), une
  valeur en conflit levant `ValidationError`.

`TREE` (HSD) — chaque ligne suit le format de son nœud, indentée de `PADDING` par
niveau :

- Valeur `V` avec un enfant nommé `V` (casse ignorée) : `Nom = V {`, contenu de cet
  enfant (sa valeur puis ses enfants) puis autres enfants, `}` ; `Nom = V {}` si ce
  contenu est vide. Une valeur avec des enfants dont aucun ne s'appelle `V` s'écrit
  de même.
- Valeur sans enfant : `Nom = V`. Sans valeur : `Nom = {` enfants `}`, ou `Nom = {}`.
- Unité : `Nom [unité] = V`. Nombres : `str()`. Chaînes : nues (`DFTB`), entre `"`
  si vides ou contenant un blanc ou l'un de `{ } = [ ] " #` ; une chaîne contenant
  `"` ne peut pas être citée (`ValueError`).
- Liste plate : valeurs jointes par `SEPARATOR` (`Atoms = 1 2 3`). Tableau (liste de
  listes) : `Nom = {`, une ligne par rangée, `}`.
- Pas de ligne de mots-clés : `keywords` non vide lève `ValueError`.

`KEYWORD_BLOCK` :

- Ligne de mots-clés : `keywords` puis les valeurs des nœuds de premier niveau dont
  le format a `INLINE` vrai, jointes par le `SEPARATOR` de `InputTree.format`,
  précédées de `KEYWORD_PREFIX` (attribut de classe : `!` pour ORCA, `#p` pour
  Gaussian) ; pas de ligne si rien à écrire. Un nœud `INLINE` avec enfants lève
  `ValueError`.
- Autres nœuds, dans l'ordre : `Nom` + `ASSIGN` + valeur (`%maxcore 2000`) ; avec
  enfants, `Nom` (+ valeur) (+ `OPEN` s'il est non vide), enfants indentés de
  `PADDING` (sous-blocs récursifs), puis `CLOSE` s'il est non vide (`end`).
- Valeurs : booléens via `BOOLEAN`, listes jointes par `SEPARATOR`, chaînes telles
  quelles ; l'unité suit le nom.

### Ressources et `raw`

- `INPUT.RESOURCES` : `{"CPU": [chemin], "RAM": [chemin]}`. `ExecutionSpec.cpu` et
  `ExecutionSpec.ram` (Mo) y sont écrits tels quels ; une ressource sans chemin, ou
  de valeur `None`, n'est pas écrite.
- `raw` n'est jamais validé : il est copié tel quel dans `InputTree.raw`, et son
  insertion dans le texte revient au composer de la famille.

## Lien avec le catalogue (`CANONICAL`)

Le catalogue canonique (`catalog/`, format dans `CATALOG_SCHEMA.md`) nomme
méthodes, modules et options indépendamment des logiciels. Un nœud d'un `doc.json`
s'y rattache par `CANONICAL`, à n'importe quelle profondeur de `MODULES`, `METHODS` et
`PARAMETERS` (famille, variante, entrée d'`ARGUMENTS`, choix…).

```jsonc
"DFTB2": { "CANONICAL": "DFTB2" }          // forme courte : équivalence EXACT

"DftD3": {                                  // forme longue : un nœud, plusieurs entrées
  "CANONICAL": {
    "D3(BJ)": { "SETS": { "Damping": "BeckeJohnson" } },
    "D3(0)":  { "SETS": { "Damping": "ZeroDamping" } }
  }
}

"MODES": {
  "CANONICAL": { "FREQUENCIES": { "EQUIVALENCE": "APPROX", "NOTE": "sans thermochimie" } }
}
```

Règles appliquées par `links()` (`amac/parameter/catalog.py`) :

- la valeur est un identifiant du catalogue, ou un objet non vide dont chaque clé est
  un identifiant. Un alias est refusé, l'erreur donne l'identifiant à utiliser ;
- clés admises dans l'objet : `EQUIVALENCE` (`EXACT` par défaut ; `APPROX` quand le
  logiciel s'écarte de la définition canonique : paramétrisation, termes omis…),
  `NOTE` (texte libre) et `SETS` (valeurs que prennent les options du nœud pour
  exprimer l'entrée) ;
- les noms de `SETS` désignent des `ARGUMENTS` ou `COMMON_ARGUMENTS` du nœud (clé ou
  alias, casse ignorée) ; une valeur texte doit figurer dans les `VALUES` de l'option
  quand elles sont déclarées ;
- une entrée `MODULE` ne se lie que depuis `MODULES`, et `MODULES` ne se lie qu'à des
  entrées `MODULE` ; `METHODS` et `PARAMETERS` visent méthodes et options ;
- le mot-clé du lien est le `KEYWORD` non vide du nœud, sinon sa clé ;
- plusieurs nœuds peuvent viser la même entrée (`DftD3` et `SimpleDftD3` vers
  `D3(BJ)`).

Le validateur et le composer ignorent `CANONICAL` : ses `SETS` ne sont pas appliqués
aux paramètres de l'utilisateur.
