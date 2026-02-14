from enum import Enum


class PetSpecies(str, Enum):
    CANINO = "Canino"
    FELINO = "Felino"
    EXOTICOS = "Exoticos"


class PetSize(str, Enum):
    PP = "PP"
    P = "P"
    M = "M"
    G = "G"
    GG = "GG"
