# Proposition d'implémentation 01 : paquets logiciels de `amac/assets/`

Ce document propose l'organisation des paquets `amac/assets/<logiciel>/` pour **ORCA**,
**Gaussian**, **DFTB+** et **deMonNano**. Il s'appuie sur le socle existant, sans le
modifier sauf mention explicite : `Software`, `FileIOSoftware`, `InProcessSoftware`,
`Driver`, `@handler`, `translate()` et `CANONICAL`.

Conventions :

- `<PLACEHOLDER: …>` : information non connue avec certitude, à compléter ou à
  vérifier dans la documentation du logiciel ou de la bibliothèque.
- ✓ : lien `CANONICAL` exact ; ≈ : lien `EQUIVALENCE: "APPROX"` ; ? : capacité
  probable mais à confirmer (placeholder) ; — : non supporté ou hors catalogue.

---

## 1. Principes

1. **Deux chemins par phase.** Pour ORCA, Gaussian et DFTB+, chaque phase
   (`prepare` = générer l'input, `collect` = lire les sorties) existe **en local**
   (chemin `"amac"` : composer et parser écrits dans AMAC) **et** par au moins une
   **bibliothèque dédiée** (un `Driver`). Le choix se fait avec `driver=` (`"amac"`,
   `"auto"` ou un nom), comme aujourd'hui.
2. **Des drivers par combinaison de phases.** Un calculateur n'a qu'un driver. Pour
   combiner « input local + parser bibliothèque », on déclare un driver dont
   `PHASES` ne contient que `collect`. On obtient ainsi une petite famille de drivers
   par logiciel (tableau §4).
3. **Des handlers indépendants du chemin.** Les handlers communs (`energy`, `forces`,
   …) lisent un **résultat normalisé** (`<Logiciel>Output`, dataclass). Il est rempli
   soit par le parser local, soit par le driver qui collecte. Seuls les handlers
   renvoyant un objet natif d'une bibliothèque déclarent `drivers=(...)`.
4. **Capacités = logiciel ∩ catalogue.** Une méthode, un module ou une valeur d'option
   n'est exposé dans `doc.json` que si le logiciel sait le faire **et** si l'entrée
   existe dans `catalog/`. Le nœud porte alors un `CANONICAL`. Ce qui n'existe pas dans
   le catalogue (ZINDO/S, ONIOM, CASMP2, pSIC, …) n'est pas exposé. On l'ajoutera plus
   tard avec l'agent `catalog-curator`, puis on créera le lien.
5. **Aucune découverte automatique.** Exécutables, bibliothèques partagées
   (`libdftbplus.so`) et utilitaires (`formchk`, `orca_plot`, `modes`) ne viennent que
   de sources explicites : `executable=`, variable d'environnement ou fichier de
   configuration. Jamais du `PATH`.
6. **deMonNano** n'a qu'une bibliothèque Python. Il n'a ni composer ni parser local
   (§3.4).

---

## 2. Arborescence type

```
amac/assets/
├── __init__.py                 # imports explicites (inchangé dans le principe)
├── _shared/                    # privé : ignoré par documented_software()
│   ├── __init__.py
│   ├── cclib_driver.py         # driver "cclib" (collect) partagé ORCA / Gaussian
│   └── units.py                # <PLACEHOLDER: conversions, en attente de la décision sur les unités>
├── orca/
│   ├── __init__.py             # expose les handlers
│   ├── doc.json                # SYNTAX KEYWORD_BLOCK, liens CANONICAL
│   ├── orca.py                 # classe Orca(FileIOSoftware) + DRIVERS
│   ├── composer.py             # OrcaComposer : générateur d'input local
│   ├── parser.py               # OrcaOutput + parse_directory() : parser local
│   ├── drivers.py              # OpiDriver, OpiParserDriver
│   └── handlers.py             # @handler(software="ORCA", ...)
├── gaussian/
│   ├── __init__.py
│   ├── doc.json
│   ├── gaussian.py             # Gaussian(FileIOSoftware)
│   ├── composer.py             # GaussianComposer
│   ├── parser.py               # GaussianOutput + parse_directory()
│   ├── drivers.py              # AseGaussianDriver, <PLACEHOLDER: bibliothèque dédiée>
│   └── handlers.py
├── dftbplus/
│   ├── __init__.py
│   ├── doc.json                # à restaurer : supprimé dans l'arbre de travail
│   ├── dftbplus.py             # DftbPlus(FileIOSoftware)
│   ├── composer.py             # DftbPlusComposer (HSD)
│   ├── parser.py               # DftbPlusOutput : results.tag, detailed.out, band.out
│   ├── drivers.py              # DftbPlusApiDriver, HsdDriver, AseDftbDriver
│   └── handlers.py
└── demonnano/
    ├── __init__.py
    ├── doc.json                # SYNTAX API, EXECUTION ["INPROCESS"]
    ├── demonnano.py            # DeMonNano(InProcessSoftware), délègue à la bibliothèque
    └── handlers.py

test/
├── fixtures/
│   ├── orca/                   # sorties réelles anonymisées (orca.out, .engrad, .hess, …)
│   ├── gaussian/               # gaussian.log, gaussian.fchk
│   ├── dftbplus/               # results.tag, detailed.out, band.out, dftb_pin.hsd
│   └── demonnano/              # <PLACEHOLDER: objets sérialisés ou sorties de la bibliothèque>
└── assets/
    ├── test_orca_composer.py   # rendu d'input comparé à des fichiers attendus
    ├── test_orca_parser.py     # parsing des fixtures, sans ORCA installé
    ├── test_orca_drivers.py    # bibliothèques factices, comme amac_dummy_lib
    └── …                       # idem pour chaque logiciel
```

Rôle de chaque fichier :

| Fichier | Contenu | Dépend de |
|---|---|---|
| `<logiciel>.py` | `NAME`, `ALIASES`, `DOC`, `composer_cls`, `DRIVERS`, `command()`, `stdout_file()`, `version()` | `composer.py`, `drivers.py` |
| `composer.py` | rendu de l'`InputTree` et de la géométrie en texte | `amac.parameter.composer` |
| `parser.py` | fonctions pures `texte → OutputData`, sans `RunContext` ; testables seules | numpy, ase |
| `drivers.py` | un `Driver` par bibliothèque ou combinaison de phases ; bibliothèques importées **dans les phases** | `parser.py` (dataclass) |
| `handlers.py` | handlers communs et spécifiques ; importe `<logiciel>.py` en premier | `parser.py` |
| `__init__.py` | `from amac.assets.<logiciel>.handlers import energy, …` | `handlers.py` |

### 2.1 Résultat normalisé et handlers

Motif commun aux quatre logiciels (exemple ORCA) :

```python
# amac/assets/orca/parser.py
@dataclass
class OrcaOutput:
    """Grandeurs lues dans les sorties, unités du programme."""

    energy: float | None = None
    forces: np.ndarray | None = None           # (n, 3)
    dipole: np.ndarray | None = None           # (3,)
    charges: dict[str, np.ndarray] = field(default_factory=dict)  # {"mulliken": …, "loewdin": …}
    orbital_energies: np.ndarray | None = None
    final_geometry: Atoms | None = None
    frequencies: np.ndarray | None = None
    hessian: np.ndarray | None = None
    excitations: np.ndarray | None = None      # énergies, forces d'oscillateur
    terminated_normally: bool = False


def parse_directory(directory: Path, basename: str = "orca") -> OrcaOutput:
    """Lit orca.out, orca.engrad, orca.hess et orca.xyz quand ils existent."""
```

```python
# amac/assets/orca/handlers.py
from amac.assets.orca.orca import OUTPUT_KEY, Orca  # enregistre ORCA en premier
from amac.assets.orca.parser import OrcaOutput, parse_directory
from amac.engine.handlers import handler


def _output(ctx) -> OrcaOutput:
    """Résultat du driver collecteur, sinon parsing local mis en cache."""
    if OUTPUT_KEY not in ctx.objects:
        ctx.objects[OUTPUT_KEY] = parse_directory(ctx.directory)
    return ctx.objects[OUTPUT_KEY]


@handler(software="ORCA", requires_files=("orca.out",))
def energy(ctx):
    return _output(ctx).energy


@handler(software="ORCA", modules=("GEOMETRY_OPTIMISATION", "TRANSITION_STATE_SEARCH"))
def final_geometry(ctx): ...


@handler(software="ORCA", drivers=("opi",))
def opi_output(ctx):
    return ctx.objects["opi"]  # objet natif OPI
```

Règle : un driver qui collecte **doit** remplir `ctx.files`, pour que `requires_files`
reste valable, et `ctx.objects[OUTPUT_KEY]` avec la dataclass normalisée. Les handlers
communs fonctionnent alors avec tous les drivers ; `amac.reprocess` fonctionne aussi,
car le cache est reconstruit depuis les fichiers.

Les méthodes vides actuelles des classes (`energies`, `mulliken_charges`, `eigenvalues`,
…) sont supprimées. Elles deviennent des handlers aux noms communs (`energy`,
`charges`, …), plus des handlers spécifiques (`mulliken_charges`, `orbital_energies`).

---

## 3. Proposition par logiciel

### 3.1 ORCA (`NAME = "ORCA"`)

#### Classe

```python
@register_software
class Orca(FileIOSoftware):
    NAME = "ORCA"
    ALIASES = ()
    DOC = Path(__file__).with_name("doc.json")
    composer_cls = OrcaComposer
    DRIVERS = (OpiDriver, OpiParserDriver, CclibDriver)  # ordre pour driver="auto"
    # EXECUTABLE_ENV = "ORCA_EXECUTABLE" (défaut)

    def command(self, ctx):
        # ORCA exige un chemin absolu pour ses runs parallèles : cohérent avec la règle AMAC.
        return [self.require_executable(ctx.exec_spec).path, "orca.inp"]

    def stdout_file(self, ctx):
        return Path("orca.out")

    def version(self):
        return None  # <PLACEHOLDER: lire l'en-tête "Program Version" de orca.out après le run ?>
```

#### Générateur d'input local (`composer.py`)

Il hérite du futur `KeywordBlockComposer` du socle, qui assure le rendu commun
ligne `!` + blocs `%…end`. Sont propres à ORCA :

```
! <méthode/variante> <base> <dispersion> <approximation RI> <module>   # InputTree.keywords
%pal nprocs <cpu> end                     # INPUT.RESOURCES.CPU
%maxcore <ram / cpu>                      # INPUT.RESOURCES.RAM (Mo par cœur)
%scf … end                                # nodes de premier niveau "%scf"
%geom … end
* xyz <charge> <multiplicité>
<symboles et coordonnées en Å>
*
```

- Charge et multiplicité : `<PLACEHOLDER: argument de méthode (Charge, Multiplicity) ou
  ase.Atoms (initial_charges, initial_magnetic_moments) ; décision à prendre, commune
  aux quatre logiciels>`.
- `raw` : lignes ajoutées telles quelles après la ligne `!`.
- `%maxcore` est exprimé **par cœur** : le composer divise `ram` par `cpu`.

#### Parser local (`parser.py`)

| Fichier (`OUTPUT.FILES`) | Contenu lu |
|---|---|
| `orca.out` | énergie finale (`FINAL SINGLE POINT ENERGY`), charges Mulliken/Löwdin, dipôle, énergies orbitalaires, états excités, fréquences, `ORCA TERMINATED NORMALLY` |
| `orca.engrad` | gradient (forces = −gradient) |
| `orca.hess` | Hessienne, fréquences, modes |
| `orca.xyz`, `orca_trj.xyz` | géométrie finale, trajectoire |
| `orca.property.txt` | `<PLACEHOLDER: format ORCA 6, éventuellement plus simple que orca.out>` |
| `orca.gbw` | non lu (binaire) ; gardé pour `orca_plot` |

#### Bibliothèques dédiées (`drivers.py`)

| Driver | `REQUIRES` / `DISTRIBUTION` | `PHASES` | Rôle |
|---|---|---|---|
| `opi` | `("opi",)` / `orca-pi` | prepare, run, collect | OPI écrit l'input (`Calculator`, `input.add_simple_keywords`, …), lance ORCA et lit ses sorties JSON. `check_environment` : ORCA ≥ 6.1 `<PLACEHOLDER: méthode de détection de la version>` |
| `opi-parser` | `("opi",)` / `orca-pi` | collect | AMAC écrit et lance ; OPI lit les sorties. `<PLACEHOLDER: OPI peut-il lire un calcul qu'il n'a pas préparé ? (fichiers JSON produits par orca_2json)>` |
| `cclib` | `("cclib",)` / `cclib` | collect | `cclib.io.ccread("orca.out")`, converti en `OrcaOutput` ; partagé dans `_shared/cclib_driver.py` |

- `opi` : `SUPPORTED_SETTINGS = {"cpu", "ram", "executable"}`. L'exécutable est passé
  **explicitement** à OPI. `<PLACEHOLDER: nom du paramètre ou de la variable
  d'environnement lu par OPI pour le chemin d'ORCA>`. `SUPPORTS_RAW` :
  `<PLACEHOLDER: OPI accepte-t-il des blocs arbitraires ?>`.
- Traduction `InputTree` → objets OPI : table de correspondance dans `drivers.py`.
  La clé est le mot-clé ORCA du `doc.json`, déjà résolu par `translate()`.

#### Capacités ORCA (doc.json ∩ catalogue)

Version de référence : `<PLACEHOLDER: ORCA 6.1>`.

- **Méthodes**
  - `HF` ✓.
  - `DFT` : SVWN5 ✓ (`LSD`/`VWN5` `<PLACEHOLDER: vérifier la composante VWN>`),
    SPW92 ✓ (`PWLDA`), PBE ✓, PBEsol ? (via LibXC), BLYP ✓, BP86 ✓, PW91 ✓, TPSS ✓,
    SCAN ✓, r2SCAN ✓.
  - Hybrides : **B3LYP ✓ (`B3LYP/G`)**, **B3LYP5 ✓ (`B3LYP`, VWN5 dans ORCA)**,
    B3PW91 ✓, PBE0 ✓, TPSSh ✓, M06 ✓, M06-2X ✓, CAM-B3LYP ✓, wB97X-V ✓, B2PLYP ✓.
  - wB97X-D ? : ORCA propose `wB97X-D3`/`wB97X-D4`, distincts selon le catalogue ; le
    lien n'est créé que si `HYB_GGA_XC_WB97X_D` est accessible via LibXC. HSE06 ?
  - `MOLLER_PLESSET` : MP2 ✓, SCS-MP2 ✓, SOS-MP2 ✓, MP3 ?, MP4 —.
  - `COUPLED_CLUSTER` : CCSD ✓, CCSD(T) ✓, QCISD ✓, QCISD(T) ✓, EOM-CCSD ✓, CCSDT ?
    (AUTOCI), CC2 —.
  - `CONFIGURATION_INTERACTION` : CIS ✓, CISD ?, FCI ?.
  - `MULTIREFERENCE` : CASSCF ✓, CASPT2 ✓, NEVPT2 ✓, MRCI ✓.
  - `SEMIEMPIRICAL` : MNDO ?, AM1 ?, PM3 ? (encore présents dans ORCA 6 ?), PM6 —,
    PM7 —.
  - `XTB` : GFN0-xTB ?, GFN1-xTB ✓, GFN2-xTB ✓ (binaire `xtb` externe,
    `<PLACEHOLDER: chemin explicite de xtb>`), IPEA1-xTB —.
  - `DFTB` —.
- **Modules** : SINGLE_POINT ✓, GRADIENT ✓ (`EnGrad`), GEOMETRY_OPTIMISATION ✓,
  TRANSITION_STATE_SEARCH ✓ (`OptTS`), IRC ✓, NEB ✓, PES_SCAN ✓ (`%geom Scan`),
  FREQUENCIES ✓ (`Freq`/`NumFreq`), HESSIAN ≈ (via `Freq`, fichier `.hess`),
  MOLECULAR_DYNAMICS ✓ (`%md`), ORBITAL_PLOT ✓ (programme séparé `orca_plot`,
  `TARGET: "EXTERNAL_PROGRAM"`). ELECTRON_DYNAMICS, ELECTRON_TRANSPORT,
  EXTERNAL_DRIVER et PHONONS : —.
- **Options**
  - `REFERENCE` : RESTRICTED ✓, UNRESTRICTED ✓, RESTRICTED_OPEN ✓, GENERALISED —.
  - `INTEGRAL_APPROXIMATION` : RI-J ✓, RI-JK ✓, RIJCOSX ✓.
  - `LOCAL_CORRELATION` : DLPNO ✓, LPNO ? (retiré des versions récentes ?).
  - `DISPERSION` : D2 ✓, D3(0) ✓, D3(BJ) ✓, D4 ✓, VV10 ✓ (`NL`), D3M(BJ) ? ;
    TS, MBD, LENNARD_JONES et SLATER_KIRKWOOD : —.
  - `SOLVATION` : CPCM ✓, SMD ✓, ALPB ≈ (avec XTB uniquement) ; PCM, COSMO, GB et
    SASA : —.
  - `EXCITED_STATES` : LR-TDDFT ✓, TDA ✓, DELTA-SCF ? ; PP-RPA et REKS : —.
  - `SMEARING` : FERMI_DIRAC ✓ (`SmearTemp`), les autres : —.
  - `SPIN_ORBIT_COUPLING` ✓, `ELECTRIC_FIELD` ✓, `POINT_CHARGES` ✓.
  - `KPOINTS` et `HUBBARD_U` : —.

Extrait de `doc.json` :

```jsonc
{
  "SOFTWARE": "ORCA",
  "VERSION": "<PLACEHOLDER: 6.1>",
  "SYNTAX": "KEYWORD_BLOCK",
  "EXECUTION": ["FILEIO"],
  "INPUT": {
    "FILENAME": "orca.inp",
    "FORMAT_DEFAULTS": {"INLINE": true, "OPEN": "", "CLOSE": "end", "BOOLEAN": ["true", "false"]},
    "RESOURCES": {"CPU": ["%pal", "nprocs"], "RAM": ["%maxcore"]}
  },
  "MODULES": {
    "SINGLE_POINT": {"KEYWORD": "SP", "CANONICAL": "SINGLE_POINT", "TARGET": "SIMPLE_INPUT", "PERIODIC": "MOLECULE"},
    "GEOMETRY_OPTIMISATION": {"KEYWORD": "Opt", "ALIASES": ["OPT"], "CANONICAL": "GEOMETRY_OPTIMISATION", "TARGET": "SIMPLE_INPUT", "PERIODIC": "MOLECULE"},
    "FREQUENCIES": {"KEYWORD": "Freq", "ALIASES": ["FREQ"], "CANONICAL": "FREQUENCIES", "TARGET": "SIMPLE_INPUT"},
    "ORBITAL_PLOT": {"KEYWORD": null, "BINARY": "orca_plot", "TARGET": "EXTERNAL_PROGRAM", "CANONICAL": "ORBITAL_PLOT"}
  },
  "METHODS": {
    "DFT": {
      "KEYWORD": null,
      "CANONICAL": "DFT",
      "VARIANTS": {
        "B3LYP":  {"KEYWORD": "B3LYP",   "CANONICAL": "B3LYP5", "NOTE": "VWN5 dans ORCA"},
        "B3LYP/G":{"KEYWORD": "B3LYP/G", "CANONICAL": "B3LYP"},
        "PBE0":   {"KEYWORD": "PBE0",    "CANONICAL": "PBE0"}
      }
    },
    "MOLLER_PLESSET": {"KEYWORD": null, "CANONICAL": "MOLLER_PLESSET", "VARIANTS": {"MP2": {"KEYWORD": "MP2", "CANONICAL": "MP2"}}}
  },
  "PARAMETERS": {
    "BASIS": {"TYPE": "STRING", "PATH": ["!"], "DESCRIPTION": "Base (nom Basis Set Exchange ou ORCA)."},
    "DISPERSION": {"TYPE": "CHOICE", "VALUES": ["D3ZERO", "D3BJ", "D4"], "ARGUMENTS": {
      "D3BJ": {"TYPE": "FLAG", "CANONICAL": "D3(BJ)"},
      "D4":   {"TYPE": "FLAG", "CANONICAL": "D4"}
    }},
    "INTEGRAL_APPROXIMATION": {"TYPE": "CHOICE", "VALUES": ["RIJ", "RIJK", "RIJCOSX"], "ARGUMENTS": {
      "RIJCOSX": {"TYPE": "FLAG", "CANONICAL": "RIJCOSX"}
    }}
  },
  "OUTPUT": {"FILES": {"orca.out": {}, "orca.engrad": {}, "orca.hess": {}, "orca.xyz": {}, "orca_trj.xyz": {}, "orca.property.txt": {}}}
}
```

> Point ouvert : la variante `B3LYP` du `doc.json` ORCA est liée à l'entrée `B3LYP5`
> du catalogue. Un utilisateur qui demande `method_args={"variant": "B3LYP"}` obtient le
> mot-clé ORCA `B3LYP`, c'est-à-dire VWN5. Il faut décider si la résolution des variantes
> doit passer par le catalogue (nom canonique → mot-clé du logiciel) ou rester
> spécifique au logiciel. **Ce choix dépasse cette proposition.**

---

### 3.2 Gaussian (`NAME = "GAUSSIAN"`)

#### Classe

```python
@register_software
class Gaussian(FileIOSoftware):
    NAME = "GAUSSIAN"
    ALIASES = ("G16",)  # <PLACEHOLDER: alias souhaités>
    DOC = Path(__file__).with_name("doc.json")
    composer_cls = GaussianComposer
    DRIVERS = (CclibDriver, AseGaussianDriver)

    def command(self, ctx):
        # g16 lit gaussian.com et écrit gaussian.log dans le répertoire courant.
        return [self.require_executable(ctx.exec_spec).path, "gaussian.com"]
```

- Environnement (`g16root`, `GAUSS_EXEDIR`, `GAUSS_SCRDIR`) : **uniquement** via `env`
  de `[software.GAUSSIAN]` ou `exec_spec.env`. `<PLACEHOLDER: liste minimale des
  variables requises par g16>`.
- `formchk` (production du `.fchk`) : exécutable séparé, avec une source explicite
  dédiée (`GAUSSIAN_FORMCHK_EXECUTABLE`). `<PLACEHOLDER: lancé dans collect, ou
  étape optionnelle activée par un paramètre>`.

#### Générateur d'input local

```
%nprocshared=<cpu>                          # INPUT.RESOURCES.CPU
%mem=<ram>MB                                # INPUT.RESOURCES.RAM
%chk=gaussian.chk
#p <variante>/<base> <module> EmpiricalDispersion=GD3BJ SCRF=(SMD,Solvent=Water) …

<titre : label AMAC>

<charge> <multiplicité>
<symboles et coordonnées en Å>
[Tv lignes si ase.Atoms.pbc]

[sections additionnelles : ModRedundant, charges ponctuelles, base Gen, …]

```

- Il hérite du futur `KeywordBlockComposer`. Sont propres à Gaussian : le Link 0
  (`%…=`), la route (`#p`), la ligne vide finale **obligatoire** et l'ordre des sections
  additionnelles.
- Option `KEYWORD(sous-options)` : `FORMAT` avec `"OPEN": "=("`, `"CLOSE": ")"` et
  `"SEPARATOR": ","`. `<PLACEHOLDER: vérifier que le vocabulaire FORMAT suffit, sinon
  étendre DOC_SCHEMA.md>`.

#### Parser local

| Fichier | Contenu lu |
|---|---|
| `gaussian.log` | `SCF Done`, énergies MP2/CC (`EUMP2`, `CCSD(T)=`), `Forces (Hartrees/Bohr)`, dipôle, charges Mulliken, géométrie `Standard orientation`, fréquences, états excités, `Normal termination` |
| `gaussian.fchk` | Hessienne (`Cartesian Force Constants`), gradient, charges, orbitales ; format structuré, préféré au `.log` quand il existe |
| `gaussian.chk` | non lu (binaire) |

#### Bibliothèques dédiées

Gaussian n'a pas de bibliothèque Python officielle.

| Driver | `REQUIRES` / `DISTRIBUTION` | `PHASES` | Rôle |
|---|---|---|---|
| `cclib` | `("cclib",)` / `cclib` | collect | lit `gaussian.log` (partagé avec ORCA) |
| `ase` | `("ase.io.gaussian",)` / `ase` | prepare, collect | `ase.io.gaussian.write_gaussian_in` et `read_gaussian_out` |
| `<PLACEHOLDER: nom>` | `<PLACEHOLDER>` | `<PLACEHOLDER>` | bibliothèque dédiée éventuelle (générateur de route, parser de fchk) |

> Attention : `ase` est une dépendance obligatoire d'AMAC, donc le driver `ase` est
> **toujours disponible**. Placé en tête de `DRIVERS`, il serait toujours choisi par
> `driver="auto"`. D'où l'ordre proposé : `cclib`, puis `ase`.

#### Capacités Gaussian (doc.json ∩ catalogue)

Version de référence : `<PLACEHOLDER: Gaussian 16 Rev. C.01>`.

- **Méthodes**
  - `HF` ✓.
  - `DFT` : SVWN5 ✓, SPW92 ?, PBE ✓ (`PBEPBE`), PBEsol ?, BLYP ✓, BP86 ✓
    (`<PLACEHOLDER: composante locale P86 selon Gaussian>`), PW91 ✓ (`PW91PW91`),
    TPSS ✓ (`TPSSTPSS`).
  - Hybrides : **B3LYP ✓ (VWN3, définition du catalogue)**, B3PW91 ✓, PBE0 ✓
    (`PBE1PBE`), TPSSh ✓, M06 ✓, M06-2X ✓, CAM-B3LYP ✓, wB97X-D ✓ (`wB97XD`),
    HSE06 ✓ (`HSEH1PBE`), B2PLYP ✓.
  - Absents : SCAN, r2SCAN, wB97X-V (—) ; B3LYP5 — (`<PLACEHOLDER: possible par
    IOp, non exposé>`).
  - `MOLLER_PLESSET` : MP2 ✓, MP3 ✓, MP4 ✓ (`MP4(SDTQ)`), SCS-MP2 ? (IOp),
    SOS-MP2 —.
  - `COUPLED_CLUSTER` : CCSD ✓, CCSD(T) ✓, QCISD ✓, QCISD(T) ✓, EOM-CCSD ✓ ;
    CC2 et CCSDT : —.
  - `CONFIGURATION_INTERACTION` : CIS ✓, CISD ✓, FCI —.
  - `MULTIREFERENCE` : CASSCF ✓ (`CAS(n,m)`) ; CASPT2, NEVPT2 et MRCI : —
    (CASMP2 n'est pas CASPT2 et n'est pas dans le catalogue).
  - `SEMIEMPIRICAL` : MNDO ✓, AM1 ✓, PM3 ✓, PM6 ✓, PM7 ✓.
  - `DFTB` ? : mot-clé `DFTB`/`DFTBA`, `<PLACEHOLDER: ordre (DFTB2 ou DFTB3) et
    équivalence, probablement APPROX>`. `XTB` —.
- **Modules** : SINGLE_POINT ✓ (`SP`), GRADIENT ✓ (`Force`), GEOMETRY_OPTIMISATION ✓,
  TRANSITION_STATE_SEARCH ✓ (`Opt=TS`, `QST2`/`QST3`), IRC ✓, PES_SCAN ✓ (`Scan`,
  `Opt=ModRedundant`), FREQUENCIES ✓, HESSIAN ≈ (via `Freq`, `.fchk`),
  MOLECULAR_DYNAMICS ✓ (`BOMD` ; `ADMP` hors catalogue), ORBITAL_PLOT ✓ (utilitaire
  `cubegen`, source explicite). NEB, ELECTRON_DYNAMICS, ELECTRON_TRANSPORT,
  EXTERNAL_DRIVER et PHONONS : —.
- **Options**
  - `REFERENCE` : RESTRICTED ✓, UNRESTRICTED ✓, RESTRICTED_OPEN ✓, GENERALISED ✓
    (`GHF`/`GKS`).
  - `INTEGRAL_APPROXIMATION` : RI-J ✓ (`DensityFit`) ; RI-JK et RIJCOSX : —.
    `LOCAL_CORRELATION` —.
  - `DISPERSION` : D2 ✓ (`GD2`), D3(0) ✓ (`GD3`), D3(BJ) ✓ (`GD3BJ`), les autres : —.
  - `SOLVATION` : PCM ✓ (`IEFPCM`, défaut de `SCRF`), CPCM ✓, SMD ✓, les autres : —.
  - `EXCITED_STATES` : LR-TDDFT ✓ (`TD`), TDA ✓ (`TDA`), DELTA-SCF ? (`Guess=Alter`,
    probablement APPROX) ; PP-RPA et REKS : —.
  - `SMEARING` : FERMI_DIRAC ? (`SCF=Fermi`, PBC), les autres : —.
  - `ELECTRIC_FIELD` ✓ (`Field=`), `POINT_CHARGES` ✓ (`Charge`).
  - `KPOINTS` — (PBC sans contrôle utilisateur des k-points), `HUBBARD_U` —,
    `SPIN_ORBIT_COUPLING` —.

---

### 3.3 DFTB+ (`NAME = "DFTBP"`)

Le `doc.json` (DFTB+ 25.1) existe dans `HEAD` mais est **supprimé dans l'arbre de
travail** (`git status` : `D amac/assets/dftbplus/doc.json`), alors que `dftbplus.py`
le référence toujours. Il faut le restaurer tel quel : ses liens `CANONICAL` sont déjà
conformes à cette proposition.

#### Classe

```python
@register_software
class DftbPlus(FileIOSoftware):
    NAME = "DFTBP"
    ALIASES = ("DFTB+",)
    DOC = Path(__file__).with_name("doc.json")
    composer_cls = DftbPlusComposer
    DRIVERS = (DftbPlusApiDriver, HsdDriver, AseDftbDriver)

    def command(self, ctx):
        return [self.require_executable(ctx.exec_spec).path]  # lit dftb_in.hsd

    def stdout_file(self, ctx):
        return Path("dftb.out")  # à ajouter dans OUTPUT.FILES
```

- `DFTB_PREFIX` et `DFTBPLUS_PARAM_DIR` ne viennent que de `env` (déjà l'exemple du
  README).
- Programmes séparés `modes`, `phonons` et `waveplot` (`TARGET: "EXTERNAL_PROGRAM"`) :
  chacun a sa source explicite (`DFTBP_MODES_EXECUTABLE`, …). Il faut un mécanisme de
  **commandes successives dans un même run**, absent du socle
  (`<PLACEHOLDER: command() renvoyant plusieurs commandes, ou module chaîné hors cœur>`).

#### Générateur d'input local

- Il hérite du futur `TreeComposer`. Le rendu HSD découle directement de l'`InputTree`
  (`FORMAT_DEFAULTS` du `doc.json` : `" = "`, `{ }`, `Yes/No`, `[unit]`).
- Géométrie : bloc `Geometry = GenFormat { … }`, écrit depuis `ase.Atoms`
  (`ase.io.write(format="gen")` vers une chaîne, ou rendu interne).
- Le composer ajoute `Options { WriteResultsTag = Yes }` si l'utilisateur ne l'a pas
  fourni, car le parser local en a besoin. `<PLACEHOLDER: injection dans le composer,
  ou REQUIRES/SETS dans le doc.json>`.
- `ParserOptions { StopAfterParsing = Yes }` permet de valider le composer contre
  `dftb_pin.hsd` dans les tests d'intégration.

#### Parser local

| Fichier | Contenu lu |
|---|---|
| `results.tag` | énergie totale, énergie libre de Mermin, forces, contraintes, valeurs propres, charges ; format `nom :type:rang:forme` puis valeurs |
| `detailed.out` | charges de Mulliken, dipôle, niveau de Fermi, décomposition de l'énergie |
| `band.out` | valeurs propres, occupations par k-point et spin |
| `geo_end.gen` / `geo_end.xyz` | géométrie finale, trajectoire MD |
| `hessian.out`, `born.out` | Hessienne, charges de Born |
| `md.out` | énergies et température le long de la trajectoire |
| `EXC.DAT` | énergies d'excitation, forces d'oscillateur |

#### Bibliothèques dédiées

| Driver | `REQUIRES` / `DISTRIBUTION` | `PHASES` | Rôle |
|---|---|---|---|
| `dftbplus-api` | `("dftbplus",)` / `<PLACEHOLDER: fourni avec DFTB+ (tools/pythonapi), absent de PyPI ?>` | run, collect | AMAC écrit `dftb_in.hsd` ; l'API (`dftbplus.DftbPlus(libpath=…, hsdpath=…)`) lance le calcul en processus et fournit `get_energy()`, `get_gradients()`, `get_gross_charges()` |
| `hsd` | `("hsd",)` / `hsd-python` | prepare | `ctx.metadata["input_tree"]` → dict → `hsd.dump()` ; `SUPPORTS_RAW = True` (fusion du dict `raw`) |
| `ase` | `("ase.calculators.dftb",)` / `ase` | collect | lecture de `results.tag` par ASE `<PLACEHOLDER: API publique ou interne ?>` |

- `dftbplus-api` : le chemin de `libdftbplus.so` est **explicite**, lu dans
  `execution_settings()["env"]["DFTBP_LIBRARY"]` (donc `env` du fichier de
  configuration ou `exec_spec.env`). Absent, `check_environment` renvoie une raison.
  `SUPPORTED_SETTINGS = {"env"}`. `<PLACEHOLDER: prise en compte de cpu, puisque
  OMP_NUM_THREADS doit être fixé avant le chargement de la bibliothèque>`.
- Pour les tests, prévoir que `ase` reste disponible (voir la remarque du §3.2 sur
  l'ordre).

#### Capacités DFTB+ (liens `CANONICAL` du doc.json 25.1)

- **Méthodes**
  - `DFTB` : DFTB1 ✓, DFTB2 ✓, DFTB3 ✓, MDFTB ✓, LC-DFTB ✓, GLOBAL-HYBRID-DFTB ✓,
    CAM-DFTB ✓.
  - `XTB` (tblite) : GFN1-xTB ✓, GFN2-xTB ✓, IPEA1-xTB ✓, GFN0-xTB —.
  - Les autres familles : —.
- **Modules** : SINGLE_POINT ✓, GEOMETRY_OPTIMISATION ✓, HESSIAN ✓
  (`SecondDerivatives`), FREQUENCIES ≈ (`modes`, sans thermochimie),
  MOLECULAR_DYNAMICS ✓, ELECTRON_DYNAMICS ✓, ELECTRON_TRANSPORT ✓, EXTERNAL_DRIVER ✓
  (`Socket`), PHONONS ✓, ORBITAL_PLOT ✓ (`waveplot`), GRADIENT ≈
  (`Analysis { Printforces = Yes }`, **lien à ajouter**). TRANSITION_STATE_SEARCH, IRC,
  NEB et PES_SCAN : —.
- **Options**
  - `DISPERSION` : LENNARD_JONES ✓, SLATER_KIRKWOOD ✓, D3(BJ) ✓, D3(0) ✓, D3M(BJ) ✓,
    D4 ✓, TS ✓, MBD ✓ ; D2 et VV10 : —.
  - `SOLVATION` : GB ✓, COSMO ✓, SASA ✓, ALPB ? (option du bloc `GeneralisedBorn`,
    absente du doc.json).
  - `EXCITED_STATES` : LR-TDDFT ✓, PP-RPA ✓, DELTA-SCF ✓, REKS ✓, TDA —.
  - `SMEARING` : FERMI_DIRAC ✓, METHFESSEL_PAXTON ✓, GAUSSIAN_SMEARING ✓,
    MARZARI_VANDERBILT —.
  - `KPOINTS` : EXPLICIT_KPOINTS ✓, MONKHORST_PACK ≈ (repliement diagonal), BAND_PATH ✓,
    GAMMA_ONLY ≈ (liste explicite `0 0 0 1`, lien à ajouter).
  - `REFERENCE` : UNRESTRICTED ✓ (`Colinear`), GENERALISED ✓ (`NonColinear`),
    RESTRICTED ≈ (absence de `SpinPolarisation`, aucun nœud à lier aujourd'hui),
    RESTRICTED_OPEN —.
  - `HUBBARD_U` : FLL ✓, AMF —.
  - `SPIN_ORBIT_COUPLING` ✓, `ELECTRIC_FIELD` ✓, `POINT_CHARGES` ✓.

Nœuds du doc.json actuel **sans `CANONICAL`**, à retirer des capacités exposées
(principe 4) ou à faire entrer dans le catalogue : `SETUPGEOM`, `EXTERNAL_ASI`, la
variante `pSIC` de `ORBITAL_POTENTIAL`. Les paramètres purement logiciels (`MIXER`,
`SOLVER`, `OPTIONS`, …) ne sont pas des capacités et restent sans lien.

---

### 3.4 deMonNano (`NAME = "DEMON"`) : bibliothèque Python uniquement

deMonNano n'a **ni composer ni parser local**. Deux solutions :

**A. `InProcessSoftware` qui délègue à la bibliothèque (recommandée, sans changement
du socle)**

```python
@register_software
class DeMonNano(InProcessSoftware):
    NAME = "DEMON"
    ALIASES = ("deMonNano",)
    DOC = Path(__file__).with_name("doc.json")   # SYNTAX "API", EXECUTION ["INPROCESS"]
    LIBRARY = "<PLACEHOLDER: nom du module Python>"
    DISTRIBUTION = "<PLACEHOLDER: nom du paquet pip>"

    def check_environment(self):
        # Contrôle sans import, comme Driver.missing_modules.
        if importlib.util.find_spec(self.LIBRARY) is None:
            raise RunError(f"deMonNano requires {self.LIBRARY} (pip install {self.DISTRIBUTION})")

    def build(self, ctx):
        import <PLACEHOLDER: module>                       # import dans la phase seulement
        tree = translate(ctx.spec, load_schema(self.DOC))  # l'input_tree n'est posé que pour un driver
        ctx.objects["demonnano.calc"] = <PLACEHOLDER: construction depuis tree et ctx.atoms>

    def compute(self, ctx):
        ctx.objects["demonnano.calc"].<PLACEHOLDER: run()>

    def collect(self, ctx):
        ctx.objects[OUTPUT_KEY] = DemonNanoOutput.from_library(ctx.objects["demonnano.calc"])
```

- `ctx.metadata["input_tree"]` n'est rempli par `AMAC` que si un driver est choisi
  (`amac.py`, `_context`). `build()` appelle donc `translate()` lui-même. On peut aussi
  étendre le socle pour poser l'arbre pour toute software ayant un `doc.json`.
- `Software.check_environment()` existe mais **n'est appelé nulle part** aujourd'hui.
  Il faut l'appeler dans `AMAC.__init__`, sinon une bibliothèque absente n'échoue qu'au
  premier `execute()`, en `RunError`.
- Si la bibliothèque écrit des fichiers et lance un binaire deMon, son exécutable est
  passé explicitement à la bibliothèque (`resolve_executable`, `DEMON_EXECUTABLE`).
  Mettre alors `REQUIRES_EXECUTABLE = True`. `<PLACEHOLDER: la bibliothèque est-elle
  un binding en processus ou un wrapper de fichiers ?>`
- Handlers : lecture de `ctx.objects[OUTPUT_KEY]`, sans `drivers=` puisqu'il n'y a qu'un
  chemin.

**B. `FileIOSoftware` sans chemin AMAC et driver unique obligatoire.** Il faudrait un
attribut du socle (`DEFAULT_DRIVER`, ou `AMAC_PATH = False`) pour que `driver="amac"`
soit refusé et que le driver devienne le défaut. C'est plus cohérent avec « bibliothèque
= driver », mais cela change `select_driver` et la documentation. **Non recommandée
pour l'instant.**

L'exemple `examples/usage/05_facade_workstation.py` configure un `executable` pour
deMonNano : à revoir selon la réponse au placeholder ci-dessus.

#### Capacités deMonNano (à confirmer entièrement)

Version de référence : `<PLACEHOLDER>`.

- **Méthodes** : `DFTB` : DFTB1 ✓, DFTB2 ✓, DFTB3 ?, MDFTB —, LC-DFTB —,
  GLOBAL-HYBRID-DFTB —, CAM-DFTB —. Les autres familles : —.
- **Modules** : SINGLE_POINT ✓, GRADIENT ?, GEOMETRY_OPTIMISATION ✓,
  MOLECULAR_DYNAMICS ✓, FREQUENCIES ?, HESSIAN ?. Les autres : —. (La dynamique à
  échange de répliques est hors catalogue.)
- **Options** : `DISPERSION` `<PLACEHOLDER: variante réellement implémentée>`,
  `SMEARING` FERMI_DIRAC ? (occupations fractionnaires), `POINT_CHARGES` ? (QM/MM),
  `REFERENCE` RESTRICTED ✓ / UNRESTRICTED ?, `EXCITED_STATES` ? (le CI-DFTB de
  deMonNano ne correspond à aucune variante du catalogue), `ELECTRIC_FIELD` ?.
  `KPOINTS`, `HUBBARD_U` et `SPIN_ORBIT_COUPLING` : —.

---

## 4. Récapitulatif des drivers

| Logiciel | `"amac"` (local) | Drivers (ordre `"auto"`) | Phases |
|---|---|---|---|
| ORCA | composer + parser | `opi` · `opi-parser` · `cclib` | P+R+C · C · C |
| Gaussian | composer + parser | `cclib` · `ase` · `<PLACEHOLDER>` | C · P+C · ? |
| DFTB+ | composer + parser | `dftbplus-api` · `hsd` · `ase` | R+C · P · C |
| deMonNano | — (bibliothèque dans la classe) | aucun | — |

P = prepare, R = run, C = collect.

Combinaisons « input bibliothèque + parser local » : `hsd` pour DFTB+, `ase` pour
Gaussian (qui collecte aussi avec ASE ; un driver `ase-writer` limité à `prepare`
serait nécessaire pour garder le parser local). Pour ORCA, `opi` couvre les trois
phases ; `<PLACEHOLDER: ajouter un opi-writer (prepare seul) si le besoin existe>`.

Dépendances optionnelles, à déclarer dans `pyproject.toml` (le README cite un
`requirements-optional.txt`, supprimé) :

```toml
[project.optional-dependencies]
orca = ["orca-pi"]
parsers = ["cclib"]
dftbplus = ["hsd-python"]           # l'API dftbplus est installée avec DFTB+
demonnano = ["<PLACEHOLDER>"]
```

---

## 5. Matrice des capacités (catalogue × logiciel)

Légende : ✓ exact · ≈ approché · ? à confirmer · — non supporté.

### Méthodes

| Famille | Variante | ORCA | Gaussian | DFTB+ | deMonNano |
|---|---|:-:|:-:|:-:|:-:|
| HF | — | ✓ | ✓ | — | — |
| DFT | SVWN5 | ✓ | ✓ | — | — |
| | SPW92 | ✓ | ? | — | — |
| | PBE | ✓ | ✓ | — | — |
| | PBEsol | ? | ? | — | — |
| | BLYP | ✓ | ✓ | — | — |
| | BP86 | ✓ | ✓ | — | — |
| | PW91 | ✓ | ✓ | — | — |
| | TPSS | ✓ | ✓ | — | — |
| | SCAN | ✓ | — | — | — |
| | r2SCAN | ✓ | — | — | — |
| | B3LYP (VWN3) | ✓ `B3LYP/G` | ✓ | — | — |
| | B3LYP5 (VWN5) | ✓ `B3LYP` | — | — | — |
| | B3PW91 | ✓ | ✓ | — | — |
| | PBE0 | ✓ | ✓ | — | — |
| | TPSSh | ✓ | ✓ | — | — |
| | M06 | ✓ | ✓ | — | — |
| | M06-2X | ✓ | ✓ | — | — |
| | CAM-B3LYP | ✓ | ✓ | — | — |
| | wB97X-D | ? | ✓ | — | — |
| | wB97X-V | ✓ | — | — | — |
| | HSE06 | ? | ✓ | — | — |
| | B2PLYP | ✓ | ✓ | — | — |
| MOLLER_PLESSET | MP2 | ✓ | ✓ | — | — |
| | SCS-MP2 | ✓ | ? | — | — |
| | SOS-MP2 | ✓ | — | — | — |
| | MP3 | ? | ✓ | — | — |
| | MP4 | — | ✓ | — | — |
| COUPLED_CLUSTER | CC2 | — | — | — | — |
| | CCSD | ✓ | ✓ | — | — |
| | CCSD(T) | ✓ | ✓ | — | — |
| | CCSDT | ? | — | — | — |
| | QCISD | ✓ | ✓ | — | — |
| | QCISD(T) | ✓ | ✓ | — | — |
| | EOM-CCSD | ✓ | ✓ | — | — |
| CONFIGURATION_INTERACTION | CIS | ✓ | ✓ | — | — |
| | CISD | ? | ✓ | — | — |
| | FCI | ? | — | — | — |
| MULTIREFERENCE | CASSCF | ✓ | ✓ | — | — |
| | CASPT2 | ✓ | — | — | — |
| | NEVPT2 | ✓ | — | — | — |
| | MRCI | ✓ | — | — | — |
| SEMIEMPIRICAL | MNDO | ? | ✓ | — | — |
| | AM1 | ? | ✓ | — | — |
| | PM3 | ? | ✓ | — | — |
| | PM6 | — | ✓ | — | — |
| | PM7 | — | ✓ | — | — |
| XTB | GFN0-xTB | ? | — | — | — |
| | GFN1-xTB | ✓ | — | ✓ | — |
| | GFN2-xTB | ✓ | — | ✓ | — |
| | IPEA1-xTB | — | — | ✓ | — |
| DFTB | DFTB1 | — | ? | ✓ | ✓ |
| | DFTB2 | — | ? | ✓ | ✓ |
| | DFTB3 | — | ? | ✓ | ? |
| | MDFTB | — | — | ✓ | — |
| | LC-DFTB | — | — | ✓ | — |
| | GLOBAL-HYBRID-DFTB | — | — | ✓ | — |
| | CAM-DFTB | — | — | ✓ | — |

### Modules

| Module | ORCA | Gaussian | DFTB+ | deMonNano |
|---|:-:|:-:|:-:|:-:|
| SINGLE_POINT | ✓ | ✓ | ✓ | ✓ |
| GRADIENT | ✓ | ✓ | ≈ | ? |
| GEOMETRY_OPTIMISATION | ✓ | ✓ | ✓ | ✓ |
| TRANSITION_STATE_SEARCH | ✓ | ✓ | — | — |
| IRC | ✓ | ✓ | — | — |
| NEB | ✓ | — | — | — |
| PES_SCAN | ✓ | ✓ | — | — |
| FREQUENCIES | ✓ | ✓ | ≈ | ? |
| HESSIAN | ≈ | ≈ | ✓ | ? |
| MOLECULAR_DYNAMICS | ✓ | ✓ | ✓ | ✓ |
| ELECTRON_DYNAMICS | — | — | ✓ | — |
| ELECTRON_TRANSPORT | — | — | ✓ | — |
| EXTERNAL_DRIVER | — | — | ✓ | — |
| ORBITAL_PLOT | ✓ | ✓ | ✓ | ? |
| PHONONS | — | — | ✓ | — |

### Options

| Axe | Valeur | ORCA | Gaussian | DFTB+ | deMonNano |
|---|---|:-:|:-:|:-:|:-:|
| REFERENCE | RESTRICTED | ✓ | ✓ | ≈ | ✓ |
| | UNRESTRICTED | ✓ | ✓ | ✓ | ? |
| | RESTRICTED_OPEN | ✓ | ✓ | — | — |
| | GENERALISED | — | ✓ | ✓ | — |
| INTEGRAL_APPROXIMATION | RI-J | ✓ | ✓ | — | — |
| | RI-JK | ✓ | — | — | — |
| | RIJCOSX | ✓ | — | — | — |
| LOCAL_CORRELATION | DLPNO | ✓ | — | — | — |
| | LPNO | ? | — | — | — |
| DISPERSION | D2 | ✓ | ✓ | — | ? |
| | D3(0) | ✓ | ✓ | ✓ | ? |
| | D3(BJ) | ✓ | ✓ | ✓ | ? |
| | D3M(BJ) | ? | — | ✓ | — |
| | D4 | ✓ | — | ✓ | — |
| | TS | — | — | ✓ | — |
| | MBD | — | — | ✓ | — |
| | VV10 | ✓ | — | — | — |
| | LENNARD_JONES | — | — | ✓ | ? |
| | SLATER_KIRKWOOD | — | — | ✓ | ? |
| SOLVATION | PCM | — | ✓ | — | — |
| | CPCM | ✓ | ✓ | — | — |
| | SMD | ✓ | ✓ | — | — |
| | COSMO | — | — | ✓ | — |
| | GB | — | — | ✓ | — |
| | ALPB | ≈ | — | ? | — |
| | SASA | — | — | ✓ | — |
| EXCITED_STATES | LR-TDDFT | ✓ | ✓ | ✓ | ? |
| | TDA | ✓ | ✓ | — | — |
| | PP-RPA | — | — | ✓ | — |
| | DELTA-SCF | ? | ? | ✓ | — |
| | REKS | — | — | ✓ | — |
| SMEARING | FERMI_DIRAC | ✓ | ? | ✓ | ? |
| | GAUSSIAN_SMEARING | — | — | ✓ | — |
| | METHFESSEL_PAXTON | — | — | ✓ | — |
| | MARZARI_VANDERBILT | — | — | — | — |
| KPOINTS | MONKHORST_PACK | — | — | ≈ | — |
| | GAMMA_ONLY | — | — | ≈ | — |
| | EXPLICIT_KPOINTS | — | — | ✓ | — |
| | BAND_PATH | — | — | ✓ | — |
| HUBBARD_U | FLL | — | — | ✓ | — |
| | AMF | — | — | — | — |
| SPIN_ORBIT_COUPLING | — | ✓ | — | ✓ | — |
| ELECTRIC_FIELD | — | ✓ | ✓ | ✓ | ? |
| POINT_CHARGES | — | ✓ | ✓ | ✓ | ? |

Contrôle automatique proposé : un test `test/test_capabilities.py` qui
1. vérifie que chaque entrée de premier niveau et chaque variante de `METHODS` et
   `MODULES` de chaque `doc.json` porte un `CANONICAL` (principe 4) ;
2. compare `catalog.links(schema)` à une matrice attendue
   (`test/fixtures/capabilities.json`), pour qu'aucune capacité n'apparaisse ou ne
   disparaisse sans le vouloir.

---

## 6. Changements du socle induits

| Changement | Nécessaire pour | Priorité |
|---|---|---|
| Implémenter `KeywordBlockComposer` et `TreeComposer` (rendu commun) | chemin local ORCA, Gaussian, DFTB+ | haute |
| Décider de la source de la charge et de la multiplicité (spec ou `Atoms`) | les quatre composers | haute |
| Appeler `Software.check_environment()` à la création du calculateur | deMonNano (bibliothèque absente) | moyenne |
| Poser `ctx.metadata["input_tree"]` pour toute software avec `doc.json` | deMonNano, simplification | basse |
| Commandes successives dans un run (`modes`, `formchk`, `orca_plot`) | FREQUENCIES DFTB+, `.fchk` Gaussian, ORBITAL_PLOT | moyenne |
| Résolution des variantes via le catalogue (B3LYP ORCA/Gaussian) | cohérence inter-logiciels | à discuter |
| Extension de `FORMAT` pour `Mot=(a,b)` | Gaussian | à vérifier |

## 7. Ordre de mise en œuvre suggéré

1. Restaurer `amac/assets/dftbplus/doc.json` ; écrire `dftbplus/parser.py` et ses
   tests sur fixtures (aucun binaire requis).
2. Implémenter `TreeComposer`, puis `DftbPlusComposer`, et valider contre
   `dftb_pin.hsd`.
3. Écrire les handlers communs DFTB+, puis les drivers `hsd` et `dftbplus-api`.
4. ORCA : `doc.json` (capacités ✓ du §5), `KeywordBlockComposer`, parser, driver `opi`.
5. Gaussian : `doc.json`, composer (spécificités Link 0 et route), parser, drivers
   `cclib` et `ase`.
6. deMonNano : lever les placeholders de la bibliothèque, puis appliquer la solution A.
7. Test de capacités (§5) et mise à jour du README et de `examples/usage/`.
