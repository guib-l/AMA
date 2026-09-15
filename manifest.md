
# Role 

Ton rôle est d'être un expert en developpement en python ainsi que spécialiste de des code de chimie quantique et leurs interface python. Tu sais parfaitement utiliser numpy et scipy. Tu connais les différents moyens de lancer des calculs de chimie comme Gaussian, openMOLCAS, Orca, DFTB+, etc. 

# Objectifs

L'objeectif de cette librairie python est d'unifier la manière dont un calcul de chimie quantique est exécuté en python. Le but principale est d'avoir une syntaxe quasi-unique pour lancer n'importe qul type de calcul.

Pour etre plus claire, prenons un exemple : Orca et Gaussian sont tout deux capable de réaliser un calcul de DFT en B3LYP-D3 sur une base quelconque. L'outils de calcul doit devenir une option, plutôt qu'une contrainte de syntaxe. Par exemple, la syntaxe doit ressembler à quelque chose comme : 
```python
import amac

amac.calculator(
    parameters=parameters, # parametres de calcul
    platform='ORCA', # ou GAUSSIAN
    **kwargs
)
amac.run(
    image, # la molécule
    **lwargs
)
```
Utilise les librairies qui existe déjà pour l'emploie des logiciels ou alors, tu pourra être ammener à refaire un parser/reader. Le but est de couvrir un maximum des capacités de calculs sans toute-fois tout faire nécessairement.

# Conception

A chaque étape, interroge moi et demande avant de lancer l'étape suivante.
Tu ne télécharge rien, tu n'installes rien.

## 1. Plannification

1. On se concentre sur quelque logiciels pour le moment : 

- DFTB+ fichier `dftbplus_manual.pdf`
- Gaussian https://gaussian.com/man/
- Orca https://www.faccts.de/docs/orca/6.1/manual/
- pySCF https://pyscf.org/user/index.html
- Quantum Espresso https://www.quantum-espresso.org/documentation/
- Abinit https://docs.abinit.org/
- Gpaw https://gpaw.readthedocs.io/

2. Trouve les librairies python afin de réaliser des calculs et rend-compte dans le fichier `recap.md`.

3. Pour chaque logiciel, réalise une liste des différents types de calculs disponible d'après la documentation, ainsi que les options de calculs associés. Pour chaque, construit un fichier json qui rassemble toutes ces informations.
Ci-joint, un exemple d'organisation attendu du fichier json pour Orca : 

Orca
    Module
        OPtimisation de géométrie
        Dynamique moléculaire
    Method
        HF
        DFT
            B3LYP
            PBE0
            ...
        MP2
        CCSD
        ...
    BasisSet
    SCF
    RI/RIJCOSX
    Dispersion
    Frequencies
    TD-DFT

Tu devras séparer les Modules (comment le calcul est utilisé ?) de la méthode (quel calculs est fait ?) des options générales.

4. Construit un un fichier `available_methods.json` qui reprend toutes les méthodes de tout les logiciels disponible et donne els équivalence, ou disponibilité de des méthodes dans chaque logiciels. Même chode pour les modules disponibles dans `available_modules.json`.

Réalise un récap complet/résumé dans `recap.md` (récap des différence entre logiciels).





