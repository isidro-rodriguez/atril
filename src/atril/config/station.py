"""Configuración de la estación (``atril.toml``).

La estación es la carpeta que contiene ``atril.toml``. Su estructura es fija:

- ``app/``: checkout de DeepTutor (reconstruible, sin backup).
- ``data/``: ``DEEPTUTOR_HOME`` (ajustes, KB, índices, chats).
- ``temarios/<id>/``: un temario por carpeta, cada uno con su ``temario.toml``.
"""

from dataclasses import dataclass
from pathlib import Path

from acodo.utils import valid_path, valid_slug, valid_url

from atril.config._toml import ConfigError, Table, load_toml

STATION_FILE = "atril.toml"
"""Nombre del fichero de configuración en la raíz de la estación."""

DEEPTUTOR_REPO = "https://github.com/HKUDS/DeepTutor"
"""Repositorio de DeepTutor por defecto."""


@dataclass(frozen=True, slots=True)
class DeepTutorConfig:
    """Tabla ``[deeptutor]``: checkout, puertos y parches de atril."""

    repo: str
    branch: str
    backend_port: int
    frontend_port: int
    patches: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    """Tabla ``[ollama]``: servidor y modelo de embedding.

    ``context`` debe coincidir con ``OLLAMA_CONTEXT_LENGTH`` del servidor y con la
    ventana de contexto declarada en DeepTutor.
    """

    url: str
    embedding: str
    dimension: int
    context: int


@dataclass(frozen=True, slots=True)
class IndexingConfig:
    """Tabla ``[indexado]``: valores que se exigen a DeepTutor al indexar."""

    parser: str
    chunk_size: int
    chunk_overlap: int


@dataclass(frozen=True, slots=True)
class BackupTarget:
    """Destino de backup ``[backup.destinos.<nombre>]`` (repositorio restic)."""

    name: str
    repo: str


@dataclass(frozen=True, slots=True)
class Retention:
    """Retención de snapshots de restic (``restic forget --keep-*``)."""

    daily: int
    weekly: int
    monthly: int


@dataclass(frozen=True, slots=True)
class BackupConfig:
    """Tabla ``[backup]``.

    La contraseña de restic nunca va en ``atril.toml``: se toma del entorno
    (``RESTIC_PASSWORD`` o ``RESTIC_PASSWORD_FILE``).
    """

    targets: tuple[BackupTarget, ...]
    retention: Retention
    git_repos: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class Station:
    """Configuración completa de una estación."""

    root: Path
    deeptutor: DeepTutorConfig
    ollama: OllamaConfig
    indexing: IndexingConfig
    backup: BackupConfig

    @property
    def app_dir(self) -> Path:
        """Checkout de DeepTutor."""
        return self.root / "app"

    @property
    def data_dir(self) -> Path:
        """``DEEPTUTOR_HOME``."""
        return self.root / "data"

    @property
    def syllabi_dir(self) -> Path:
        """Carpeta de temarios."""
        return self.root / "temarios"

    @property
    def deeptutor_cli(self) -> Path:
        """Ejecutable ``deeptutor`` del entorno virtual de ``app/`` (Windows)."""
        return self.app_dir / ".venv" / "Scripts" / "deeptutor.exe"


def find_station(start: Path) -> Path:
    """Busca la raíz de la estación desde ``start`` hacia arriba.

    Args:
        start: Carpeta desde la que empezar (normalmente la actual).

    Returns:
        La primera carpeta, de ``start`` hacia la raíz, que contiene ``atril.toml``.

    Raises:
        ConfigError: Si ninguna la contiene.
    """
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / STATION_FILE).is_file():
            return folder
    raise ConfigError(
        f"No se encuentra {STATION_FILE} en {start} ni en sus carpetas superiores. "
        "Indica la estación con --estacion o la variable ATRIL_ESTACION."
    )


def load_station(root: Path) -> Station:
    """Lee y valida ``<root>/atril.toml``.

    Args:
        root: Raíz de la estación.

    Returns:
        La configuración validada.

    Raises:
        ConfigError: Si el fichero falta o no cumple el esquema.
    """
    path = root / STATION_FILE
    top = Table(load_toml(path), path)
    station = Station(
        root=root.resolve(),
        deeptutor=_deeptutor(top.get_table("deeptutor")),
        ollama=_ollama(top.get_table("ollama")),
        indexing=_indexing(top.get_table("indexado", required=False)),
        backup=_backup(top.get_table("backup")),
    )
    top.close()
    return station


def _url(table: Table, key: str, default: str | None = None) -> str:
    """URL http(s) válida."""
    value = table.get_str(key) if default is None else table.get_str(key, default)
    if not valid_url(value):
        raise table.error(f"'{key}' no es una URL válida: {value!r}.")
    return value


def _deeptutor(table: Table) -> DeepTutorConfig:
    """Tabla ``[deeptutor]``."""
    ports = table.get_table("puertos", required=False)
    backend = ports.get_int("backend", 8001)
    frontend = ports.get_int("frontend", 3782)
    ports.close()
    for port in (backend, frontend):
        if port > 65535:
            raise ports.error(f"puerto fuera de rango: {port}.")
    if backend == frontend:
        raise ports.error("backend y frontend no pueden usar el mismo puerto.")

    patches = table.get_str_list("parches", [])
    for patch in patches:
        if not valid_slug(patch):
            raise table.error(f"nombre de parche no válido: {patch!r}.")

    config = DeepTutorConfig(
        repo=_url(table, "repo", DEEPTUTOR_REPO),
        branch=table.get_str("rama", "dev"),
        backend_port=backend,
        frontend_port=frontend,
        patches=tuple(patches),
    )
    table.close()
    return config


def _ollama(table: Table) -> OllamaConfig:
    """Tabla ``[ollama]``."""
    config = OllamaConfig(
        url=_url(table, "url", "http://localhost:11434"),
        embedding=table.get_str("embedding"),
        dimension=table.get_int("dimension"),
        context=table.get_int("contexto", 8192),
    )
    table.close()
    return config


def _indexing(table: Table) -> IndexingConfig:
    """Tabla ``[indexado]`` (opcional)."""
    config = IndexingConfig(
        parser=table.get_str("parser", "docling"),
        chunk_size=table.get_int("chunk", 1024),
        chunk_overlap=table.get_int("solape", 150, minimum=0),
    )
    if config.chunk_overlap >= config.chunk_size:
        raise table.error("'solape' debe ser menor que 'chunk'.")
    table.close()
    return config


def _backup(table: Table) -> BackupConfig:
    """Tabla ``[backup]``."""
    targets_table = table.get_table("destinos")
    targets = []
    for name, target in targets_table.get_named_tables():
        if not valid_slug(name):
            raise targets_table.error(f"nombre de destino no válido: {name!r}.")
        targets.append(BackupTarget(name=name, repo=target.get_str("repo")))
        target.close()
    if not targets:
        raise targets_table.error("declara al menos un destino.")

    keep = table.get_table("retencion", required=False)
    retention = Retention(
        daily=keep.get_int("diarias", 7, minimum=0),
        weekly=keep.get_int("semanales", 4, minimum=0),
        monthly=keep.get_int("mensuales", 12, minimum=0),
    )
    keep.close()

    repos = table.get_str_list("repos_git", [])
    for repo in repos:
        if not valid_path(repo, absolute=True):
            raise table.error(f"'repos_git' exige rutas absolutas: {repo!r}.")

    config = BackupConfig(
        targets=tuple(targets),
        retention=retention,
        git_repos=tuple(Path(repo) for repo in repos),
    )
    table.close()
    return config


__all__ = [
    "BackupConfig",
    "BackupTarget",
    "ConfigError",
    "DeepTutorConfig",
    "IndexingConfig",
    "OllamaConfig",
    "Retention",
    "Station",
    "find_station",
    "load_station",
]
