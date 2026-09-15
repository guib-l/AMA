# AMAC — Récapitulatif de planification

> État : **étape 1.2 terminée** (inventaire des bibliothèques Python).
> Les sections 3 (JSON par logiciel) et 4 (équivalences méthodes/modules) seront ajoutées
> après validation de cette étape.

---

## 0. Périmètre

Sept codes retenus pour la première itération :

| Code | Type | Domaine | Licence |
|---|---|---|---|
| DFTB+ | tight-binding (DFTB, xTB) | molécules + périodique | libre (LGPL) |
| Gaussian | ondes atomiques (GTO) | molécules | commercial |
| ORCA | ondes atomiques (GTO) | molécules (+ périodique limité) | gratuit académique, fermé |
| pySCF | ondes atomiques (GTO) | molécules + périodique | libre (Apache-2), **natif Python** |
| Quantum Espresso | ondes planes + PP | périodique | libre (GPL) |
| Abinit | ondes planes + PAW/PP | périodique | libre (GPL) |
| GPAW | PW / LCAO / grille réelle, PAW | périodique + molécules | libre (GPL), **natif Python** |

Deux familles très différentes cohabitent : la **chimie quantique moléculaire** (Gaussian,
ORCA, pySCF) et la **physique de l'état solide** (QE, Abinit, GPAW), avec DFTB+ à cheval.
C'est la principale difficulté d'unification (cf. §5).

---

## 1. Les trois couches de l'écosystème Python

L'écosystème existant se répartit en trois couches. AMAC devra choisir sur laquelle
il se branche — voir la recommandation §5.

### Couche A — Frameworks unificateurs (déjà « multi-codes »)

| Bibliothèque | Rôle | Codes couverts (parmi les 7) | Intérêt pour AMAC |
|---|---|---|---|
| **ASE** (Atomic Simulation Environment) | objet `Atoms` + `Calculator` unifié, écriture d'input / lecture d'output, optimiseurs, MD, NEB, phonons | DFTB+, Gaussian, ORCA, QE, Abinit, GPAW (pySCF hors ASE officiel) | ⭐ Pivot naturel : déjà dans `requirements.txt`, couvre 6/7 |
| **quacc** (Quantum Accelerator) | « recettes » de haut niveau au-dessus d'ASE, branchées sur des moteurs de workflow (Covalent, Parsl, Jobflow, Dask, Prefect, Redun) | ORCA, Gaussian, QE, GPAW, DFTB+, psi4, VASP, xTB… | Référence de conception : c'est le projet le plus proche de l'objectif d'AMAC |
| **AiiDA** + plugins (`aiida-quantumespresso`, `aiida-abinit`, `aiida-gaussian`, `aiida-orca`, `aiida-dftbp`) | provenance, base de données, workflows HPC | QE (très mature), Abinit, Gaussian, ORCA, DFTB+ | Très lourd (PostgreSQL, RabbitMQ, démon). À écarter comme dépendance |
| **QCEngine / QCElemental (QCSchema, MolSSI)** | schéma JSON normalisé d'un calcul (`AtomicInput`/`AtomicResult`) + exécuteurs | Psi4, NWChem, GAMESS, CFOUR, Turbomole, TeraChem, MOPAC, xtb… (pas ORCA/Gaussian/QE/Abinit officiellement) | ⭐ Le **schéma** est excellent à réutiliser comme modèle de données ; les harnesses, non |
| **pymatgen** (`pymatgen.io.*`) | I/O matériaux : `io.gaussian`, `io.abinit`, `io.pwscf` (QE), `io.xyz` | Gaussian, Abinit, QE | Utile en dépannage de parsing |
| **cclib** (v1.8.1) | **parser d'output** unifié, ~16 codes, attributs normalisés (`scfenergies`, `moenergies`, `vibfreqs`, `etenergies`, `atomcoords`…) | Gaussian, ORCA (+ Psi4, NWChem, Molpro, Molcas, Q-Chem, GAMESS, ADF, Turbomole, DALTON, MOPAC…) | ⭐ À adopter tel quel pour Gaussian/ORCA côté lecture |

### Couche B — Interfaces natives / officielles par code

| Code | Interface Python officielle | Statut |
|---|---|---|
| **pySCF** | *est* une bibliothèque Python | Natif, rien à écrire |
| **GPAW** | `gpaw.GPAW` est directement un calculateur ASE | Natif |
| **ORCA** | **OPI** — ORCA Python Interface (`pip install orca-pi`), par FACCTs, introduit avec ORCA 6.1 : construction d'input typée + lecture des sorties JSON (`orca_2json`) | ⭐ Nouveauté majeure, à privilégier pour ORCA ≥ 6.1 |
| **DFTB+** | API `ctypes` sur `libdftbplus` (classe `DftbPlus`, calcul en mémoire) + **`hsd-python`** (paquet `hsd`, lecture/écriture du format HSD) + `dptools` (bandes, DOS, format `.gen`) | Officiel (dépôt dftbplus). L'API ctypes exige DFTB+ compilé avec son API |
| **Abinit** | **AbiPy** (dépôt abinit) : génération d'input, lecture des NetCDF, flows | Officiel de fait, très complet, mais lourd (dépend de pymatgen) |
| **Quantum Espresso** | aucune API officielle. Écosystème : `qeschema` (XSD officiel du XML de sortie), `qe-tools`, `xespresso`, `postqe`, `pwtools` | Fragmenté |
| **Gaussian** | aucune API Python. Uniquement des parsers tiers | — |

### Couche C — Utilitaires transverses

- **`ccinput`** : générateur d'input multi-codes (Gaussian, ORCA, xtb, Q-Chem, NWChem, Psi4) — approche très proche de l'objectif AMAC côté écriture.
- **`geometric` / `pyberny` / `Sella`** : optimiseurs de géométrie externes, utilisables sur n'importe quel calculateur (utile pour offrir un module « optimisation » homogène quand le code ne le fait pas).
- **`dftd3` / `dftd4` (simple-dftd3, dftd4)** : dispersions D3/D4 en bibliothèque, avec API Python et interfaces ASE/QCSchema.
- **`iodata`** (HORTON) : conversion de formats de fonctions d'onde (fchk, molden, wfn…).
- **`ase.io`** : lecture/écriture de ~100 formats géométriques (gen, xyz, cif, POSCAR, cube, molden…).

---

## 2. Détail par logiciel

### 2.1 DFTB+
- **ASE** : `ase.calculators.dftb.Dftb` — `FileIOCalculator`. Écrit `dftb_in.hsd` + `geo_end.gen`, lit `detailed.out` / `results.tag`. Les mots-clés HSD sont aplatis en arguments Python : `Hamiltonian_SCC='Yes'`, `Hamiltonian_MaxAngularMomentum_C='"p"'`. Nécessite `DFTB_PREFIX` (jeux Slater-Koster) et une commande/profil.
- **Officiel** : `hsd` (hsd-python) pour manipuler l'HSD proprement (dict ⇄ HSD) ; API `ctypes` `DftbPlus` pour piloter `libdftbplus` en mémoire ; `dptools` pour les post-traitements.
- **Parsing** : pas de support cclib. `detailed.out`, `band.out`, `results.tag` → parser maison ou ASE.
- **Recommandation AMAC** : composer l'input via `hsd` (arbre de dict → HSD), exécuter en file-IO, lire via ASE + parser maison de `detailed.out`. Le manuel PDF (`dftbplus_manual.pdf`) fournit l'arborescence complète des blocs pour l'étape 3.

### 2.2 Gaussian
- **ASE** : `ase.calculators.gaussian.Gaussian` (route section construite depuis les kwargs : `method`, `basis`, `xc`, plus mots-clés libres) et `GaussianOptimizer` / `GaussianIRC` pour déléguer l'optimisation à Gaussian. `ase.io.gaussian` lit le `.log`.
- **Parsing** : **cclib** (le plus complet), `pymatgen.io.gaussian.GaussianOutput`.
- **Écriture** : ASE, `ccinput`, `pymatgen.io.gaussian.GaussianInput`.
- **Recommandation AMAC** : écriture maison (la « route section » est une simple chaîne `#p method/basis mots-clés`, facile à générer et à contrôler finement) + lecture par cclib.

### 2.3 ORCA
- **ASE** : `ase.calculators.orca.ORCA` — wrapper volontairement minimal : `orcasimpleinput` (la ligne `!`) et `orcablocks` (les blocs `%... end`) sont des **chaînes libres**. Aucune validation, aucune structure. Insuffisant pour l'objectif d'AMAC.
- **OPI** (`orca-pi`, ORCA ≥ 6.1) : modèles typés pour l'input, exécution, et lecture des résultats via le JSON produit par `orca_2json`. C'est la voie propre.
- **Parsing** : OPI (JSON), sinon **cclib** sur le `.out`.
- **Recommandation AMAC** : structurer nous-mêmes `simple keywords` / `blocs %` (c'est exactement le découpage Module / Méthode / Options du manifeste), avec OPI en option d'exécution/lecture si présent, cclib en repli.

### 2.4 pySCF
- Natif Python : `gto.Mole` / `pbc.gto.Cell`, puis `scf.RHF`, `dft.RKS`, `mp.MP2`, `cc.CCSD`, `mcscf.CASSCF`, `tdscf`… Pas de fichier d'input, pas de parser.
- **ASE** : `pyscf/pbc/tools/pyscf_ase.py` fournit la conversion `Atoms` ⇄ `Cell` et un calculateur minimal ; pas de calculateur officiel dans ASE.
- **Recommandation AMAC** : c'est le cas particulier structurant. pySCF impose que la couche d'abstraction AMAC produise un **objet de calcul**, pas seulement un fichier texte : il faut un backend in-process à côté du backend file-IO.

### 2.5 Quantum Espresso
- **ASE** : `ase.calculators.espresso.Espresso` — `GenericFileIOCalculator` + `EspressoProfile`. `input_data` est un dict imbriqué qui reproduit les namelists `&CONTROL / &SYSTEM / &ELECTRONS / &IONS / &CELL`, plus `pseudopotentials={'Si': 'Si.pbe-n-kjpaw.UPF'}` et `kpts`. `ase.io.espresso` lit/écrit `pw.in` / `pw.out`.
- Au-delà de `pw.x`, la chaîne d'outils (`ph.x`, `dos.x`, `projwfc.x`, `bands.x`, `neb.x`, `cp.x`) n'est **pas** couverte par ASE → c'est là qu'interviennent `qeschema` (parsing du XML `data-file-schema.xml`), `postqe`, ou quacc (recettes `ph.x`, `bands.x`, `dos.x`).
- **Recommandation AMAC** : namelists = dict imbriqué (mapping direct), `pw.x` via ASE, et un modèle « chaîne d'exécutables » pour le reste (à décider à l'étape 3).

### 2.6 Abinit
- **ASE** : `ase.calculators.abinit.Abinit` (`GenericFileIOCalculator` + `AbinitProfile`, `pp_paths`). Input à plat : variables Abinit (`ecut`, `ixc`, `nband`, `toldfe`, `ngkpt`…).
- **AbiPy** : génération d'input avec validation des variables, lecture des fichiers NetCDF (`GSR.nc`, `DDB`, `WFK`), flows de convergence. Le plus complet, mais entraîne pymatgen.
- **Recommandation AMAC** : input à plat très simple à générer nous-mêmes ; AbiPy en dépendance optionnelle pour la lecture NetCDF.

### 2.7 GPAW
- **Natif** : `from gpaw import GPAW, PW` puis `atoms.calc = GPAW(mode=PW(400), xc='PBE', kpts=...)`. C'est un calculateur ASE de plein droit, en mémoire (pas de fichier d'input), avec ses propres fichiers `.gpw`.
- **Recommandation AMAC** : même traitement que pySCF (backend in-process).

---

## 3. Matrice de synthèse

| | ASE calculator | Type d'exécution | API/lib officielle | Parser recommandé |
|---|---|---|---|---|
| DFTB+ | `Dftb` (FileIO) | fichier (HSD) ou API ctypes | `hsd`, `dptools`, ctypes | maison + ASE |
| Gaussian | `Gaussian` (FileIO) | fichier | — | **cclib** |
| ORCA | `ORCA` (GenericFileIO, chaînes libres) | fichier | **OPI** (`orca-pi`, ≥ 6.1) | OPI JSON / cclib |
| pySCF | non officiel (`pyscf_ase`) | **in-process** | pySCF lui-même | objets Python |
| Q. Espresso | `Espresso` (GenericFileIO) | fichier (namelists) | — (`qeschema`, `postqe`) | ASE + `qeschema` (XML) |
| Abinit | `Abinit` (GenericFileIO) | fichier (variables à plat) | **AbiPy** | ASE / AbiPy (NetCDF) |
| GPAW | natif | **in-process** | GPAW lui-même | objets Python |

Formats d'input à couvrir, par famille syntaxique — cela conditionne le `composer` :

1. **Ligne de mots-clés + blocs** : ORCA (`! ...` + `%bloc ... end`), Gaussian (route `#p ...` + Link0 `%mem`, `%nproc`).
2. **Arbre hiérarchique** : DFTB+ (HSD, imbrication arbitraire).
3. **Namelists Fortran** : Quantum Espresso (`&SYSTEM ... /` + cartes `ATOMIC_SPECIES`, `K_POINTS`).
4. **Variables à plat** : Abinit (`ecut 20`, avec suffixes de dataset `ecut2`).
5. **Aucun fichier** : pySCF, GPAW (appels Python).

Le `doc.json` actuel (`amac/assets/Orca/doc.json`) gère déjà les types `INLINE` et `BLOCK` :
il couvre la famille 1, il faudra l'étendre aux familles 2–4 (types `TREE`, `NAMELIST`, `FLAT`)
et prévoir un backend « API » pour la famille 5.

---

## 4. Ce qui existe / ce qu'il faudra écrire

**Réutilisable directement**
- `ase.Atoms` + `ase.io` comme objet moléculaire et I/O géométrique (déjà dans `requirements.txt`, cohérent avec `amac/base/`).
- `cclib` pour Gaussian et ORCA en lecture.
- `hsd` pour DFTB+ en écriture/lecture d'input.
- Le **schéma QCSchema** comme modèle du dictionnaire de résultats normalisé (`energy`, `gradient`, `hessian`, `properties`, `provenance`).

**À écrire dans AMAC**
- La **couche sémantique** : c'est le vrai apport. Aucune bibliothèque existante ne donne l'équivalence « B3LYP-D3/def2-TZVP » ⇄ mots-clés ORCA ⇄ route Gaussian ⇄ `xc` GPAW ⇄ `input_dft` QE. quacc et ASE s'arrêtent avant : ils uniformisent l'*exécution*, pas la *description physique du calcul*.
- Les `doc.json` par logiciel (étape 3) + `available_methods.json` / `available_modules.json` (étape 4).
- Les composers par famille syntaxique (5 au lieu de 7).
- Le backend in-process pour pySCF/GPAW.

**À écarter**
- AiiDA (infrastructure trop lourde pour une bibliothèque).
- QCEngine comme exécuteur (ne couvre pas nos codes) — mais son schéma est à reprendre.

---

## 5. Conséquences pour l'architecture AMAC

1. **Deux modes d'exécution obligatoires**, pas un seul : `FileIO` (DFTB+, Gaussian, ORCA, QE, Abinit) et `InProcess` (pySCF, GPAW). L'API `amac.calculator(...)` / `amac.run(image)` du manifeste reste identique ; c'est le backend (`amac/engine/`) qui diverge.
2. **ASE comme socle, pas comme façade** : on s'appuie sur `Atoms`, `ase.io` et les calculateurs quand ils suffisent, mais AMAC garde ses propres `doc.json` pour valider et composer les inputs — ASE ne valide rien pour ORCA et aplatit maladroitement le HSD de DFTB+.
3. **Séparation Module / Méthode / Options** (manifeste §3) : elle est justifiée par les codes eux-mêmes — le *module* correspond au `runtype` / `calculation` (`!Opt`, `#p Opt`, `calculation='relax'`, `Driver = GeometryOptimization`), la *méthode* au hamiltonien, les *options* au reste. C'est le découpage naturel des cinq familles syntaxiques.
4. **Résultats normalisés au format QCSchema-like**, quel que soit le backend.

---

## 6. Dépendances proposées

Aucune de ces bibliothèques n'est installée dans l'environnement courant
(`python 3.12.3`, seul le Python système : ni numpy, ni scipy, ni ase).
Rien n'a été installé ni téléchargé.

```
# noyau
numpy, scipy, ase

# lecture d'output
cclib            # Gaussian, ORCA

# optionnelles, par logiciel
hsd              # DFTB+ (input HSD)
orca-pi          # ORCA >= 6.1 (OPI)
pyscf            # backend in-process
gpaw             # backend in-process
abipy            # Abinit (NetCDF) — lourd
qeschema         # Quantum Espresso (XML de sortie)
```

## 7. Suite

- **Étape 3** — pour chaque logiciel : liste des modules, méthodes et options d'après la
  documentation, et construction du `doc.json` correspondant (format à figer avant de
  démarrer : le schéma actuel `amac/assets/Orca/doc.json` doit être étendu).
- **Étape 4** — `available_methods.json` et `available_modules.json` (équivalences entre
  logiciels), puis complément de ce récapitulatif avec le comparatif des différences.

---

### Sources

- [ASE — Calculators](https://ase-lib.org/ase/calculators/calculators.html) · [ASE — DFTB+](https://wiki.fysik.dtu.dk/ase/ase/calculators/dftb.html) · [ASE — Changelog](https://ase-lib.org/changelog.html)
- [cclib](https://cclib.github.io/index.html)
- [quacc — The Quantum Accelerator](https://quantum-accelerators.github.io/quacc/)
- [OPI — ORCA Python Interface](https://www.faccts.de/docs/orca/6.1/manual/contents/workflowsautomatization/orcapythoninterface.html) · [orca-pi (PyPI)](https://pypi.org/project/orca-pi/) · [faccts/opi](https://github.com/faccts/opi)
- [hsd-python](https://github.com/dftbplus/hsd-python) · [DFTB+ — Python interface](https://dftbplus-recipes.readthedocs.io/en/latest/interfaces/pyapi/pyapi.html)
- [AbiPy](https://github.com/abinit/abipy) · [Abinit — topic AbiPy](https://docs.abinit.org/topics/Abipy/)
- [pymatgen.io](https://pymatgen.org/pymatgen.io.html) · [pySCF ⇄ ASE](https://github.com/pyscf/pyscf/blob/master/examples/pbc/09-talk_to_ase.py)
- [MolSSI QCEngine](https://github.com/MolSSI/QCEngine)
