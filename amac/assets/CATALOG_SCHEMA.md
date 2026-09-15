# Format du catalogue canonique

Le paquet `amac/assets/catalog/` nomme les méthodes, modules et options **indépendamment
des logiciels**. Chaque `doc.json` s'y rattache par `CANONICAL` (voir `DOC_SCHEMA.md`,
« Lien avec le catalogue »). Le catalogue est lu par `amac/parameter/catalog.py`.

Règle de répartition : **ce qui relève de la physique va dans le catalogue, ce qui
dépend du logiciel reste dans `doc.json`**. Exemple : « DFT exige une fonctionnelle » est
intrinsèque, « la base est obligatoire » ne l'est pas (GPAW et Quantum Espresso
utilisent des ondes planes).

## Fichiers

| Fichier | `KIND` | Contenu |
|---|---|---|
| `methods.json` | `METHOD` | familles (`HF`, `DFTB`, `COUPLED_CLUSTER`…) et leurs variantes |
| `functionals.json` | `METHOD` | fonctionnelles, variantes de `DFT` (`PARENT`) |
| `modules.json` | `MODULE` | run types (`SINGLE_POINT`, `GEOMETRY_OPTIMISATION`…) |
| `options.json` | `OPTION` | axes orthogonaux (`REFERENCE`, `DISPERSION`, `SOLVATION`…) et leurs valeurs |

Tout fichier `*.json` du répertoire est chargé, par ordre alphabétique.

## Structure d'un fichier

```jsonc
{
  "CATALOG": "FUNCTIONALS",   // nom du fichier, documentaire
  "KIND": "METHOD",           // METHOD | MODULE | OPTION
  "PARENT": "DFT",            // facultatif : entrée (même KIND, autre fichier) dont les
                              // entrées de premier niveau sont les variantes
  "DESCRIPTION": "...",
  "ENTRIES": { "<id>": { ... } }
}
```

## Entrées

```jsonc
"DFTB": {
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
| `ALIASES` | liste de noms non vides |
| `VARIANTS` | entrées filles, de même forme (récursif), de même `KIND` |
| `VARIANT_REQUIRED` | booléen : l'entrée doit avoir au moins une variante (dans ce fichier ou via `PARENT`) |
| `ACCEPTS` | axes d'`options.json` (entrées `OPTION` de premier niveau) pertinents pour la méthode ; documentaire pour l'instant |
| `DESCRIPTION` | texte court |

Toute autre clé est une information libre, non interprétée : `CLASS`, `EXX`, `PT2` et
`LIBXC` (noms des composantes dans Libxc) pour les fonctionnelles.

Dans `options.json`, une entrée de premier niveau est un **axe** et ses variantes en
sont les **valeurs** (`DISPERSION` → `D3(BJ)`) ; un axe sans variante est une option
simple (`SPIN_ORBIT_COUPLING`).

## Règles vérifiées au chargement

- **Identifiants et alias uniques dans tout le catalogue**, casse ignorée, tous fichiers
  et tous `KIND` confondus : un nom désigne toujours une seule entrée.
- Un identifiant n'est déclaré qu'une fois.
- `PARENT` désigne une entrée existante du même `KIND`.
- `ACCEPTS` ne cite que des axes d'options.
- `VARIANT_REQUIRED: true` exige au moins une variante.

Une violation lève `ValidationError`, avec le fichier en cause.

## Conventions de nommage

- Noms usuels de la littérature, sans espace : `M06-2X`, `CCSD(T)`, `D3(BJ)`.
- Bases (à venir) : noms de Basis Set Exchange (`cc-pVDZ`, `6-31G*`).
- Un nom ambigu entre logiciels reçoit un identifiant explicite : `B3LYP` (VWN3,
  Gaussian) et `B3LYP5` (VWN5, B3LYP d'ORCA).
- Les approximations ne sont pas des méthodes : `RI-MP2` est `MP2` avec
  `INTEGRAL_APPROXIMATION = RI-J`, `UHF` est `HF` avec `REFERENCE = UNRESTRICTED`.
