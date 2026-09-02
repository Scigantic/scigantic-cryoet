"""scigantic_cryoet -- search the CZ CryoET Data Portal from Python.

>>> import scigantic_cryoet as cryoet
>>> cat = cryoet.CryoetCatalog()
>>> cat.search("neuron", organism="Homo sapiens").head()

See CryoetCatalog for the searchable index and CryoetClient for live
per-dataset reads straight from the portal's public bucket.
"""
from .catalog import CryoetCatalog, CryoetClient

__version__ = "0.1.0"

__all__ = ["CryoetCatalog", "CryoetClient", "__version__"]
