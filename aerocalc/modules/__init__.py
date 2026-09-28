"""Calculator modules.  Importing this package registers every calculator."""

from .. import core
from . import (aero, avionics, flightmech, fluids, gasdyn, propulsion, space,
               structures, thermo)

_MODULES = [aero, gasdyn, fluids, thermo, propulsion, flightmech, structures,
            space, avionics]


def load_all():
    for m in _MODULES:
        core.register_all(m.CALCULATORS)
