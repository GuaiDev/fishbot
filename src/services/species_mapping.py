"""
Common name ↔ scientific name mapping for SDM training.
Only includes species that have SDM models or are candidates for future models.
"""

# common name (lowercase) → scientific name
COMMON_TO_SCIENTIFIC = {
    # SDM species (currently modelled)
    "creek chub": "Semotilus atromaculatus",
    "pumpkinseed": "Lepomis gibbosus",
    "yellow perch": "Perca flavescens",
    "brown bullhead": "Ameiurus nebulosus",
    "white sucker": "Catostomus commersonii",
    "brook stickleback": "Culaea inconstans",
    "rainbow darter": "Etheostoma caeruleum",
    "rock bass": "Ambloplites rupestris",
    "smallmouth bass": "Micropterus dolomieu",

    # High-priority targets for future models
    "channel catfish": "Ictalurus punctatus",
    "common carp": "Cyprinus carpio",
    "shorthead redhorse": "Moxostoma macrolepidotum",
    "silver redhorse": "Moxostoma anisurum",
    "golden redhorse": "Moxostoma erythrurum",
    "greater redhorse": "Moxostoma valenciennesi",
    "bowfin": "Amia calva",
    "common shiner": "Luxilus cornutus",
    "hornyhead chub": "Nocomis biguttatus",
    "river chub": "Nocomis micropogon",
    "western blacknose dace": "Rhinichthys obtusus",
    "longnose dace": "Rhinichthys cataractae",
    "bluntnose minnow": "Pimephales notatus",
    "fathead minnow": "Pimephales promelas",
    "northern hog sucker": "Hypentelium nigricans",
    "smallmouth buffalo": "Ictiobus bubalus",
    "bigmouth buffalo": "Ictiobus cyprinellus",
    "freshwater drum": "Aplodinotus grunniens",
    "walleye": "Sander vitreus",
    "northern pike": "Esox lucius",
    "largemouth bass": "Micropterus salmoides",
    "bluegill": "Lepomis macrochirus",
    "green sunfish": "Lepomis cyanellus",
    "black crappie": "Pomoxis nigromaculatus",
    "longnose gar": "Lepisosteus osseus",
    "rainbow trout": "Oncorhynchus mykiss",
    "brown trout": "Salmo trutta",
    "brook trout": "Salvelinus fontinalis",
    "lake trout": "Salvelinus namaycush",
    "chinook salmon": "Oncorhynchus tshawytscha",
    "coho salmon": "Oncorhynchus kisutch",

    # Microfishing targets
    "fantail darter": "Etheostoma flabellare",
    "johnny darter": "Etheostoma nigrum",
    "iowa darter": "Etheostoma exile",
    "least darter": "Etheostoma microperca",
    "northern redbelly dace": "Chrosomus eos",
    "rosyface shiner": "Notropis rubellus",
    "emerald shiner": "Notropis atherinoides",
    "spottail shiner": "Notropis hudsonius",
    "striped shiner": "Luxilus chrysocephalus",
    "spotfin shiner": "Cyprinella spiloptera",
    "brassy minnow": "Hybognathus hankinsoni",
    "central stoneroller": "Campostoma anomalum",
    "northern brook lamprey": "Ichthyomyzon fossor",
    "american brook lamprey": "Lethenteron appendix",
    "stonecat": "Noturus flavus",
    "tadpole madtom": "Noturus gyrinus",
    "brindled madtom": "Noturus miurus",
    "northern madtom": "Noturus stigmosus",
    "margined madtom": "Noturus insignis",
}

# scientific name → common name (reverse lookup)
SCIENTIFIC_TO_COMMON = {v: k for k, v in COMMON_TO_SCIENTIFIC.items()}


def common_to_scientific(common_name: str) -> str | None:
    """Convert a common name to scientific name.

    Handles partial matches and uncertain IDs (strips "(uncertain)" tags).
    Returns None if no match found.
    """
    clean = common_name.lower().replace("(uncertain)", "").strip()
    if clean in COMMON_TO_SCIENTIFIC:
        return COMMON_TO_SCIENTIFIC[clean]
    for common, scientific in COMMON_TO_SCIENTIFIC.items():
        if clean in common or common in clean:
            return scientific
    return None


def scientific_to_common(scientific_name: str) -> str | None:
    return SCIENTIFIC_TO_COMMON.get(scientific_name)
