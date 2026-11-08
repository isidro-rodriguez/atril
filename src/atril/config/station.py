"""Configuración de la estación (``atril.toml``).

La estación es la carpeta que contiene ``atril.toml`` y es también el
``DEEPTUTOR_HOME`` (``deeptutor --home``). Su estructura es fija:

- ``app/``: checkout de DeepTutor (reconstruible, sin backup).
- ``data/``: datos que DeepTutor crea bajo su ``home`` (ajustes, KB, índices, chats).
- ``temarios/<id>/``: un temario por carpeta, cada uno con su ``temario.toml``.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from acodo.utils import valid_path, valid_url

from atril.config._toml import ConfigError, Table, load_toml
from atril.patches import PATCHES

STATION_FILE = "atril.toml"
"""Nombre del fichero de configuración en la raíz de la estación."""

DEEPTUTOR_REPO = "https://github.com/HKUDS/DeepTutor"
"""Repositorio de DeepTutor por defecto."""

PARSERS = frozenset(
    {"text_only", "docling", "mineru", "markitdown", "pymupdf4llm", "liteparse", "tika"}
)
"""Parsers de documentos de DeepTutor (``document_parsing.engine``)."""


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Tabla ``[deeptutor.llm]``: proveedor y modelo de chat de DeepTutor.

    Solo admite proveedores sin clave en el fichero (p. ej. ``claude_code`` con
    OAuth); las claves de API nunca van en ``atril.toml``.
    """

    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class DeepTutorConfig:
    """Tabla ``[deeptutor]``: checkout, puertos y parches de atril."""

    repo: str
    branch: str
    python: str
    backend_port: int
    frontend_port: int
    patches: tuple[str, ...]
    packages: tuple[str, ...]
    """Paquetes extra que se instalan en ``app/.venv`` (``uv pip install``)."""
    llm: LlmConfig | None
    search: str | None
    """Proveedor de búsqueda web de DeepTutor (``duckduckgo``...)."""


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
    download_models: bool
    """Permite que el parser descargue sus modelos locales (Docling, MinerU)."""
    threads: int = 0
    """Hilos de CPU para el parser y el troceado; 0 = sin límite."""
    batch_size: int = 10
    """Fragmentos por petición de embedding (lote pequeño = ráfagas de GPU cortas)."""
    pause_ms: int = 0
    """Intervalo mínimo entre peticiones de embedding, en milisegundos."""


ARCHIVE_FORMATS = ("zip", "tar.xz")
"""Formatos de backup: ``zip`` (deflate 9) o ``tar.xz`` (xz 9, más lento y compacto)."""


@dataclass(frozen=True, slots=True)
class BackupConfig:
    """Tabla ``[backup]``: copias comprimidas de la estación en carpetas."""

    destinations: tuple[Path, ...]
    """Carpetas donde se guardan las copias (disco externo, Google Drive...)."""
    archive_format: str
    """``zip`` o ``tar.xz``."""
    keep: int
    """Copias que se conservan en cada destino; las más antiguas se borran."""


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
        """Datos de DeepTutor (``<DEEPTUTOR_HOME>/data``)."""
        return self.root / "data"

    @property
    def launcher_log(self) -> Path:
        """Log del último ``deeptutor start``."""
        return self.data_dir / "user" / "runtime" / "launcher.log"

    @property
    def knowledge_dir(self) -> Path:
        """Bases de conocimiento de DeepTutor."""
        return self.data_dir / "knowledge_bases"

    def kb_dir(self, kb_id: str) -> Path:
        """Carpeta de una KB en DeepTutor."""
        return self.knowledge_dir / kb_id

    @property
    def logs_dir(self) -> Path:
        """Logs de atril (indexados, evaluaciones); en ``data/``, entra en el backup."""
        return self.data_dir / "atril" / "logs"

    @property
    def launcher_state(self) -> Path:
        """Estado del lanzador en segundo plano (``pid``, ``status``)."""
        return self.data_dir / "user" / "runtime" / "launcher.json"

    @property
    def lock_file(self) -> Path:
        """Bloqueo de operaciones largas; en la raíz, fuera de copias y restauración."""
        return self.root / ".atril.lock"

    @property
    def syllabi_dir(self) -> Path:
        """Carpeta de temarios."""
        return self.root / "temarios"

    @property
    def venv_python(self) -> Path:
        """Python del entorno virtual de ``app/``."""
        if sys.platform == "win32":
            return self.app_dir / ".venv" / "Scripts" / "python.exe"
        return self.app_dir / ".venv" / "bin" / "python"

    @property
    def deeptutor_cli(self) -> Path:
        """Ejecutable ``deeptutor`` del entorno virtual de ``app/``."""
        if sys.platform == "win32":
            return self.app_dir / ".venv" / "Scripts" / "deeptutor.exe"
        return self.app_dir / ".venv" / "bin" / "deeptutor"


STATION_TEMPLATE = """\
# atril.toml: configuración de la estación (referencia: docs/esquemas.md de atril).

[deeptutor]
# rama = "dev"
# parches = ["paginas-citas", "arranque-sin-ventana"]

[ollama]
embedding = "qwen3-embedding:8b"
dimension = 4096

[backup]
destinos = ['E:\\backups-atril']  # carpetas para las copias; cámbialo por la tuya
"""
"""``atril.toml`` mínimo y válido para una estación nueva."""


def init_station(root: Path) -> None:
    """Crea la estación en ``root``: ``atril.toml`` mínimo y ``temarios/``.

    Raises:
        ConfigError: Si ya existe ``atril.toml`` en ``root``.
    """
    path = root / STATION_FILE
    if path.exists():
        raise ConfigError(f"{path} ya existe; no se sobrescribe.")
    (root / "temarios").mkdir(parents=True, exist_ok=True)
    path.write_text(STATION_TEMPLATE, encoding="utf-8")


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
        backup=_backup(top.get_table("backup"), root.resolve()),
    )
    top.close()
    return station


def _inside(path: Path, root: Path) -> bool:
    """``path`` es ``root`` o está dentro (comparando rutas, no texto)."""
    if not path.is_absolute():
        return False
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


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
        if patch not in PATCHES:
            known = ", ".join(sorted(PATCHES))
            raise table.error(f"parche desconocido: {patch!r} (disponibles: {known}).")

    llm_table = table.get_table("llm", required=False)
    provider = llm_table.get_str("proveedor", None)
    model = llm_table.get_str("modelo", None)
    llm_table.close()
    if (provider is None) != (model is None):
        raise llm_table.error("declara a la vez 'proveedor' y 'modelo'.")
    llm = LlmConfig(provider, model) if provider and model else None

    config = DeepTutorConfig(
        repo=_url(table, "repo", DEEPTUTOR_REPO),
        branch=table.get_str("rama", "dev"),
        python=table.get_str("python", "3.13"),
        backend_port=backend,
        frontend_port=frontend,
        patches=tuple(patches),
        packages=tuple(table.get_str_list("paquetes", [])),
        llm=llm,
        search=table.get_str("busqueda", None),
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
        download_models=table.get_bool("descargar_modelos", True),
        threads=table.get_int("hilos", 0, minimum=0),
        batch_size=table.get_int("lote_embedding", 10),
        pause_ms=table.get_int("pausa_embedding", 0, minimum=0),
    )
    if config.parser not in PARSERS:
        raise table.error(
            f"parser desconocido: {config.parser!r} "
            f"(disponibles: {', '.join(sorted(PARSERS))})."
        )
    if config.chunk_overlap >= config.chunk_size:
        raise table.error("'solape' debe ser menor que 'chunk'.")
    table.close()
    return config


def _backup(table: Table, root: Path) -> BackupConfig:
    """Tabla ``[backup]``; ``root`` es la raíz de la estación."""
    folders = table.get_str_list("destinos")
    if not folders:
        raise table.error("declara al menos una carpeta en 'destinos'.")
    destinations: list[Path] = []
    for folder in folders:
        if not valid_path(folder, absolute=True):
            raise table.error(f"'destinos' exige rutas absolutas: {folder!r}.")
        path = Path(folder)
        if _inside(path, root):
            raise table.error(
                f"el destino {folder!r} está dentro de la estación: se copiaría a "
                "sí mismo y se perdería con ella."
            )
        if path in destinations:
            raise table.error(f"destino repetido: {folder!r}.")
        destinations.append(path)
    archive_format = table.get_str("formato", "zip")
    if archive_format not in ARCHIVE_FORMATS:
        raise table.error(
            f"'formato' debe ser {' o '.join(ARCHIVE_FORMATS)}: {archive_format!r}."
        )
    config = BackupConfig(
        destinations=tuple(destinations),
        archive_format=archive_format,
        keep=table.get_int("conservar", 7),
    )
    table.close()
    return config


__all__ = [
    "BackupConfig",
    "ConfigError",
    "DeepTutorConfig",
    "IndexingConfig",
    "LlmConfig",
    "OllamaConfig",
    "Station",
    "init_station",
    "load_station",
]
