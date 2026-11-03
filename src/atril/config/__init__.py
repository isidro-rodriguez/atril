"""Esquemas y carga de ``atril.toml`` (estación) y ``temario.toml`` (temarios)."""

from atril.config._toml import ConfigError as ConfigError
from atril.config.station import Station as Station
from atril.config.station import find_station as find_station
from atril.config.station import load_station as load_station
from atril.config.syllabus import Syllabus as Syllabus
from atril.config.syllabus import load_syllabi as load_syllabi
from atril.config.syllabus import load_syllabus as load_syllabus
