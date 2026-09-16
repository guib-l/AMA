# Format du catalogue canonique

Le répertoire `catalog/`, à la racine du dépôt, nomme les méthodes, modules et options
**indépendamment des logiciels**. Chaque `doc.json` s'y rattache par `CANONICAL` (voir
`DOC_SCHEMA.md`, « Lien avec le catalogue »). Le catalogue est lu par
`amac/parameter/catalog.py`.

Règle de répartition : **ce qui relève de la physique va dans le catalogue, ce qui
dépend du logiciel reste dans `doc.json`**. Exemple : « DFT exige une fonctionnelle » est
intrinsèque, « la base est obligatoire » ne l'est pas (GPAW et Quantum Espresso
utilisent des ondes planes). Un fichier du catalogue ne cite donc aucun logiciel, aucun
mot-clé d'entrée et aucun choix d'implémentation.

## Arborescence

```
catalog/
├── methods/              KIND = METHOD : familles et leurs variantes
│   ├── dft/              DFT ; les fonctionnelles sont ses variantes
│   │   ├── entry.json
│   │   └── README.md
│   └── dftb/ …
├── modules/              KIND = MODULE : run types
│   └── single-point/ …
└── options/              KIND = OPTION : axes et leurs valeurs
    └── dispersion/ …
```

- **Un dossier = une entrée de premier niveau** (famille, module ou axe). Ses variantes
  sont déclarées dans son `entry.json`, jamais dans un sous-dossier : `MP2` est une
  variante de `MOLLER_PLESSET` (`methods/moller-plesset/`), pas un dossier.
- Le nom du dossier (slug) est en minuscules, mots séparés par `-`
  (`^[a-z0-9]+(-[a-z0-9]+)*$`). Il dérive en principe de l'identifiant
  (`SINGLE_POINT` → `single-point`), mais seul l'`ID` fait foi
  (`GEOMETRY_OPTIMISATION` est dans `optimization/`).
- Seuls `methods/`, `modules/` et `options/` sont admis à la racine, et chaque dossier
  d'entrée contient un `entry.json`.
- Ordre des entrées : méthodes, modules puis options ; dossiers par ordre alphabétique ;
  chaque variante après son parent, dans l'ordre de déclaration.

## `entry.json`

```jsonc
{
  "ID": "DFTB",                        // identifiant canonique, obligatoire
  "ALIASES": ["TIGHT_BINDING_DFTB"],   // autres noms acceptés
  "VARIANT_REQUIRED": true,            // la famille seule ne définit pas un calcul
  "ACCEPTS": ["DISPERSION", "SOLVATION"],
  "DESCRIPTION": "...",
  "VARIANTS": {
    "DFTB2": { "ALIASES": ["SCC-DFTB"], "DESCRIPTION": "..." }
  }
}
```

| Clé | Sens |
|---|---|
| `ID` | identifiant de l'entrée de premier niveau, texte non vide ; absent des variantes, dont la clé est l'identifiant |
| `ALIASES` | liste de noms non vides |
| `VARIANTS` | entrées filles, de même forme sans `ID` (récursif), de même `KIND` |
| `VARIANT_REQUIRED` | booléen : l'entrée doit avoir au moins une variante |
| `ACCEPTS` | axes d'options (entrées de premier niveau de `options/`) pertinents pour la méthode ; documentaire pour l'instant |
| `DESCRIPTION` | texte court |

Toute autre clé est une information libre, non interprétée : `CLASS`, `EXX`, `PT2` et
`LIBXC` (noms des composantes dans Libxc) pour les fonctionnelles, variantes de `DFT`
dans `methods/dft/entry.json`.

Dans `options/`, une entrée de premier niveau est un **axe** et ses variantes en sont
les **valeurs** (`DISPERSION` → `D3(BJ)`) ; un axe sans variante est une option simple
(`SPIN_ORBIT_COUPLING`).

## `README.md`

Ignoré par le chargeur. Il suit un modèle minimal : un résumé de l'entrée (et de ses
variantes si besoin) et ses références, une par ligne, avec le DOI quand il existe.

```markdown
# DFTB

## Résumé

Density Functional Tight Binding, paramétré par des fichiers Slater-Koster.

## Références

- M. Elstner et al., Phys. Rev. B 58, 7260 (1998). doi:10.1103/PhysRevB.58.7260
```

## Règles vérifiées au chargement

- **Identifiants et alias uniques dans tout le catalogue**, casse ignorée, tous dossiers
  et tous `KIND` confondus : un nom désigne toujours une seule entrée.
- Un identifiant n'est déclaré qu'une fois.
- Chaque `entry.json` est un objet avec un `ID` non vide ; aucune variante n'a d'`ID`.
- Slug valide, dossiers de premier niveau limités à `methods`, `modules` et `options`,
  `entry.json` présent dans chaque dossier d'entrée.
- `ACCEPTS` ne cite que des axes d'options.
- `VARIANT_REQUIRED: true` exige au moins une variante.

Une violation lève `ValidationError`, avec le fichier en cause.

## Conventions de nommage

- Noms usuels de la littérature, sans espace : `M06-2X`, `CCSD(T)`, `D3(BJ)`.
- Bases (à venir) : noms de Basis Set Exchange (`cc-pVDZ`, `6-31G*`).
- Un nom ambigu dans la littérature reçoit un identifiant explicite : `B3LYP` (VWN3) et
  `B3LYP5` (VWN5).
- Les approximations ne sont pas des méthodes : `RI-MP2` est `MP2` avec
  `INTEGRAL_APPROXIMATION = RI-J`, `UHF` est `HF` avec `REFERENCE = UNRESTRICTED`.

## Ajouter une entrée

L'agent `catalog-curator` (`.claude/agents/catalog-curator.md`) ajoute une entrée, une
variante ou un alias à partir des informations fournies, sans rien inventer, puis
vérifie le catalogue et les liens `CANONICAL` existants.
